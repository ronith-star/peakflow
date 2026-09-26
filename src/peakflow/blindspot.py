"""Deliverable A: two DRBC review blind spots for data center cooling water.

(a) Averaging blind spot. A withdrawal project is excluded from Commission review when "the daily
    average gross withdrawal during any 30 consecutive day period does not exceed 100,000 gallons"
    [drbc_admin_manual: DRBC Administrative Manual Part 1, Article 3; 18 CFR 401.35(a)(2)-(3)]. A
    configuration whose maximum 30-day average is <= 100,000 gal/day is therefore excluded even if single
    days far exceed 100,000 gal.
(b) Purchased-supply blind spot. The thresholds apply to a project's own withdrawal; a data center that
    buys water from an existing public or authority system is not itself a withdrawal project, so no review
    is triggered regardless of size [drbc_datacenters_2026; drbc_admin_manual].
Cooling makeup is treated as gross withdrawal (no credit for return flow).

Grid: IT load {50, 100, 200, 400} MW x {evaporative_tower, hybrid, air_cooled_chiller}; PUE 1.2,
cycles of concentration 4; the hybrid's T_sw, gamma and Twb_ref are read at run time from
results/calibration.json (key path CALIBRATIONS[name]); IT load is set by the grid, not by the calibration.
A Falls Township (AWS Keystone) reference row carries the reported average and peak [falls_levittown_2026;
falls_herald_2026] and the modeled maximum 30-day average from the primary calibration diagnostics.
Climate: KTTN hourly wet-bulb, 2005-2024; daily makeup on America/New_York calendar days via
cooling_model.daily_makeup; days with < 20 valid hours are NaN. The analysis keeps local days
2005-01-01..2024-12-31 (the UTC record's ragged local-day edges fall outside or become NaN).

30-day rolling average: trailing 30 calendar days, mean of the valid days, computed when >= 27 of the
30 days are valid (>= 90 %). Requiring all 30 valid would drop 13.5 % of windows, including the
July-August 2011 heat-wave window that sets the record maximum, so the all-30 rule is reported only as a
sensitivity column (r30_max_gpd_all30).
Flow context: Trenton daily mean flow (USGS 01463500) on the same calendar date, compared with its
day-of-year p25 over 2005-2024 and with the full-record LP3 7Q10 (results/flow_stats.json).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .cooling_model import CoolingParams, daily_makeup
from .paths import PROCESSED, RESULTS

TRIGGER_GPD = 100_000.0
MW_GRID = (50, 100, 200, 400)
ARCHS = ("evaporative_tower", "hybrid", "air_cooled_chiller")
ARCH_LABEL = {"evaporative_tower": "Evaporative tower", "hybrid": "Hybrid (calibrated)",
              "air_cooled_chiller": "Air-cooled chiller"}
PUE, CYCLES = 1.2, 4.0
START, END = pd.Timestamp("2005-01-01"), pd.Timestamp("2024-12-31")
N_YEARS = END.year - START.year + 1
WINDOW_DAYS = 30
WINDOW_MIN_VALID = 27


CALIBRATIONS = {"primary": ("primary",), "wet_2pct": ("sensitivity_wet_2pct", "peak_day")}
RAW_FILES = {"primary": "blindspot_raw.csv", "wet_2pct": "blindspot_raw_wet2pct.csv"}
DISPLAY_FILES = {"primary": "table_blindspot.csv", "wet_2pct": "table_blindspot_wet2pct.csv"}


def load_calibration(name: str = "primary") -> dict:
    c = json.loads((RESULTS / "calibration.json").read_text())
    for k in CALIBRATIONS[name]:
        c = c[k]
    return c


def load_inputs(name: str = "primary"):
    w = pd.read_parquet(PROCESSED / "weather_hourly.parquet")
    w = w[w.station == "KTTN"].reset_index(drop=True)
    cal = load_calibration(name)
    fs = json.loads((RESULTS / "flow_stats.json").read_text())
    q7q10 = fs["seven_q_ten"]["primary_full_record"]["value_cfs"]
    fl = pd.read_parquet(PROCESSED / "flow_daily.parquet")[["date", "flow_cfs", "p25_2005_2024"]]
    fl = fl.set_index("date")
    return w, cal, q7q10, fl


def config_params(mw: float, arch: str, cal: dict) -> CoolingParams:
    return CoolingParams(p_it_mw=float(mw), pue=PUE, cycles=CYCLES, t_sw_c=cal["t_sw_c"], gamma=cal["gamma"],
                         twb_ref_c=cal["twb_ref_c"], architecture=arch)


def daily_series(w: pd.DataFrame, p: CoolingParams) -> pd.Series:
    d = daily_makeup(w, p).makeup_gpd
    return d.reindex(pd.date_range(START, END, freq="D"))


def summarize(d: pd.Series, flow: pd.DataFrame, q7q10: float) -> dict:
    r30 = d.rolling(WINDOW_DAYS, min_periods=WINDOW_MIN_VALID).mean()
    r30_all = d.rolling(WINDOW_DAYS, min_periods=WINDOW_DAYS).mean()
    annual_mean = d.groupby(d.index.year).mean()
    r30_annual = r30.groupby(r30.index.year).mean()
    over = d > TRIGGER_GPD
    f = flow.reindex(d.index)
    of = f[over.to_numpy()]
    n_over = int(over.sum())
    n_over_flow = int(of.flow_cfs.notna().sum())
    return {
        "annual_mean_gpd": float(annual_mean.mean()),
        "max_annual_mean_gpd": float(annual_mean.max()),
        "r30_annual_mean_gpd": float(r30_annual.mean()),
        "r30_max_gpd": float(r30.max()),
        "r30_max_end_date": r30.idxmax().date().isoformat() if r30.notna().any() else "",
        "r30_max_gpd_all30": float(r30_all.max()),
        "below_trigger_30day_all30": bool(r30_all.max() <= TRIGGER_GPD),
        "peak_day_p99_gpd": float(d.quantile(0.99)),
        "peak_day_max_gpd": float(d.max()),
        "peak_day_max_date": d.idxmax().date().isoformat(),
        "below_trigger_30day": bool(r30.max() <= TRIGGER_GPD),
        "above_trigger_peak_day": bool(d.max() > TRIGGER_GPD),
        "days_over_trigger_total": n_over,
        "valid_years_daily": float(d.notna().sum() / 365.25),
        "days_per_year_over_trigger": n_over / float(d.notna().sum() / 365.25),
        "days_30day_window_over_trigger_total": int((r30 > TRIGGER_GPD).sum()),
        "valid_years_30day_windows": float(r30.notna().sum() / 365.25),
        "days_per_year_30day_window_over_trigger": float((r30 > TRIGGER_GPD).sum() / (r30.notna().sum() / 365.25)),
        "share_over_days_flow_below_doy_p25": (float((of.flow_cfs < of.p25_2005_2024).sum() / n_over_flow)
                                               if n_over_flow else np.nan),
        "share_over_days_flow_below_7q10": (float((of.flow_cfs < q7q10).sum() / n_over_flow)
                                            if n_over_flow else np.nan),
        "n_nan_days": int(d.isna().sum()),
        "n_valid_30day_windows": int(r30.notna().sum()),
        "n_valid_30day_windows_all30": int(r30_all.notna().sum()),
    }


def run(name: str = "primary") -> pd.DataFrame:
    w, cal, q7q10, flow = load_inputs(name)
    rows = []
    for mw in MW_GRID:
        for arch in ARCHS:
            d = daily_series(w, config_params(mw, arch, cal))
            rows.append({"it_load_mw": mw, "architecture": arch, **summarize(d, flow, q7q10)})
    t = pd.DataFrame(rows)
    t["blind_spot_strict"] = t.below_trigger_30day & t.above_trigger_peak_day
    t["blind_spot_loose"] = (t.annual_mean_gpd < TRIGGER_GPD) & t.above_trigger_peak_day
    t["review_if_self_supplied"] = ~t.below_trigger_30day
    t["review_if_purchased"] = False
    t["calibration"] = name
    for k in ("t_sw_c", "gamma", "twb_ref_c"):
        t[f"hybrid_{k}"] = cal[k]
    t.attrs.update({"q7q10_cfs": q7q10, "calibration": name})
    t.to_csv(RESULTS / RAW_FILES[name], index=False)
    return t


def counts(t: pd.DataFrame) -> dict:
    lo, hi = hybrid_blindspot_band(t)
    return {"n_configs": int(len(t)),
            "n_averaging_blind_spot_strict": int(t.blind_spot_strict.sum()),
            "n_averaging_blind_spot_loose_annual_mean": int(t.blind_spot_loose.sum()),
            "n_review_if_self_supplied": int(t.review_if_self_supplied.sum()),
            "n_review_if_purchased": int(t.review_if_purchased.sum()),
            "n_purchased_supply_blind_spot": int((t.review_if_self_supplied & ~t.review_if_purchased).sum()),
            "hybrid_strict_band_mw": [lo, hi] if lo < hi else None,
            "n_nan_days": int(t.n_nan_days.iloc[0])}


def hybrid_blindspot_band(t: pd.DataFrame) -> tuple[float, float]:
    """IT-load band (MW) in which the calibrated hybrid is below the 30-day threshold yet above it on its
    maximum day. Makeup is exactly proportional to IT load at fixed PUE, cycles and climate, so the band
    follows from any grid row: lower = trigger / (max day per MW), upper = trigger / (max 30-day avg per MW)."""
    h = t[t.architecture == "hybrid"].iloc[0]
    return (TRIGGER_GPD * h.it_load_mw / h.peak_day_max_gpd, TRIGGER_GPD * h.it_load_mw / h.r30_max_gpd)


# ----------------------------------------------------------------------------- display
def sig3(x: float, suffix: str = "") -> str:
    """Three significant figures with thousands separators; exact zero prints as '0'; NaN as 'n/a'."""
    if pd.isna(x):
        return "n/a"
    if x == 0:
        return "0" + suffix
    v = float(f"{x:.3g}")
    digits = 3 - 1 - int(np.floor(np.log10(abs(v))))
    return f"{v:,.{max(digits, 0)}f}{suffix}"


# Footnote markers: 1 model-derived; 2 DRBC 30-day rule; 3 USGS streamflow; 4 reported Falls values;
# 5 purchased-supply exclusion.
FN_MODEL, FN_DRBC, FN_USGS, FN_FALLS, FN_BUY = "\u00b9", "\u00b2", "\u00b3", "\u2074", "\u2075"
# (csv/md header, figure header line 1, figure header line 2, alignment)
DISPLAY_COLUMNS = [
    ("IT load (MW)", "IT load", "(MW)", "right"),
    ("Configuration", "Configuration", "", "left"),
    (f"30-day avg, annual mean (gal/d){FN_MODEL}", "30-day avg,", f"annual mean (gal/d){FN_MODEL}", "right"),
    (f"30-day avg, max (gal/d){FN_MODEL}", "30-day avg,", f"max (gal/d){FN_MODEL}", "right"),
    (f"Peak day p99 (gal/d){FN_MODEL}", "Peak day", f"p99 (gal/d){FN_MODEL}", "right"),
    (f"Peak day max (gal/d){FN_MODEL}", "Peak day", f"max (gal/d){FN_MODEL}", "right"),
    (f"Below trigger on 30-day avg{FN_DRBC}", "Below trigger", f"on 30-day avg{FN_DRBC}", "center"),
    (f"Days/yr, 30-day avg > 100,000 gal/d{FN_DRBC}", "Days/yr, 30-day", f"avg > 100,000{FN_DRBC}", "right"),
    (f"Days/yr, single day > 100,000 gal (not the trigger test){FN_MODEL}", "Days/yr, single", f"day > 100,000{FN_MODEL}", "right"),
    (f"Of those, flow < DOY p25{FN_USGS}", "Of those,", f"flow < DOY p25{FN_USGS}", "right"),
    (f"Of those, flow < 7Q10{FN_USGS}", "Of those,", f"flow < 7Q10{FN_USGS}", "right"),
    (f"Review if self-supplied{FN_DRBC}", "Review if", f"self-supplied{FN_DRBC}", "center"),
    (f"Review if purchased from an existing system{FN_BUY}", "Review if purchased", f"from existing system{FN_BUY}",
     "center"),
]
SHADE_COL = "Shaded (averaging blind spot)"
FALLS_LABEL = "Falls Twp (AWS Keystone), reported"
KEYS_MODEL = ["noaa_isd", "stull_2011", "alduchov_1996"]
KEYS_ALL = ["drbc_admin_manual", "drbc_datacenters_2026", "usgs_nwis_01463500", "falls_levittown_2026",
            "falls_herald_2026", *KEYS_MODEL]
RULE_CITE = "DRBC Administrative Manual Part 1, Article 3; 18 CFR 401.35(a)(2)-(3)"
RULE_QUOTE = "the daily average gross withdrawal during any 30 consecutive day period does not exceed 100,000 gallons"
DRBC_DC_QUOTE = ("To date, the DRBC has not received any applications for data center projects because the "
                 "existing data centers in the Basin purchase water from public water supply systems rather than "
                 "operate their own withdrawal systems.")
MORRISVILLE_ALLOCATION_MGD = 243  # reported by LevittownNow [falls_levittown_2026]; not model-derived
YN = {True: "Yes", False: "No"}


def falls_row() -> dict:
    """Reference row: reported average and peak (sourced), modeled max 30-day average (primary calibration)."""
    p = load_calibration("primary")
    tg, dg = p["targets"], p["diagnostics"]
    vals = ["n/a", FALLS_LABEL, sig3(tg["avg_gpd"]) + FN_FALLS, sig3(dg["max_30day_avg_gpd"]) + FN_MODEL, "n/a",
            sig3(tg["peak_gpd"]) + FN_FALLS, YN[dg["max_30day_avg_gpd"] <= TRIGGER_GPD], "n/a", "n/a", "n/a", "n/a",
            YN[dg["max_30day_avg_gpd"] > TRIGGER_GPD], "No"]
    assert len(vals) == len(DISPLAY_COLUMNS)
    row = {c[0]: v for c, v in zip(DISPLAY_COLUMNS, vals)}
    row[SHADE_COL] = "No"
    return row


def display_frame(t: pd.DataFrame, with_falls: bool = True) -> pd.DataFrame:
    """The single source of displayed strings for the CSVs, the Markdown table and the PNG/PDF."""
    vals = [
        t.it_load_mw.map(lambda v: f"{v:,}"),
        t.architecture.map(ARCH_LABEL),
        t.r30_annual_mean_gpd.map(sig3),
        t.r30_max_gpd.map(sig3),
        t.peak_day_p99_gpd.map(sig3),
        t.peak_day_max_gpd.map(sig3),
        t.below_trigger_30day.map(YN),
        t.days_per_year_30day_window_over_trigger.map(sig3),
        t.days_per_year_over_trigger.map(sig3),
        t.share_over_days_flow_below_doy_p25.map(lambda v: sig3(100 * v, "%")),
        t.share_over_days_flow_below_7q10.map(lambda v: sig3(100 * v, "%")),
        t.review_if_self_supplied.map(YN),
        t.review_if_purchased.map(YN),
    ]
    df = pd.DataFrame({c[0]: v.to_numpy() for c, v in zip(DISPLAY_COLUMNS, vals)})
    df[SHADE_COL] = t.blind_spot_strict.map(YN).to_numpy()
    if with_falls:
        df = pd.concat([df, pd.DataFrame([falls_row()])], ignore_index=True)
    return df


def headline(t: pd.DataFrame) -> str:
    c = counts(t)
    return (f"{c['n_averaging_blind_spot_strict']} of {c['n_configs']} configurations escape DRBC review by "
            f"averaging, and all {c['n_purchased_supply_blind_spot']} that would trigger it escape if they buy "
            "water from an existing system")


SUBTITLE = ("Modeled daily cooling makeup compared with the DRBC review threshold of 100,000 gal/day, "
            "averaged over any 30 consecutive days")


def footnotes(t: pd.DataFrame) -> list[str]:
    q = t.attrs["q7q10_cfs"]
    c = counts(t)
    n_days = len(pd.date_range(START, END))
    cal_path = "results/calibration.json " + "/".join(CALIBRATIONS[t.attrs["calibration"]])
    return [
        (("Shaded rows are" if c["n_averaging_blind_spot_strict"] else "Shading would mark") +
         " the averaging blind spot: below the threshold on every 30-day average but above "
         "100,000 gal on at least one day" +
         ("." if c["n_averaging_blind_spot_strict"] else "; no configuration in the grid qualifies.") +
         f" Under a looser annual-mean test, "
         f"{c['n_averaging_blind_spot_loose_annual_mean']} of {c['n_configs']} configurations would qualify. "
         "The Falls row is a reference and is not counted."),
        (f"{FN_MODEL} Model-derived: PUE 1.2, 4 cycles of concentration, hybrid parameters from {cal_path}, "
         f"KTTN hourly wet-bulb 2005-2024 [noaa_isd; stull_2011; alduchov_1996]. Makeup is treated as gross "
         f"withdrawal. {c['n_nan_days']} of {n_days:,} local days are missing, and 30-day windows require at "
         "least 27 valid days."),
        (f"{FN_DRBC} A withdrawal is excluded from review when {RULE_QUOTE} [drbc_admin_manual] ({RULE_CITE}). "
         "Days/yr, 30-day avg counts days whose trailing 30-day average exceeds 100,000 gal/d (the trigger test); "
         "Days/yr, single day counts days whose own makeup exceeds 100,000 gal and is not the trigger test. Both "
         "are divided by the number of valid years (valid days or valid windows / 365.25)."),
        (f"{FN_USGS} Delaware River at Trenton daily mean flow on days above 100,000 gal, compared with its "
         f"2005-2024 day-of-year 25th percentile and the full-record LP3 7Q10 of {q:,.0f} cfs [usgs_nwis_01463500]."),
        (f"{FN_FALLS} Reported: average cooling service water 135,000 gal/day [falls_levittown_2026] and peak "
         "4.4 million gal/day [falls_levittown_2026; falls_herald_2026]."),
        (f"{FN_BUY} The thresholds apply to a project's own withdrawal, so a data center that buys water from an "
         "existing public or authority system is not itself reviewed [drbc_datacenters_2026; drbc_admin_manual]. "
         "Falls is supplied by the Morrisville Municipal Authority service-water system, whose allocation is "
         f"reported as {MORRISVILLE_ALLOCATION_MGD} million gal/day [falls_levittown_2026]."),
    ]


def write_tables(t: pd.DataFrame) -> pd.DataFrame:
    from .paths import FIGURES

    df = display_frame(t)
    df.to_csv(RESULTS / DISPLAY_FILES[t.attrs["calibration"]], index=False)
    if t.attrs["calibration"] == "primary":
        df.to_csv(FIGURES / "table_blindspot_data.csv", index=False)
    return df


def write_markdown(t: pd.DataFrame) -> str:
    df = display_frame(t)
    cols = [c[0] for c in DISPLAY_COLUMNS]
    align = {c[0]: c[3] for c in DISPLAY_COLUMNS}
    sep = {"right": "---:", "left": ":---", "center": ":---:"}
    lines = [f"**{headline(t)}**", "", SUBTITLE + ".", "",
             "| " + " | ".join(cols) + " |",
             "| " + " | ".join(sep[align[c]] for c in cols) + " |"]
    for i in range(len(df)):
        cells = [df[c].iloc[i] for c in cols]
        if df[SHADE_COL].iloc[i] == "Yes":
            cells = [f"**{c}**" for c in cells]
        lines.append("| " + " | ".join(cells) + " |")
    notes = footnotes(t)
    notes[0] = notes[0].replace("Shaded rows are", "Bold rows (shaded in the figure) are").replace(
        "Shading would mark", "Bold type (shading in the figure) would mark")
    lines += [""] + [n + "  " for n in notes] + ["", "Sources: " + "; ".join(f"[{k}]" for k in KEYS_ALL) + ".", ""]
    txt = "\n".join(lines)
    (RESULTS / "table_blindspot.md").write_text(txt)
    return txt


def _describe(rows: pd.DataFrame) -> str:
    """One sentence per configuration, giving its maximum day and highest 30-day average."""
    return " ".join(f"The {ARCH_LABEL[r.architecture].lower()} at {r.it_load_mw} MW has a maximum day of "
                    f"{sig3(r.peak_day_max_gpd)} gal and a highest 30-day average of {sig3(r.r30_max_gpd)} gal/d."
                    for r in rows.itertuples())


def write_caption(t: pd.DataFrame, t_wet: pd.DataFrame | None = None) -> str:
    from .paths import FIGURES

    q = t.attrs["q7q10_cfs"]
    c = counts(t)
    strict, loose = t[t.blind_spot_strict], t[t.blind_spot_loose]
    p = load_calibration("primary")
    if len(strict):
        strict_txt = f"Under this strict test, {len(strict)} of 12 configurations qualify. {_describe(strict)}"
    else:
        strict_txt = ("Under this strict test, no configuration in the grid qualifies, because every configuration "
                      "that exceeds 100,000 gal on its maximum day also exceeds the threshold on at least one 30-day "
                      "average.")
    loose_txt = (f"Under a looser test that compares the annual mean with 100,000 gal/day, {len(loose)} of 12 would "
                 "qualify." + (f" {_describe(loose)}" if len(loose) else ""))
    band = c["hybrid_strict_band_mw"]
    band_txt = (f"Because modeled makeup is proportional to IT load, the calibrated hybrid would fall in the "
                f"averaging blind spot only for IT loads between {sig3(band[0])} MW and {sig3(band[1])} MW, which "
                "lie below the tabulated grid." if band else
                "The calibrated hybrid has no IT-load band that falls in the averaging blind spot.")
    wet_txt = ""
    if t_wet is not None:
        cw = counts(t_wet)
        wet_txt = (f" The wet-share sensitivity calibration sets evaporative operation on about 2 % of hours, and that "
                   f"fit cannot reach the 135,000 gal/day average. Under that calibration, the averaging blind spot "
                   f"contains {cw['n_averaging_blind_spot_strict']} of 12 configurations and the purchased-supply "
                   f"blind spot contains {cw['n_purchased_supply_blind_spot']} of 12 "
                   f"(results/table_blindspot_wet2pct.csv).")
    ratio = p["targets"]["peak_gpd"] / p["targets"]["avg_gpd"]
    rule_cite = RULE_CITE.replace("; ", " and ")   # captions carry no semicolons
    keys_txt = ", ".join(KEYS_ALL[:-1]) + " and " + KEYS_ALL[-1]
    txt = f"""# Table A. Two DRBC review blind spots for data center cooling water

