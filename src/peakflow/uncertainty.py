"""Monte Carlo uncertainty in peak-day cooling makeup for the 24 active planned sites.

For every site in results/supply_screen.csv, N_DRAWS draws of peak-day cooling makeup (gal/day) are made and
compared with the median flow of the site's nearest eligible municipal plant (plant_median_flow_mgd * 1e6).

Per draw (one numpy default_rng, seed SEED, common random numbers across scenarios):
  architecture  categorical: evaporative tower / hybrid / air-cooled chiller. Primary weights are LBNL 2024
                Figure 4.2 (p.39), hyperscale bar for 2023, digitized from data/raw/lbnl_2024.pdf and grouped
                into the three model architectures (LBNL_SYSTEM_GROUPS). Sensitivities: the LBNL 'Midsize and
                Colo' bar, and the assumed weights 0.3 / 0.5 / 0.2.
  site WUE      annual-average site WUE (L per IT kWh) from LBNL 2024 Figure 4.4 (p.46), large-scale boxes,
                digitized from the PDF. Distribution: piecewise-linear quantile function through (lower
                whisker, Q1, median, Q3, upper whisker) at p = (0, 0.25, 0.5, 0.75, 1); the figure does not state
                its whisker rule (the whiskers extend beyond 1.5 IQR), so the whiskers are treated as the range
                ends. Evaporative tower: 'Waterside economizer (water-cooled chiller)', the only large-scale
                system that rejects heat through cooling towers all year. Hybrid: 'Airside economizer &
                adiabatic cooling (water-cooled chiller)', the most common water-using hyperscale system in
                Figure 4.2 (sensitivity: 'Dry cooler with adiabatic assist (air-cooled chiller)'). Air-cooled
                chiller: zero makeup (the model's closed dry loop; LBNL shows near-zero site WUE).
  PUE           uniform on 1.15 to 1.35, LBNL's projected 2028 average PUE range (p.48).
  IT load       stated sites (capacity_basis != 'assumed_100MW_IT') use it_mw; unstated sites resample, with
                equal probability, the IT loads of the 8 stated active sites in the screen (sensitivity:
                the deterministic screen's assumed 100 MW).

Conversion from annual WUE to peak-day makeup per MW IT:
  average gpd/MW = WUE [L/kWh] * 1000 kWh/MWh * 24 h/day / 3.785411784 L/gal = WUE * 6,340.13
  heat rejected scales with PUE (cooling_model: Q = P_IT * PUE), so LBNL's WUE, simulated at its own PUE, is
  rescaled by PUE_draw / PUE_ref, PUE_ref = the median PUE of the same large-scale box in Figure 4.4.
  peak-day = average * R_arch, R_arch = the cooling model's max-day / mean-day ratio on KTTN 2005-2024
  (evaporative tower 1.0 because phi = 1 every hour; calibrated hybrid 32.59; air-cooled has no makeup).
  A hybrid peak day cannot exceed full evaporation of the day's heat, so hybrid draws are capped at the
  evaporative-tower peak day of the model at the drawn PUE (cycles 4); the share of capped draws is reported.
  Sensitivity 'variable_ratio': instead of a fixed R, the hybrid switchover wet-bulb T_sw is re-solved (gamma
  fixed at the calibrated value) so that the model's annual WUE equals the drawn WUE, and the peak day is that
  re-solved model's maximum day.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import blindspot as B
from .cooling_model import EVAP_M3_PER_MWH
from .paths import FIGURES, RAW, RESULTS

SEED = 20260925
N_DRAWS = 10_000
L_PER_GAL = 3.785411784
GPD_PER_MW_PER_LKWH = 1000.0 * 24.0 / L_PER_GAL   # 6,340.13 gal/day per MW IT per (L/kWh)
PUE_RANGE = (1.15, 1.35)
ARCHS = ("evaporative_tower", "hybrid", "air_cooled_chiller")
ASSUMED_BASIS = "assumed_100MW_IT"
LBNL_PDF = RAW / "lbnl_2024.pdf"

# ---------------------------------------------------------------- LBNL 2024 Figure 4.4 (p.46), digitized
# Five-number summaries (lower whisker, Q1, median, Q3, upper whisker) in L/kWh (WUE) and PUE, read from the
# large-scale boxes by digitize_figure_4_4() at 8x render (1 px = 0.0035 L/kWh; 0.0013 PUE). Values rounded to
# 0.01 L/kWh and 0.001 PUE. A negative lower whisker (line-width artifact at 0) is clipped to 0.
FIG44_ROWS = [  # row order top to bottom in the figure (17 rows)
    "small_direct_expansion", "small_air_cooled_chiller", "small_water_cooled_chiller",
    "mid_direct_expansion", "mid_air_cooled_chiller", "mid_dry_cooler_acc", "mid_airside_econ_acc",
    "mid_water_cooled_chiller", "mid_airside_econ_wcc", "mid_waterside_econ_wcc",
    "large_dry_cooler_adiabatic_acc", "large_airside_econ_adiabatic_acc", "large_airside_econ_adiabatic_wcc",
    "large_waterside_econ_wcc", "large_liquid_waterside_econ_wcc", "large_liquid_dry_cooler_adiabatic_acc",
    "large_liquid_dry_cooler_acc"]
LBNL_WUE = {
    "large_waterside_econ_wcc": (1.72, 2.04, 2.18, 2.31, 2.78),
    "large_airside_econ_adiabatic_wcc": (0.00, 0.21, 0.42, 0.72, 1.56),
    "large_dry_cooler_adiabatic_acc": (0.00, 0.17, 0.23, 0.31, 0.58),
}
LBNL_PUE = {
    "large_waterside_econ_wcc": (1.029, 1.098, 1.118, 1.138, 1.228),
    "large_airside_econ_adiabatic_wcc": (1.008, 1.114, 1.144, 1.167, 1.279),
    "large_dry_cooler_adiabatic_acc": (1.053, 1.169, 1.199, 1.233, 1.350),
}
FIG44_LABEL = {
    "large_waterside_econ_wcc": "Waterside economizer (water-cooled chiller), large-scale",
    "large_airside_econ_adiabatic_wcc": "Airside economizer & adiabatic cooling (water-cooled chiller), large-scale",
    "large_dry_cooler_adiabatic_acc": "Dry cooler with adiabatic assist (air-cooled chiller), large-scale",
}
WUE_MAP = {"evaporative_tower": "large_waterside_econ_wcc", "hybrid": "large_airside_econ_adiabatic_wcc"}
WUE_MAP_ALT = {"evaporative_tower": "large_waterside_econ_wcc", "hybrid": "large_dry_cooler_adiabatic_acc"}

# ---------------------------------------------------------------- LBNL 2024 Figure 4.2 (p.39), digitized
# Percent of each bar (2023) by cooling system, read by digitize_figure_4_2() along the bar center line;
# 1 px = 0.065 percentage points; segments under 0.5 percent are near the reading limit.
FIG42_SHARES = {
    "hyperscale": {
        "airside_econ_adiabatic_acc": 42.05, "airside_econ_adiabatic_wcc": 42.89, "airside_econ_acc": 5.45,
        "airside_econ_wcc": 5.71, "direct_expansion": 1.04, "dry_cooler_acc": 0.52,
        "dry_cooler_adiabatic_acc": 0.52, "water_cooled_chiller": 0.26, "waterside_econ_wcc": 1.30,
        "air_cooled_chiller": 0.0},
    "midsize_colo": {
        "air_cooled_chiller": 12.98, "airside_econ_adiabatic_acc": 2.86, "airside_econ_adiabatic_wcc": 2.60,
        "airside_econ_acc": 14.28, "airside_econ_wcc": 14.54, "direct_expansion": 33.03, "dry_cooler_acc": 1.30,
        "dry_cooler_adiabatic_acc": 1.30, "water_cooled_chiller": 14.28, "waterside_econ_wcc": 2.60},
}
# Grouping of LBNL cooling systems into the three model architectures:
#   evaporative tower : cooling towers carry the load all year (water-cooled chiller, waterside economizer)
#   hybrid            : dry or outdoor-air cooling most of the year, water used in hot or humid hours
#                       (adiabatic systems, and airside economizers backed by a water-cooled chiller)
#   air-cooled        : no evaporative heat rejection (air-cooled chiller, DX, dry cooler, airside + ACC)
LBNL_SYSTEM_GROUPS = {
    "water_cooled_chiller": "evaporative_tower", "waterside_econ_wcc": "evaporative_tower",
    "airside_econ_adiabatic_acc": "hybrid", "airside_econ_adiabatic_wcc": "hybrid",
    "airside_econ_wcc": "hybrid", "dry_cooler_adiabatic_acc": "hybrid",
    "air_cooled_chiller": "air_cooled_chiller", "direct_expansion": "air_cooled_chiller",
    "dry_cooler_acc": "air_cooled_chiller", "airside_econ_acc": "air_cooled_chiller",
}
ASSUMED_WEIGHTS = {"evaporative_tower": 0.3, "hybrid": 0.5, "air_cooled_chiller": 0.2}


def grouped_weights(bar: str) -> dict:
    s = FIG42_SHARES[bar]
    tot = sum(s.values())
    return {a: sum(v for k, v in s.items() if LBNL_SYSTEM_GROUPS[k] == a) / tot for a in ARCHS}


# ---------------------------------------------------------------- scenarios
@dataclass
class Scenario:
    name: str
    weights: dict
    wue_map: dict = field(default_factory=lambda: dict(WUE_MAP))
    conversion: str = "fixed_ratio"          # or "variable_ratio"
    unstated_capacity: str = "resample_stated"  # or "fixed_100"
    note: str = ""


def scenarios() -> list[Scenario]:
    hyp, mid = grouped_weights("hyperscale"), grouped_weights("midsize_colo")
    return [
        Scenario("primary", hyp, note="LBNL Fig 4.2 hyperscale weights; fixed-ratio conversion; unstated IT "
                                      "load resampled from the 8 stated sites"),
        Scenario("weights_lbnl_midsize_colo", mid, note="LBNL Fig 4.2 'Midsize and Colo' bar"),
        Scenario("weights_assumed_30_50_20", dict(ASSUMED_WEIGHTS), note="assumed 0.3 / 0.5 / 0.2"),
        Scenario("hybrid_wue_dry_cooler_adiabatic", hyp, wue_map=dict(WUE_MAP_ALT),
                 note="hybrid WUE from the large-scale dry cooler with adiabatic assist box"),
        Scenario("variable_ratio_conversion", hyp, conversion="variable_ratio",
                 note="hybrid T_sw re-solved to each drawn WUE"),
        Scenario("unstated_fixed_100mw", hyp, unstated_capacity="fixed_100",
                 note="unstated sites at the deterministic screen's 100 MW; isolates cooling uncertainty"),
    ]


# ---------------------------------------------------------------- cooling-model conversion
def model_conversion(n_grid: int = 90) -> dict:
    """Peak-day-to-average ratios and the T_sw lookup for the variable-ratio conversion (1 MW IT, PUE 1.2)."""
    w, cal, _, _ = B.load_inputs("primary")
    out = {"calibration": {k: cal[k] for k in ("t_sw_c", "gamma", "twb_ref_c", "pue", "cycles")}}
    for arch in ("evaporative_tower", "hybrid"):
        d = B.daily_series(w, B.config_params(1.0, arch, cal))
        out[arch] = {"mean_gpd_per_mw": float(d.mean()), "peak_day_gpd_per_mw": float(d.max()),
                     "peak_to_average": float(d.max() / d.mean()), "n_valid_days": int(d.notna().sum())}
    k = B.PUE * EVAP_M3_PER_MWH * B.CYCLES / (B.CYCLES - 1.0)  # WUE (L/kWh) at phi = 1
    grid = np.linspace(-15.0, cal["twb_ref_c"] - 0.25, n_grid)
    phi_mean, phi_peak = [], []
    full = out["evaporative_tower"]["peak_day_gpd_per_mw"]
    for t in grid:
        p = B.config_params(1.0, "hybrid", {**cal, "t_sw_c": float(t)})
        d = B.daily_series(w, p)
        phi_mean.append(float(d.mean() / full))
        phi_peak.append(float(d.max() / full))
    out["variable_ratio_lookup"] = {"t_sw_c": grid.tolist(), "phi_mean": phi_mean, "phi_peak": phi_peak,
                                    "wue_at_phi1_pue1p2_l_per_kwh": k}
    return out


def _quantile_draw(u: np.ndarray, five: tuple) -> np.ndarray:
    lo, q1, med, q3, hi = five
    return np.interp(u, [0.0, 0.25, 0.5, 0.75, 1.0], [max(lo, 0.0), q1, med, q3, hi])


def uniforms(n: int = N_DRAWS, n_sites: int = 24, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    return {"arch": rng.random(n), "wue": rng.random(n), "pue": rng.random(n),
            "cap": rng.random((n_sites, n))}


def per_mw_draws(U: dict, sc: Scenario, conv: dict) -> pd.DataFrame:
    """Peak-day makeup per MW IT (gal/day) for every draw under scenario `sc`."""
    cw = np.cumsum([sc.weights[a] for a in ARCHS])
    idx = np.searchsorted(cw / cw[-1], U["arch"], side="right")
    arch = np.array(ARCHS)[np.minimum(idx, 2)]
    pue = PUE_RANGE[0] + (PUE_RANGE[1] - PUE_RANGE[0]) * U["pue"]
    full = conv["evaporative_tower"]["peak_day_gpd_per_mw"] * pue / B.PUE   # full evaporation at drawn PUE
    wue = np.zeros_like(pue)
    gpd = np.zeros_like(pue)
    capped = np.zeros(len(pue), bool)
    for a in ("evaporative_tower", "hybrid"):
        m = arch == a
        key = sc.wue_map[a]
        wue[m] = _quantile_draw(U["wue"][m], LBNL_WUE[key])
        pue_ref = LBNL_PUE[key][2]
        avg = wue[m] * GPD_PER_MW_PER_LKWH * pue[m] / pue_ref
        if a == "evaporative_tower":
            gpd[m] = avg * conv["evaporative_tower"]["peak_to_average"]
        elif sc.conversion == "fixed_ratio":
            raw = avg * conv["hybrid"]["peak_to_average"]
            capped[m] = raw > full[m]
            gpd[m] = np.minimum(raw, full[m])
        else:
            L = conv["variable_ratio_lookup"]
            phi_mean = wue[m] / (pue_ref * EVAP_M3_PER_MWH * B.CYCLES / (B.CYCLES - 1.0))
            order = np.argsort(L["phi_mean"])
            pm, pp = np.asarray(L["phi_mean"])[order], np.asarray(L["phi_peak"])[order]
            phi_peak = np.where(phi_mean < pm[0], phi_mean * pp[0] / pm[0], np.interp(phi_mean, pm, pp))
            capped[m] = phi_mean > pm[-1]
            gpd[m] = np.minimum(phi_peak, 1.0) * full[m]
    return pd.DataFrame({"arch": arch, "wue_l_per_kwh": wue, "pue": pue, "gpd_per_mw": gpd, "capped": capped})


def site_it_draws(ss: pd.DataFrame, U: dict, sc: Scenario) -> tuple[np.ndarray, np.ndarray]:
    stated = ss.capacity_basis.ne(ASSUMED_BASIS).to_numpy()
    pool = np.sort(ss.loc[stated, "it_mw"].to_numpy(float))
    n = U["cap"].shape[1]
    it = np.empty((len(ss), n))
    for i, (st, mw) in enumerate(zip(stated, ss.it_mw.to_numpy(float))):
        if st:
            it[i] = mw
        elif sc.unstated_capacity == "fixed_100":
            it[i] = 100.0
        else:
            it[i] = pool[np.minimum((U["cap"][i] * len(pool)).astype(int), len(pool) - 1)]
    return it, pool


def _bin(mw, has_plant):
    return np.where(~has_plant, "no eligible plant within 10 mi",
                    np.where(mw >= 200, "over 200 MW", "50 to 200 MW"))


def site_demand(ss: pd.DataFrame, U: dict, sc: Scenario, conv: dict):
    """(per-MW draw table, site x draw peak-day makeup array in gal/day, stated IT pool)."""
    pm = per_mw_draws(U, sc, conv)
    it, pool = site_it_draws(ss, U, sc)
    return pm, it * pm.gpd_per_mw.to_numpy()[None, :], pool


def primary_site_draws(seed: int = SEED, n: int = N_DRAWS) -> tuple[pd.DataFrame, np.ndarray]:
    """Supply-screen rows and the primary scenario's site x draw peak-day makeup (gal/day)."""
    ss = pd.read_csv(RESULTS / "supply_screen.csv")
    U = uniforms(n, len(ss), seed)
    _, dem, _ = site_demand(ss, U, scenarios()[0], model_conversion())
    return ss, dem


