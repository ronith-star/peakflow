"""Calibrate the hybrid cooling model to the Falls Township (AWS Keystone Trade Center) water targets.

Targets, all from pages opened on 2026-09-25:
  average cooling service-water flow 135,000 gal/day and peak demand 4.4 million gal/day, with about
    40 percent returned to the industrial WWTP [falls_levittown_2026];
  peak 4.4 million gal/day and water cooling for about 6 percent of yearly operations [falls_herald_2026];
  water-based cooling for "less than 2%" of the year (Amazon) [amazon_falls_campus_2026], used as a
    sensitivity on the wet-hour share.
The 19,000 gal/day figure reported in the same LevittownNow article is the facility's POTABLE water demand
("equivalent to about 70 residential homes"); it is recorded here but is not a cooling target.

Free parameters: switchover wet-bulb T_sw, part-load exponent gamma, and IT load P_IT (MW); no IT or campus
capacity for Falls has been located in an opened source. PUE (1.2) and cycles of concentration (4) are
fixed assumptions; only P_IT * PUE * C/(C-1) is identifiable from water targets. Three parameters, three
targets: "feasible" means an exact solution exists inside plausible bounds.

"Peak demand" is not defined as a design rate or a realized calendar day, so both are fitted:
  A. peak_day    : peak = largest realized calendar-day makeup in the record (primary; every source calls
                   4.4 MGD a peak daily withdrawal).
  B. design_rate : peak = maximum hourly makeup rate in the 20-year KTTN record, times 24 (sensitivity).
With three free parameters and three targets the system is exactly determined: a zero residual shows that a
solution exists inside the bounds, not that the model is validated.
Climate: KTTN hourly wet-bulb, 2005-2024 [noaa_isd], Stull (2011) [stull_2011].
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import brentq, least_squares

from .cooling_model import CoolingParams, daily_makeup, evaporative_fraction, hourly_makeup_gal, wue_l_per_kwh
from .paths import PROCESSED, RESULTS

TARGETS = {"avg_gpd": 135_000.0, "peak_gpd": 4_400_000.0, "wet_hour_frac": 0.06}
WET_FRAC_SENSITIVITY = 0.02  # Amazon: "less than 2% of the year" (upper bound used)
POTABLE_GPD = 19_000.0       # documented potable demand, not a cooling target
TARGET_SOURCES = {
    "avg_gpd": "falls_levittown_2026", "peak_gpd": "falls_levittown_2026; falls_herald_2026",
    "wet_hour_frac": "falls_herald_2026; falls_levittown_2026", "wet_hour_frac_sensitivity": "amazon_falls_campus_2026",
    "potable_gpd": "falls_levittown_2026",
}
PUE = 1.2
CYCLES = 4.0
SENS_P_IT_MW = 178.0 + 75.0
SENS_SOURCE = ("https://cleanview.co/data-centers/pennsylvania/1861/aws-keystone-trade-center---building-1 ; "
               "https://cleanview.co/data-centers/pennsylvania/3439/aws-keystone-trade-center---building-2")
L_PER_GAL = 3.785411784


def load_kttn() -> pd.DataFrame:
    w = pd.read_parquet(PROCESSED / "weather_hourly.parquet")
    return w[w.station == "KTTN"].reset_index(drop=True)


def params(x, twb_ref) -> CoolingParams:
    return CoolingParams(p_it_mw=float(x[2]), pue=PUE, cycles=CYCLES, t_sw_c=float(x[0]), gamma=float(x[1]),
                         twb_ref_c=float(twb_ref), architecture="hybrid")


def model_stats(x, w: pd.DataFrame, twb_ref: float) -> dict:
    p = params(x, twb_ref)
    twb = w.wetbulb_c.to_numpy()
    valid = ~np.isnan(twb)
    h = hourly_makeup_gal(twb[valid], p)
    d = daily_makeup(w, p)
    return {
        "avg_gpd": float(d.makeup_gpd.mean()),
        "design_rate_gpd": float(h.max() * 24.0),
        "peak_day_gpd": float(d.makeup_gpd.max()),
        "p99_day_gpd": float(d.makeup_gpd.quantile(0.99)),
        "max_30day_avg_gpd": float(d.makeup_gpd.rolling(30, min_periods=27).mean().max()),
        "wet_hour_frac": float((evaporative_fraction(twb[valid], p) > 0).mean()),
        "wue_l_per_kwh": float(wue_l_per_kwh(p, float(np.mean(evaporative_fraction(twb[valid], p))))),
    }


def fit(w: pd.DataFrame, interpretation: str, targets: dict = TARGETS, p_it_fixed: float | None = None) -> dict:
    """Structured solve. Wet-hour share depends only on T_sw, so T_sw is the (1 - share) quantile of hourly
    wet-bulb. With P_IT free, peak/avg is independent of P_IT, so gamma solves the average at the peak-pinned
    P_IT (design_rate) or the peak/avg ratio (peak_day); P_IT then scales the level. With P_IT fixed, T_sw
    and gamma are fitted by least squares on log residuals."""
    twb_ref = float(np.nanmax(w.wetbulb_c))
    peak_key = "design_rate_gpd" if interpretation == "design_rate" else "peak_day_gpd"
    twb = w.wetbulb_c.to_numpy()
    twb = twb[~np.isnan(twb)]
    t_sw = float(np.quantile(twb, 1.0 - targets["wet_hour_frac"]))
    G = (0.02, 10.0)
    infeasible_note = None
    if p_it_fixed is None:
        if interpretation == "design_rate":
            s1 = model_stats([t_sw, 1.0, 100.0], w, twb_ref)
            p_it = 100.0 * targets["peak_gpd"] / s1["design_rate_gpd"]
            f = lambda g: model_stats([t_sw, g, p_it], w, twb_ref)["avg_gpd"] - targets["avg_gpd"]
            if f(G[0]) < 0:  # even a step-function hybrid (gamma -> 0) cannot reach the average
                gamma = G[0]
                infeasible_note = (f"Average target unreachable: with wet share {targets['wet_hour_frac']:.3f} the average "
                                   f"cannot exceed about peak x wet share = {targets['peak_gpd'] * targets['wet_hour_frac']:,.0f} "
                                   f"gal/day; closest fit (gamma at lower bound {G[0]}) reported.")
            else:
                gamma = brentq(f, *G)
        else:
            ratio = targets["peak_gpd"] / targets["avg_gpd"]
            f = lambda g: (lambda s: s["peak_day_gpd"] / s["avg_gpd"])(model_stats([t_sw, g, 100.0], w, twb_ref)) - ratio
            if f(G[0]) > 0:  # smallest achievable peak/avg ratio still exceeds the target ratio
                gamma = G[0]
                infeasible_note = (f"Peak-to-average ratio {ratio:.1f} unreachable at wet share "
                                   f"{targets['wet_hour_frac']:.3f}; closest fit (gamma at lower bound {G[0]}) reported, "
                                   f"P_IT set to match the average.")
            else:
                gamma = brentq(f, *G)
            p_it = 100.0 * targets["avg_gpd"] / model_stats([t_sw, gamma, 100.0], w, twb_ref)["avg_gpd"]
        x = [t_sw, gamma, p_it]
    else:
        def resid(v):
            s = model_stats([v[0], v[1], p_it_fixed], w, twb_ref)
            return [np.log(s["avg_gpd"] / targets["avg_gpd"]), np.log(s[peak_key] / targets["peak_gpd"]),
                    np.log(s["wet_hour_frac"] / targets["wet_hour_frac"])]
        r = least_squares(resid, [t_sw, 0.5], bounds=([15.0, G[0]], [28.0, G[1]]), diff_step=[1e-2, 1e-2])
        x = [float(r.x[0]), float(r.x[1]), float(p_it_fixed)]
        infeasible_note = "P_IT fixed; two-parameter least-squares fit, residuals as reported."
    s = model_stats(x, w, twb_ref)
    achieved = {"avg_gpd": s["avg_gpd"], "peak_gpd": s[peak_key], "wet_hour_frac": s["wet_hour_frac"]}
    rel = {k: achieved[k] / targets[k] - 1.0 for k in targets}
    return {
        "interpretation": interpretation,
        "t_sw_c": float(x[0]), "gamma": float(x[1]), "p_it_mw": float(x[2]),
        "pue": PUE, "cycles": CYCLES, "twb_ref_c": twb_ref,
        "targets": dict(targets), "achieved": achieved, "relative_residual": rel,
        "all_three_feasible_within_1pct": bool(max(abs(v) for v in rel.values()) < 0.01),
        "infeasibility_note": infeasible_note,
        "peak_to_average_ratio_target": targets["peak_gpd"] / targets["avg_gpd"],
        "implied_site_wue_l_per_kwh": achieved["avg_gpd"] * L_PER_GAL / (float(x[2]) * 24_000.0),
        "implied_site_wue_from_target_avg_l_per_kwh": targets["avg_gpd"] * L_PER_GAL / (float(x[2]) * 24_000.0),
        "diagnostics": s,
    }


def run() -> dict:
    w = load_kttn()
    t2 = dict(TARGETS, wet_hour_frac=WET_FRAC_SENSITIVITY)
    out = {
        "climate": "KTTN hourly wet-bulb (Stull 2011), 2005-01-01 to 2024-12-31 UTC",
        "target_sources": TARGET_SOURCES,
        "potable_demand_gpd": POTABLE_GPD,
        "primary": fit(w, "peak_day"),
        "alternative": fit(w, "design_rate"),
        "sensitivity_wet_2pct": {"source": "amazon_falls_campus_2026",
                                 "design_rate": fit(w, "design_rate", t2), "peak_day": fit(w, "peak_day", t2)},
        # P_IT fixed at an UNVERIFIED third-party figure (Cleanview: Building 1 = 178 MW, Building 2 = 75 MW;
        # seen only in search-result text, not rendered on the opened page). Not used downstream.
        "sensitivity_fixed_p_it": {"p_it_mw": SENS_P_IT_MW, "source": SENS_SOURCE, "verified": False,
                                   "design_rate": fit(w, "design_rate", p_it_fixed=SENS_P_IT_MW),
                                   "peak_day": fit(w, "peak_day", p_it_fixed=SENS_P_IT_MW)},
        "p_it_provenance": "inferred (fitted); no IT or campus capacity located in Falls Township, PECO/PJM "
                           "(FERC ER25-3492) or Bucks County press sources opened to date",
        "notes": [
            "P_IT is a fitted scale parameter, not a filed capacity; only P_IT*PUE*C/(C-1) is identified.",
            "Feasible means every target is reproduced within 1 percent inside the parameter bounds.",
            "Three free parameters are fitted to three targets, so the fit is exactly determined; zero residuals "
            "show only that a solution exists and are not validation.",
            "Primary reading: 4.4 MGD is the largest realized calendar-day makeup (peak_day); the design-rate "
            "reading (maximum hourly rate x 24) is kept as the 'alternative' sensitivity.",
            "Wet-hour share depends only on T_sw; small residuals on it are quantile ties in 0.01 C wet-bulb data.",
            "19,000 gal/day is documented potable demand and is not a cooling target.",
        ],
    }
    (RESULTS / "calibration.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    r = run()
    for k in ("primary", "alternative"):
        print(k, {x: r[k][x] for x in ("t_sw_c", "gamma", "p_it_mw", "relative_residual", "all_three_feasible_within_1pct")})
    for k in ("design_rate", "peak_day"):
        s = r["sensitivity_wet_2pct"][k]
        print("wet2", k, {x: s[x] for x in ("t_sw_c", "gamma", "p_it_mw", "relative_residual")})
        s = r["sensitivity_fixed_p_it"][k]
        print("fix253", k, {x: s[x] for x in ("t_sw_c", "gamma", "relative_residual")})
