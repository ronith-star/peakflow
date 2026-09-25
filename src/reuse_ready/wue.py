"""Average site WUE implied by the Falls Township cooling average, compared with published figures.

WUE (Green Grid definition [greengrid_wue_2011]) = annual site water (L) / IT energy (kWh).
Implied WUE = average cooling water (gal/day) x 3.785411784 L/gal / (P_IT MW x 24 h x 1000 kWh/MWh).
The cooling average (135,000 gal/day) is [falls_levittown_2026]; P_IT is the fitted value in
results/calibration.json (inferred, not sourced; primary = peak-day reading) and the unverified 253 MW
third-party figure. The wet-2% sensitivity uses its achieved average, not the 135,000 gal/day target.
Comparators are exact figures from opened sources; see sources.md.
"""
from __future__ import annotations

import json

from .paths import RESULTS

L_PER_GAL = 3.785411784
COMPARATORS = {
    "lbnl_2024_us_average_site_wue_through_2023": {
        "value": 0.36, "key": "shehabi_2024", "note": "average site WUE 'stays just over 0.36 L/kWh through 2023' (p.48)"},
    "lbnl_2024_hyperscale_aggregate_median": {"value": 0.32, "key": "shehabi_2024", "note": "p.47"},
    "lbnl_2024_airside_econ_adiabatic_reported": {
        "range": [0.1, 0.3], "key": "shehabi_2024",
        "note": "hyperscale facilities report 0.1-0.3 L/kWh for systems similar to airside economizer with adiabatic "
                "cooling; LBNL's simulated values for that system are lower because it is not used most of the year (p.46-47)"},
    "microsoft_fy2025_global_wue": {"value": 0.27, "key": "microsoft_datacenters_2025"},
    "meta_2024_wue_withdrawal_basis": {
        "value": 0.19, "key": "meta_sustainability_2025", "note": "withdrawal-based, not directly comparable"},
}


def implied(avg_gpd: float, p_it_mw: float) -> float:
    return avg_gpd * L_PER_GAL / (p_it_mw * 24_000.0)


def run() -> dict:
    cal = json.loads((RESULTS / "calibration.json").read_text())
    avg = cal["primary"]["targets"]["avg_gpd"]
    assert cal["primary"]["interpretation"] == "peak_day" and cal["alternative"]["interpretation"] == "design_rate"
    w2 = cal["sensitivity_wet_2pct"]["peak_day"]
    # (P_IT, average used). The wet-2% case uses its ACHIEVED average: its fit cannot reach 135,000 gal/day
    # under the design-rate reading, and under the peak-day reading it reaches the average at a larger P_IT.
    cases = {
        "peak_day_fit_primary": (cal["primary"]["p_it_mw"], avg),
        "design_rate_fit_sensitivity": (cal["alternative"]["p_it_mw"], avg),
        "wet_2pct_peak_day_achieved_avg": (w2["p_it_mw"], w2["achieved"]["avg_gpd"]),
        "wet_2pct_design_rate_achieved_avg": (cal["sensitivity_wet_2pct"]["design_rate"]["p_it_mw"],
                                              cal["sensitivity_wet_2pct"]["design_rate"]["achieved"]["avg_gpd"]),
        "unverified_253MW": (cal["sensitivity_fixed_p_it"]["p_it_mw"], avg),
    }
    wue = {k: {"p_it_mw": v, "avg_gpd_used": a, "implied_wue_l_per_kwh": implied(a, v)} for k, (v, a) in cases.items()}
    lo, hi = COMPARATORS["lbnl_2024_airside_econ_adiabatic_reported"]["range"]
    ratios = {k: {"lbnl_avg_over_falls": 0.36 / w["implied_wue_l_per_kwh"],
                  "microsoft_over_falls": 0.27 / w["implied_wue_l_per_kwh"],
                  "adiabatic_low_end_over_falls": lo / w["implied_wue_l_per_kwh"],
                  "inside_adiabatic_reported_range": lo <= w["implied_wue_l_per_kwh"] <= hi}
              for k, w in wue.items()}
    pk = cal["primary"]["targets"]["peak_gpd"]
    out = {
        "formula": "WUE = avg cooling gal/day x 3.785411784 L/gal / (P_IT MW x 24 h x 1000 kWh/MWh)",
        "avg_cooling_gpd": avg, "avg_source": "falls_levittown_2026",
        "potable_gpd_not_cooling": cal.get("potable_demand_gpd"),
        "peak_gpd": pk, "peak_to_average_ratio": pk / avg,
        "implied": wue, "ratios": ratios, "comparators": COMPARATORS,
    }
    (RESULTS / "falls_implied_wue.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    r = run()
    print({k: round(v["implied_wue_l_per_kwh"], 4) for k, v in r["implied"].items()}, round(r["peak_to_average_ratio"], 1))
    print({k: {a: (round(b, 2) if isinstance(b, float) else b) for a, b in v.items()} for k, v in r["ratios"].items()})