def evaluate(ss: pd.DataFrame, U: dict, sc: Scenario, conv: dict, per_mw_rate: float) -> tuple[pd.DataFrame, dict]:
    pm, dem, pool = site_demand(ss, U, sc, conv)
    q = np.quantile(dem, [0.10, 0.50, 0.90], axis=1)
    plant = (ss.plant_median_flow_mgd.to_numpy(float) * 1e6)
    has = np.isfinite(plant)
    prob = np.where(has, (dem <= np.where(has, plant, -1)[:, None]).mean(axis=1), 0.0)
    stated = ss.capacity_basis.ne(ASSUMED_BASIS).to_numpy()
    pmq = np.quantile(pm.gpd_per_mw, [0.10, 0.50, 0.90])
    cov_mw_p90 = np.where(has, plant / pmq[2], 0.0)
    df = pd.DataFrame({
        "site_id": ss.site_id, "name": ss.name,
        "it_mw_basis": np.where(stated, "stated", "drawn_from_stated_sites" if sc.unstated_capacity ==
                                "resample_stated" else "assumed_100MW_IT"),
        "it_mw_stated": np.where(stated, ss.it_mw, np.nan),
        "p10_peak_day_gpd": q[0], "p50_peak_day_gpd": q[1], "p90_peak_day_gpd": q[2],
        "plant_median_gpd": plant,
        "covers_p50": has & (plant >= q[1]), "covers_p90": has & (plant >= q[2]), "prob_covered": prob,
        "deterministic_peak_day_gpd": ss.it_mw.to_numpy(float) * per_mw_rate,
        "deterministic_class": ss["class"], "class_p90_cap": np.where(~has, "none",
                                                                       np.where(plant >= q[2], "matchable", "partial")),
        "covered_it_bin": ss.covered_it_bin, "covered_it_mw": ss.covered_it_mw,
        "covered_it_mw_p90": cov_mw_p90, "covered_it_bin_p90": _bin(cov_mw_p90, has),
    }).reset_index(drop=True)
    df["class_changes_at_p90"] = df.deterministic_class != df.class_p90_cap
    df["bin_changes_at_p90"] = df.covered_it_bin != df.covered_it_bin_p90
    arch_share = pm.arch.value_counts(normalize=True).reindex(list(ARCHS)).fillna(0).to_dict()
    summ = {
        "scenario": sc.name, "note": sc.note, "weights": sc.weights, "wue_map": sc.wue_map,
        "conversion": sc.conversion, "unstated_capacity": sc.unstated_capacity,
        "drawn_architecture_share": arch_share,
        "per_mw_peak_day_gpd": {"p10": float(pmq[0]), "p50": float(pmq[1]), "p90": float(pmq[2]),
                                "mean": float(pm.gpd_per_mw.mean())},
        "hybrid_draws_capped_share": float(pm.capped[pm.arch == "hybrid"].mean()) if (pm.arch == "hybrid").any() else 0.0,
        "n_sites": int(len(df)), "n_with_eligible_plant": int(has.sum()),
        "n_covers_p50": int(df.covers_p50.sum()), "n_covers_p90": int(df.covers_p90.sum()),
        "n_deterministic_matchable": int((df.deterministic_class == "matchable").sum()),
        "class_changes_at_p90": df.loc[df.class_changes_at_p90, ["site_id", "name", "deterministic_class",
                                                                 "class_p90_cap"]].to_dict("records"),
        "bin_changes_at_p90": df.loc[df.bin_changes_at_p90, ["site_id", "name", "covered_it_bin",
                                                             "covered_it_bin_p90"]].to_dict("records"),
        "stated_it_pool_mw": pool.tolist(),
    }
    above = has & (q[2] > np.where(has, plant, np.inf))
    df["p90_above_plant"] = above
    summ["n_p90_above_plant"] = int(above.sum())
    summ["sites_p90_above_plant"] = df.loc[above, ["site_id", "name"]].to_dict("records")
    summ["n_no_eligible_plant"] = int((~has).sum())
    return df, summ