**Table A.**

{headline(t)}.

**Caption**

The table lists modeled daily cooling-water makeup for twelve data center configurations and a reference row for the Falls Township (AWS Keystone) project. The configurations combine four IT loads (50, 100, 200 and 400 MW) with three cooling architectures (evaporative tower, calibrated hybrid and air-cooled chiller). The table tests two mechanisms by which such demand can escape Delaware River Basin Commission review.

The first mechanism is an averaging blind spot. A withdrawal is excluded from review when "{RULE_QUOTE}" [drbc_admin_manual] ({rule_cite}). Shading would mark configurations that stay below the threshold on every 30-day average but exceed 100,000 gal on at least one day. {strict_txt} {loose_txt} {band_txt}

The second mechanism is a purchased-supply blind spot. The thresholds apply to a project's own withdrawal. A data center that buys water from an existing public or authority system is therefore not itself a withdrawal project, and no review is triggered regardless of size. The Commission states: "{DRBC_DC_QUOTE}" [drbc_datacenters_2026]. Of the twelve configurations, {c['n_review_if_self_supplied']} would require review if self-supplied. None would require review if the water is purchased, so the purchased-supply blind spot covers all {c['n_purchased_supply_blind_spot']}. The Falls project reports an average of 135,000 gal/day [falls_levittown_2026] and a peak of 4.4 million gal/day [falls_levittown_2026, falls_herald_2026], a peak-to-average ratio of {sig3(ratio)}. Its modeled maximum 30-day average is {sig3(p['diagnostics']['max_30day_avg_gpd'])} gal/day, so it would require review if self-supplied [calibration.json]. It is instead supplied by the Morrisville Municipal Authority service-water system, whose allocation is reported as {MORRISVILLE_ALLOCATION_MGD} million gal/day [falls_levittown_2026].{wet_txt}