def run(seed: int = SEED, n: int = N_DRAWS) -> dict:
    ss = pd.read_csv(RESULTS / "supply_screen.csv")
    key = pd.read_csv(FIGURES / "site_key.csv")[["number", "site_id"]]
    rates = json.loads((RESULTS / "supply_summary.json").read_text())["demand_rates"]
    per_mw = rates["peak_day_gpd_per_mw"]
    conv = model_conversion()
    U = uniforms(n, len(ss), seed)
    tables, summaries = {}, {}
    for sc in scenarios():
        tables[sc.name], summaries[sc.name] = evaluate(ss, U, sc, conv, per_mw)
    prim = tables["primary"].merge(key, on="site_id", how="left").rename(columns={"number": "map_number"})
    prim = prim.sort_values("map_number").reset_index(drop=True)
    prim.to_csv(RESULTS / "peak_uncertainty.csv", index=False)
    sens_sites = pd.concat([t.assign(scenario=k) for k, t in tables.items()], ignore_index=True)
    sens_sites.to_csv(RESULTS / "peak_uncertainty_sensitivity.csv", index=False)
    out = {
        "seed": seed, "n_draws": n, "rng": "numpy.random.default_rng (PCG64)",
        "common_random_numbers": "one set of uniforms (architecture, WUE, PUE, per-site capacity) reused in every "
                                 "scenario; architecture, WUE and PUE draws shared across sites",
        "distributions": {
            "architecture_weights_primary": grouped_weights("hyperscale"),
            "architecture_weights_source": "shehabi_2024 Figure 4.2 p.39 (hyperscale, 2023), digitized; grouping "
                                           "in LBNL_SYSTEM_GROUPS",
            "fig42_shares_percent": FIG42_SHARES, "lbnl_system_groups": LBNL_SYSTEM_GROUPS,
            "wue_l_per_kwh_five_number": {k: dict(zip(("lower_whisker", "q1", "median", "q3", "upper_whisker"), v))
                                          for k, v in LBNL_WUE.items()},
            "pue_five_number_same_boxes": {k: dict(zip(("lower_whisker", "q1", "median", "q3", "upper_whisker"), v))
                                           for k, v in LBNL_PUE.items()},
            "wue_source": "shehabi_2024 Figure 4.4 p.46 (large-scale boxes), digitized; whiskers treated as range ends",
            "wue_map_primary": WUE_MAP, "wue_labels": FIG44_LABEL,
            "air_cooled_chiller": "zero makeup (cooling_model phi = 0)",
            "pue": {"dist": "uniform", "low": PUE_RANGE[0], "high": PUE_RANGE[1],
                    "source": "shehabi_2024 p.48 (projected 2028 average PUE 1.15 to 1.35)"},
            "it_load": {"stated": "it_mw from results/supply_screen.csv (stated campus MW / PUE 1.2)",
                        "unstated": "equal-probability resample of the stated active-site IT loads",
                        "pool_mw": summaries["primary"]["stated_it_pool_mw"],
                        "source": "data/sites/planned_sites.csv via results/supply_screen.csv"},
        },
        "conversion": {"gpd_per_mw_per_l_per_kwh": GPD_PER_MW_PER_LKWH,
                       "formula": "peak_gpd_per_MW = WUE * 6340.13 * PUE_draw / PUE_ref * R_arch; hybrid capped "
                                  "at full evaporation (evaporative-tower peak day x PUE_draw / 1.2)",
                       "pue_ref": {k: LBNL_PUE[k][2] for k in LBNL_WUE}, "model": conv},
        "deterministic_peak_day_gpd_per_mw": per_mw,
        "scenarios": summaries,
    }
    (RESULTS / "peak_uncertainty.json").write_text(json.dumps(out, indent=2, default=float))
    return out


# ---------------------------------------------------------------- Falls Township fan (figures/falls_mc_fan)
FAN_SEED = 20260926
FAN_N_DRAWS = 2_000
FAN_N_PLOT = 300
FAN_FLOOR_GPD = 1_000.0
FAN_YEARS = (2005, 2024)
FAN_P_IT_RANGE = (253.0, None)      # upper end = primary calibration p_it_mw, read at run time
FAN_GAMMA_KEYS = ("alternative", "primary")   # gamma range between the design-rate and peak-day readings


def _falls_weather():
    """KTTN hourly wet-bulb with local (America/New_York) date, year, day of year, 2005-2024."""
    w, cal, _, _ = B.load_inputs("primary")
    t = pd.to_datetime(w.time_utc, utc=True).dt.tz_convert("America/New_York")
    x = pd.DataFrame({"twb": w.wetbulb_c.to_numpy(float), "date": t.dt.normalize().dt.tz_localize(None)})
    x = x[(x.date >= B.START) & (x.date <= B.END)].reset_index(drop=True)
    x["year"], x["doy"] = x.date.dt.year, x.date.dt.dayofyear
    return x, cal


def fan_parameters(cal_all: dict, n: int = FAN_N_DRAWS, seed: int = FAN_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = cal_all["primary"]
    g_lo, g_hi = sorted(cal_all[k]["gamma"] for k in FAN_GAMMA_KEYS)
    years = np.arange(FAN_YEARS[0], FAN_YEARS[1] + 1)
    return pd.DataFrame({
        "draw": np.arange(n),
        "p_it_mw": rng.uniform(FAN_P_IT_RANGE[0], p["p_it_mw"], n),
        "pue": rng.uniform(*PUE_RANGE, n),
        "gamma": rng.uniform(g_lo, g_hi, n),
        "t_sw_c": np.full(n, p["t_sw_c"]),
        "cycles": np.full(n, p["cycles"]),
        "twb_ref_c": np.full(n, p["twb_ref_c"]),
        "weather_year": rng.choice(years, n),
    })


def fan_daily(x: pd.DataFrame, P: pd.DataFrame, min_hours: int = 20) -> np.ndarray:
    """Draw x day-of-year (366) makeup in gal/day, NaN where the day is missing or has < min_hours valid hours.
    Same arithmetic as cooling_model.daily_makeup for the hybrid (mean of valid hours x 24)."""
    from .cooling_model import EVAP_GAL_PER_MWH
    out = np.full((len(P), 366), np.nan)
    by_year = {y: g for y, g in x.groupby("year")}
    for i, r in enumerate(P.itertuples()):
        g = by_year[int(r.weather_year)]
        twb = g.twb.to_numpy()
        doy = g.doy.to_numpy() - 1
        xx = np.clip((twb - r.t_sw_c) / (r.twb_ref_c - r.t_sw_c), 0.0, 1.0)
        phi = np.where(twb > r.t_sw_c, xx ** r.gamma, 0.0)
        gal = phi * r.p_it_mw * r.pue * EVAP_GAL_PER_MWH * r.cycles / (r.cycles - 1.0)
        ok = np.isfinite(twb)
        cnt = np.bincount(doy[ok], minlength=366)
        tot = np.bincount(doy[ok], weights=gal[ok], minlength=366)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[i] = np.where(cnt >= min_hours, tot / cnt * 24.0, np.nan)
    return out


def falls_fan(seed: int = FAN_SEED, n: int = FAN_N_DRAWS, n_plot: int = FAN_N_PLOT) -> dict:
    x, _ = _falls_weather()
    cal_all = json.loads((RESULTS / "calibration.json").read_text())
    P = fan_parameters(cal_all, n, seed)
    D = fan_daily(x, P)
    rng = np.random.default_rng(seed + 1)
    plot_idx = np.sort(rng.choice(n, n_plot, replace=False))
    with np.errstate(all="ignore"):
        q = np.nanquantile(D, [0.10, 0.50, 0.90], axis=0)
    valid = np.isfinite(D)
    zero = valid & (D == 0)
    Dp = D[plot_idx]
    vp = np.isfinite(Dp)
    peak = np.nanmax(D, axis=1)
    info = {
        "seed": seed, "plot_selection_seed": seed + 1, "n_draws": n, "n_plotted_traces": n_plot,
        "rng": "numpy.random.default_rng (PCG64)",
        "trace_definition": "each trace is one parameter draw run over one weather year drawn uniformly from "
                            "2005 to 2024 (KTTN hourly wet-bulb, America/New_York calendar days)",
        "architecture": "calibrated hybrid (results/calibration.json 'primary')",
        "distributions": {
            "p_it_mw": {"dist": "uniform", "low": FAN_P_IT_RANGE[0], "high": cal_all["primary"]["p_it_mw"],
                        "source": "253 MW unverified Keystone figure [cleanview_keystone_2026] to the peak-day "
                                  "calibration's fitted 331.19 MW [peakflow_model]"},
            "pue": {"dist": "uniform", "low": PUE_RANGE[0], "high": PUE_RANGE[1], "source": "shehabi_2024 p.48"},
            "gamma": {"dist": "uniform", "low": float(min(cal_all[k]["gamma"] for k in FAN_GAMMA_KEYS)),
                      "high": float(max(cal_all[k]["gamma"] for k in FAN_GAMMA_KEYS)),
                      "source": "design-rate and peak-day calibration readings [peakflow_model]"},
            "t_sw_c": {"dist": "fixed", "value": cal_all["primary"]["t_sw_c"],
                       "source": "identical in both calibration readings (set by the 6 percent wet-hour target)"},
            "cycles": {"dist": "fixed", "value": cal_all["primary"]["cycles"], "source": "model assumption"},
            "weather_year": {"dist": "discrete uniform", "values": list(range(FAN_YEARS[0], FAN_YEARS[1] + 1))},
        },
        "plot_floor_gpd": FAN_FLOOR_GPD,
        "share_zero_makeup_trace_days_all_draws": float(zero.sum() / valid.sum()),
        "share_zero_makeup_trace_days_plotted": float((vp & (Dp == 0)).sum() / vp.sum()),
        "share_trace_days_below_floor_plotted": float((vp & (Dp < FAN_FLOOR_GPD)).sum() / vp.sum()),
        "n_missing_trace_days_all_draws": int((~valid).sum()),
        "annual_max_day_gpd": {"p10": float(np.quantile(peak, 0.1)), "p50": float(np.quantile(peak, 0.5)),
                               "p90": float(np.quantile(peak, 0.9)), "max": float(peak.max())},
        "share_draws_max_day_over_trigger": float((peak > B.TRIGGER_GPD).mean()),
        "share_draws_max_day_over_4p4mgd": float((peak > 4.4e6).mean()),
        "doy_p50_max_gpd": float(np.nanmax(q[1])), "doy_p90_max_gpd": float(np.nanmax(q[2])),
        "n_doy_p50_positive": int((q[1] > 0).sum()), "n_doy_p90_positive": int((q[2] > 0).sum()),
        "reference_lines_gpd": {"drbc_trigger": B.TRIGGER_GPD, "reported_peak": 4.4e6},
    }
    (RESULTS / "falls_mc_fan.json").write_text(json.dumps(info, indent=2, default=float))
    return {"info": info, "params": P, "daily": D, "plot_idx": plot_idx, "q": q}


# ---------------------------------------------------------------- digitization (reproduces the constants)
def _render(page_index: int, scale: int = 8) -> np.ndarray:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(LBNL_PDF))
    return np.asarray(doc[page_index].render(scale=scale).to_pil().convert("RGB")).astype(int)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    idx = np.where(mask)[0]
    if not len(idx):
        return []
    br = np.where(np.diff(idx) > 3)[0]
    return list(zip(np.r_[idx[0], idx[br + 1]], np.r_[idx[br], idx[-1]]))