The flow columns give, among days with makeup above 100,000 gal, the share on which Delaware River flow at Trenton (USGS 01463500) was below its 2005 to 2024 day-of-year 25th percentile or below the full-record 7Q10 of {q:,.0f} cfs [usgs_nwis_01463500]. All displayed values are rounded to three significant figures. Full-precision values are in results/blindspot_raw.csv.

**Assumptions**

1. All gallon values other than the two reported Falls values are model-derived and are not measurements. Makeup equals evaporation multiplied by C/(C-1), with 4 cycles of concentration and drift neglected. Heat rejected equals IT load multiplied by a PUE of 1.2, and the conversion to evaporation uses a latent heat of 2.43 MJ/kg.
2. The hybrid architecture uses the switchover wet-bulb temperature ({sig3(p['t_sw_c'])} C), part-load exponent ({sig3(p['gamma'])}) and reference wet-bulb temperature ({sig3(p['twb_ref_c'])} C) of the primary (peak-day) calibration in results/calibration.json. That calibration reproduces the reported Falls average, peak day and wet-operation share. With three parameters and three targets the fit is exactly determined, so this agreement is not validation. The IT load is set by the grid rather than by the calibrated value.
3. Climate is KTTN (Trenton-Mercer Airport) hourly data from 2005 to 2024 [noaa_isd]. It is converted to wet-bulb temperature with Stull (2011) [stull_2011], with relative humidity from the Magnus form [alduchov_1996]. Daily totals use America/New_York calendar days. Days with fewer than 20 valid hours are treated as missing ({c['n_nan_days']} of {len(pd.date_range(START, END)):,} days). A 30-day average is computed when at least 27 of its 30 days are valid.
4. Makeup is treated as gross withdrawal, with no credit for return flow. Whether a configuration is self-supplied or purchased is a scenario, not an observation, for every grid row.
5. The 7Q10 is a log-Pearson Type III fit by the method of moments to annual minimum 7-day mean flows for 113 complete climatic years (April to March, 1914 to 2026), using the unadjusted sample skew. Day-of-year percentiles use the 2005 to 2024 daily record.