def digitize_figure_4_4(scale: int = 8) -> dict:
    """Five-number summaries for the WUE and PUE boxes of Figure 4.4 (PDF page 46), keyed by FIG44_ROWS."""
    img = _render(45, scale)
    H, W, _ = img.shape
    dark = img.sum(axis=2) < 200
    colored = (img.max(axis=2) - img.min(axis=2)) > 60
    gray = (np.abs(img[:, :, 0] - img[:, :, 1]) < 8) & (img[:, :, 0] > 200) & (img[:, :, 0] < 240)
    frames = [c for c in _runs(dark[int(0.08 * H):int(0.57 * H)].sum(axis=0) > 0.15 * H)]
    (pl, pr), (wl, wr) = (frames[0][1] + 1, frames[1][0] - 1), (frames[2][1] + 1, frames[3][0] - 1)
    rows = _runs(dark[:, wl + 130:wr - 70].sum(axis=1) > 0.8 * (wr - wl - 200))
    top, bot = (rows[0][0] + rows[0][1]) / 2, (rows[-1][0] + rows[-1][1]) / 2
    sp = (bot - top) / len(FIG44_ROWS)
    out = {}
    for panel, (x0, x1), vals in (("wue", (wl, wr), (0.0, 4.0)), ("pue", (pl, pr), (1.0, 2.5))):
        g = _runs(gray[int(top) + 20:int(bot) - 20, x0:x1].sum(axis=0) > 0.5 * (bot - top - 40))
        c = [x0 + (a + b) / 2 for a, b in g]
        a_px, b_px = c[0], c[-1]
        to_v = lambda x, a_px=a_px, b_px=b_px, vals=vals: vals[0] + (x - a_px) * (vals[1] - vals[0]) / (b_px - a_px)
        res = {}
        for a, b in _runs(colored[int(top):int(bot), x0 + 2:x1 - 2].any(axis=1)):
            a, b = a + int(top), b + int(top)
            if b - a < 35:
                continue
            r = int(((a + b) / 2 - top) // sp)
            yc = (a + b) // 2
            cc = np.where(colored[a:b + 1, x0 + 2:x1 - 2].any(axis=0))[0] + x0 + 2
            dc = np.where(dark[yc - 2:yc + 3, x0 + 6:x1 - 6].any(axis=0))[0] + x0 + 6
            inner = dark[a + 5:b - 5, cc.min():cc.max() + 1].sum(axis=0)
            med = [k + cc.min() for k in np.where(inner > 0.8 * (b - a - 10))[0] if 8 < k < cc.max() - cc.min() - 8]
            res[FIG44_ROWS[r]] = (to_v(dc.min()), to_v(cc.min()), to_v(np.mean(med)) if med else np.nan,
                                  to_v(cc.max()), to_v(dc.max()))
        out[panel] = res
    return out


def digitize_figure_4_2(scale: int = 8) -> dict:
    """Percent shares of the hyperscale and midsize/colo bars of Figure 4.2 (PDF page 39)."""
    img = _render(38, scale)
    H, W, _ = img.shape
    dark = img.sum(axis=2) < 200
    rows = _runs(dark[:, int(0.18 * W):int(0.57 * W)].sum(axis=1) > 0.3 * W)
    y0, y1 = (rows[0][0] + rows[0][1]) / 2, (rows[1][0] + rows[1][1]) / 2
    colors = {(214, 39, 40): "airside_econ_adiabatic_acc", (255, 152, 150): "airside_econ_adiabatic_wcc",
              (255, 127, 14): "airside_econ_acc", (255, 187, 120): "airside_econ_wcc",
              (199, 199, 199): "direct_expansion", (44, 160, 44): "dry_cooler_acc",
              (152, 223, 138): "dry_cooler_adiabatic_acc", (31, 119, 180): "water_cooled_chiller",
              (174, 199, 232): "waterside_econ_wcc", (197, 176, 213): "air_cooled_chiller"}
    ref = np.array(list(colors))
    out = {}
    for bar, xf in (("midsize_colo", 398 / 1224), ("hyperscale", 518 / 1224)):
        col = img[int(y0) + 2:int(y1) - 1, int(xf * W)]
        d = np.abs(col[:, None, :] - ref[None, :, :]).sum(axis=2)
        lab = np.where(d.min(axis=1) < 45, d.argmin(axis=1), -1)
        sh = {}
        for j, name in enumerate(colors.values()):
            sh[name] = float((lab == j).sum() / (y1 - y0) * 100)
        out[bar] = sh
    return out


if __name__ == "__main__":
    r = run()
    p = r["scenarios"]["primary"]
    print(json.dumps({k: p[k] for k in ("per_mw_peak_day_gpd", "n_covers_p50", "n_covers_p90",
                                         "n_deterministic_matchable", "class_changes_at_p90", "bin_changes_at_p90",
                                         "hybrid_draws_capped_share")}, indent=1, default=float))