The citation keys are {keys_txt}.
"""
    (FIGURES / "table_blindspot_caption.md").write_text(txt)
    return txt


# ----------------------------------------------------------------------------- figure
FOOTNOTE_WRAP = 250  # characters per footnote line at SMALL_SIZE across the table width
COL_GAP_IN = 0.16    # minimum gap between adjacent columns (inches)


def _layout(fig, ax, df, cols, sizes) -> list[float]:
    """Measure each column's widest string (header lines and cells) and place columns left to right with
    equal gaps filling the axes width. Returns the anchor x (axes fraction) for each column."""
    from matplotlib.textpath import TextPath  # noqa: F401  (ensures font machinery is initialized)

    r = fig.canvas.get_renderer()
    ax_w = ax.get_window_extent(r).width
    widths = []
    for j, (col, h1, h2, _) in enumerate(cols):
        ws = []
        for txt, size, weight in [(h1, sizes["small"], "bold"), (h2, sizes["small"], "normal")] + \
                [(v, sizes["body"], "normal") for v in df[col]]:
            if not txt:
                continue
            tt = ax.text(0, 0, txt, fontsize=size, fontweight=weight)
            ws.append(tt.get_window_extent(r).width / ax_w)
            tt.remove()
        widths.append(max(ws))
    gap = (1.0 - sum(widths)) / (len(cols) - 1)
    min_gap = COL_GAP_IN * fig.dpi / ax_w
    assert gap >= min_gap, f"table too wide: gap {gap:.4f} < {min_gap:.4f}; widen the figure"
    xs, cursor = [], 0.0
    for w_j, (_, _, _, al) in zip(widths, cols):
        xs.append({"left": cursor, "right": cursor + w_j, "center": cursor + w_j / 2}[al])
        cursor += w_j + gap
    return xs


def render_figure(t: pd.DataFrame, stem: str = "table_blindspot"):
    import textwrap

    import matplotlib.pyplot as plt

    from .paths import FIGURES
    from .styles import (ACCENT, BODY_SIZE, INK, MUTED, RULE, SMALL_SIZE, SUBTITLE_SIZE, TITLE_SIZE,
                         register_fonts, source_line)

    family = register_fonts()
    df = display_frame(t)
    n = len(df)
    fn_lines = [ln for fn in footnotes(t) for ln in textwrap.wrap(fn, width=FOOTNOTE_WRAP, subsequent_indent="   ")]
    fig_w = 13.0
    pt = 1 / 72
    row_in, head_in, fn_in = 0.29, 0.55, SMALL_SIZE * 1.55 * pt
    top_in, fn_gap_in, src_in = 0.75, 0.18, 0.40
    fig_h = top_in + head_in + row_in * n + 0.08 + fn_gap_in + fn_in * len(fn_lines) + src_in
    fig = plt.figure(figsize=(fig_w, fig_h))
    mx = 0.35 / fig_w
    ax = fig.add_axes([mx, 0, 1 - 2 * mx, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, fig_h)  # y in inches from the bottom
    xs = _layout(fig, ax, df, DISPLAY_COLUMNS, {"small": SMALL_SIZE, "body": BODY_SIZE})

    y = fig_h - 0.28
    ax.text(0.0, y, headline(t), ha="left", va="center", fontsize=TITLE_SIZE, fontweight="bold", color=INK)
    y -= 0.27
    ax.text(0.0, y, SUBTITLE + ".", ha="left", va="center", fontsize=SUBTITLE_SIZE, color=MUTED)
    y_rule_top = fig_h - top_in
    ax.plot([0, 1], [y_rule_top] * 2, color=RULE, lw=0.8, solid_capstyle="butt")
    y_head = y_rule_top - head_in / 2
    for (_, h1, h2, al), x in zip(DISPLAY_COLUMNS, xs):
        ax.text(x, y_head + 0.09, h1, ha=al, va="center", fontsize=SMALL_SIZE, color=MUTED, fontweight="normal")
        if h2:
            ax.text(x, y_head - 0.09, h2, ha=al, va="center", fontsize=SMALL_SIZE, color=MUTED)
    y_rule_head = y_rule_top - head_in
    ax.plot([0, 1], [y_rule_head] * 2, color=RULE, lw=0.8, solid_capstyle="butt")
    drawn = []
    for i in range(n):
        yc = y_rule_head - row_in * (i + 0.5)
        if df[SHADE_COL].iloc[i] == "Yes":
            ax.add_patch(plt.Rectangle((0, yc - row_in / 2), 1, row_in, facecolor=ACCENT, edgecolor="none", zorder=0))
        row = []
        for (col, _, _, al), x in zip(DISPLAY_COLUMNS, xs):
            ax.text(x, yc, df[col].iloc[i], ha=al, va="center", fontsize=BODY_SIZE, color=INK, zorder=2)
            row.append(df[col].iloc[i])
        drawn.append(row)
        if i < n - 1:
            nxt = df[DISPLAY_COLUMNS[0][0]].iloc[i + 1]
            if nxt != df[DISPLAY_COLUMNS[0][0]].iloc[i]:  # between IT-load groups and before the Falls row
                ax.plot([0, 1], [yc - row_in / 2] * 2, color=RULE, lw=0.5, solid_capstyle="butt", zorder=1)
    y_bottom = y_rule_head - row_in * n
    ax.plot([0, 1], [y_bottom] * 2, color=RULE, lw=0.8, solid_capstyle="butt")
    y_fn = y_bottom - fn_gap_in
    for ln in fn_lines:  # one Text per line so the bounds check measures each line
        ax.text(0.0, y_fn, ln, ha="left", va="top", fontsize=SMALL_SIZE, color=MUTED)
        y_fn -= fn_in
    source_line(fig, KEYS_ALL, extra="Model parameters: results/calibration.json.", y_in=0.14, x_in=mx * fig_w)
    FIGURES.mkdir(parents=True, exist_ok=True)
    from .falls_figures import text_boxes_check  # lazy: falls_figures imports this module

    chk = text_boxes_check(fig)  # QA gate H1: text-text, text-edge, text-line and text-symbol overlaps
    chk["pass"] = not any(chk[k] for k in ("text_text", "text_outside_figure", "text_line", "text_symbol"))
    if stem == "table_blindspot":
        (RESULTS / f"{stem}_check.json").write_text(json.dumps({"figure": f"figures/{stem}", **chk}, indent=1,
                                                               default=str))
    # G5 outputs png/pdf/svg for the published stem; test stems write png/pdf only (the test removes those two)
    for ext in ("png", "pdf", "svg") if stem == "table_blindspot" else ("png", "pdf"):
        fig.savefig(FIGURES / f"{stem}.{ext}", dpi=300, facecolor="white")
    fig._drawn_cells = drawn
    fig._check = chk
    return fig, family


BRIEF_ROWS = [("FALLS", None), ("BAND", "Hybrid (calibrated)"), ("100", "Hybrid (calibrated)"),
              ("400", "Hybrid (calibrated)"), ("100", "Evaporative tower"), ("100", "Air-cooled chiller")]
BRIEF_BAND_MW = 15   # inside the hybrid averaging band (results/blindspot_summary.json hybrid_strict_band_mw)


def _sig3(v):
    return f"{float(f'{v:.3g}'):,.0f}"


def write_brief_table():
    """Brief-size extract of the primary table: at most 6 rows and 5 columns. The peak-day and 30-day columns
    show mechanism (a), averaging; the two review columns show mechanism (b), purchased supply. Values are
    copied from results/table_blindspot.csv, so the extract cannot drift from the full table."""
    full = pd.read_csv(RESULTS / "table_blindspot.csv", dtype=str, keep_default_na=False)
    cols = list(full.columns)
    c30 = next(c for c in cols if c.startswith("30-day avg, max"))
    cpk = next(c for c in cols if c.startswith("Peak day max"))
    cself = next(c for c in cols if c.startswith("Review if self-supplied"))
    cbuy = next(c for c in cols if c.startswith("Review if purchased"))
    raw = pd.read_csv(RESULTS / "blindspot_raw.csv")
    rows = []
    for mw, arch in BRIEF_ROWS:
        if mw == "FALLS":
            rows.append(full[full["Configuration"] == FALLS_LABEL].iloc[0])
            continue
        if mw == "BAND":
            # Makeup is linear in IT load, so the band row is the 100 MW hybrid scaled; checked against 50 MW.
            h = raw[raw.architecture == "hybrid"].set_index("it_load_mw")
            for c in ("r30_max_gpd", "peak_day_max_gpd"):
                assert abs(h.loc[50, c] * 2 - h.loc[100, c]) <= 1e-6 * h.loc[100, c], c
            summ = json.loads((RESULTS / "blindspot_summary.json").read_text())["primary"]
            lo, hi = summ["hybrid_strict_band_mw"]
            assert lo < BRIEF_BAND_MW < hi
            f = BRIEF_BAND_MW / 100.0
            r30, pk = h.loc[100, "r30_max_gpd"] * f, h.loc[100, "peak_day_max_gpd"] * f
            assert r30 <= TRIGGER_GPD < pk
            rows.append(pd.Series({"IT load (MW)": str(BRIEF_BAND_MW), "Configuration": arch,
                                   c30: _sig3(r30) + "¹", cpk: _sig3(pk) + "¹", cself: "No", cbuy: "No"}))
            continue
        r = full[(full["IT load (MW)"] == mw) & (full["Configuration"] == arch)]
        assert len(r) == 1, (mw, arch)
        rows.append(r.iloc[0])
    out = pd.DataFrame([{
        "Configuration": (f"{r['Configuration']}, {r['IT load (MW)']} MW" if r["IT load (MW)"] != "n/a"
                          else "Falls Twp (AWS Keystone), reported"),
        "Max 30-day average (gal/d)": r[c30],
        "Peak day (gal/d)": r[cpk],
        "DRBC review if self-supplied": r[cself],
        "DRBC review if purchased": r[cbuy],
    } for r in rows])
    assert out.shape[0] <= 6 and out.shape[1] <= 5
    out.to_csv(RESULTS / "table_blindspot_brief.csv", index=False)
    notes = ("Notes for results/table_blindspot_brief.csv. Except for the 15 MW hybrid row, rows and cells are copied from results/table_blindspot.csv "
             "(primary calibration); footnote marks are kept. The review trigger is a daily average gross withdrawal "
             "above 100,000 gallons over any 30 consecutive days [drbc_admin_manual]; a project that buys water "
             "from an existing public or authority system is not itself reviewed [drbc_datacenters_2026]. "
             f"The {BRIEF_BAND_MW} MW hybrid row is the 100 MW hybrid scaled linearly (makeup is proportional to "
             f"IT load); it lies inside the averaging band of {lo:.2f} to {hi:.1f} MW, where every 30-day average is "
             "below the trigger but the peak day exceeds 100,000 gallons [peakflow_model]. "
             "Modeled values are [peakflow_model]; Falls values are reported [falls_levittown_2026; "
             "falls_herald_2026], except the maximum 30-day average, which is modeled.\n")
    (RESULTS / "table_blindspot_brief_notes.md").write_text(notes)
    return out


def main():
    tabs = {name: run(name) for name in CALIBRATIONS}
    summary = {}
    for name, tab in tabs.items():
        write_tables(tab)
        cal = load_calibration(name)
        summary[name] = {**counts(tab), "calibration_key_path": list(CALIBRATIONS[name]),
                         "calibration_targets": cal["targets"],
                         "calibration_feasible": cal.get("all_three_feasible_within_1pct"),
                         "infeasibility_note": cal.get("infeasibility_note", ""),
                         "hybrid_params": {k: cal[k] for k in ("t_sw_c", "gamma", "twb_ref_c")},
                         "display_file": f"results/{DISPLAY_FILES[name]}", "raw_file": f"results/{RAW_FILES[name]}"}
    summary["q7q10_cfs"] = tabs["primary"].attrs["q7q10_cfs"]
    summary["trigger_rule"] = {"quote": RULE_QUOTE, "citation": RULE_CITE, "key": "drbc_admin_manual"}
    summary["purchased_supply"] = {"quote": DRBC_DC_QUOTE, "key": "drbc_datacenters_2026",
                                   "url": "https://www.nj.gov/drbc/programs/supply/datacenters.html"}
    (RESULTS / "blindspot_summary.json").write_text(json.dumps(summary, indent=2))
    write_markdown(tabs["primary"])
    write_brief_table()
    write_caption(tabs["primary"], tabs["wet_2pct"])
    fig, family = render_figure(tabs["primary"])
    return tabs, fig, family


if __name__ == "__main__":
    _tabs, _fig, _family = main()
    print((RESULTS / "table_blindspot.md").read_text())
    print("font:", _family)
