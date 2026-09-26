"""NOAA Integrated Surface Database (ISD, global-hourly) for KTTN and KPHL [noaa_isd].

Analysis window: 20 complete calendar years, 2005-01-01 to 2024-12-31 (UTC). The NCEI
global-hourly access files for 2025 end in August 2025 at download time, so 2025 is
downloaded for provenance but excluded from the window (logged in results/exclusions.csv).

Hourly series: one whole report is selected per clock hour (UTC). Reports with both valid
temperature and dew point are preferred; among those a routine METAR (FM-15) is preferred over a
special (FM-16), then the earliest in the hour. All fields for the hour come from that single
report. `hours_from_fm16` counts hours whose selected report is an FM-16. Values with ISD quality codes
other than 0, 1, 4, 5, 9 or with missing sentinels (+9999, 99999) are set to missing.
No interpolation is performed; missing hours stay missing and are counted.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import requests

from .paths import PROCESSED, RAW, log_exclusions, record_download
from .wetbulb import rh_from_dewpoint, stull_wetbulb

STATIONS = {
    "KTTN": {"usaf_wban": "72409514792", "name": "Trenton Mercer Airport, NJ"},
    "KPHL": {"usaf_wban": "72408013739", "name": "Philadelphia International Airport, PA"},
}
YEARS_DOWNLOAD = range(2005, 2026)
YEARS = range(2005, 2025)
URL = "https://www.ncei.noaa.gov/data/global-hourly/access/{y}/{id}.csv"
GOOD_Q = set("01459")
RAW_ISD = RAW / "isd"


def download() -> None:
    RAW_ISD.mkdir(parents=True, exist_ok=True)
    for st in STATIONS.values():
        for y in YEARS_DOWNLOAD:
            out = RAW_ISD / f"{st['usaf_wban']}_{y}.csv"
            url = URL.format(y=y, id=st["usaf_wban"])
            if not (out.exists() and out.stat().st_size > 0):
                r = requests.get(url, timeout=600)
                r.raise_for_status()
                out.write_bytes(r.content)
                time.sleep(0.5)
            record_download(out, url)


def _parse(field: pd.Series, scale: float, missing: str) -> pd.Series:
    s = field.fillna("").astype(str)
    val = s.str.split(",").str[0]
    q = s.str.split(",").str[1].fillna("")
    out = pd.to_numeric(val, errors="coerce") / scale
    bad = (val.str.lstrip("+") == missing.lstrip("+")) | ~q.isin(GOOD_Q)
    return out.mask(bad)


def load_station(code: str) -> tuple[pd.DataFrame, dict]:
    sid = STATIONS[code]["usaf_wban"]
    frames = []
    for y in YEARS:
        d = pd.read_csv(RAW_ISD / f"{sid}_{y}.csv", usecols=["DATE", "REPORT_TYPE", "TMP", "DEW", "SLP", "MA1"], dtype=str)
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["REPORT_TYPE"] = d.REPORT_TYPE.str.strip()
    d = d[d.REPORT_TYPE.isin(["FM-15", "FM-16"])].copy()
    d["time"] = pd.to_datetime(d.DATE, utc=True)
    d["hour"] = d.time.dt.floor("h")
    d["t_c"] = _parse(d.TMP, 10.0, "+9999")
    d["td_c"] = _parse(d.DEW, 10.0, "+9999")
    d["slp_hpa"] = _parse(d.SLP, 10.0, "99999")
    d["stn_p_hpa"] = _parse(d.MA1.fillna("").str.split(",").str[2:4].str.join(","), 10.0, "99999")
    # One whole report per hour: prefer a report with valid T and Td; among those prefer FM-15, then
    # the earliest in the hour. All fields for that hour come from the same report.
    d["pri"] = (d.REPORT_TYPE != "FM-15").astype(int)
    d["incomplete"] = (d.t_c.isna() | d.td_c.isna()).astype(int)
    d = d.dropna(subset=["t_c", "td_c"], how="all").sort_values(["hour", "incomplete", "pri", "time"])
    h = d.drop_duplicates("hour", keep="first").set_index("hour")[["t_c", "td_c", "slp_hpa", "stn_p_hpa", "REPORT_TYPE"]]
    full = pd.date_range(f"{YEARS[0]}-01-01", f"{YEARS[-1]}-12-31 23:00", freq="h", tz="UTC")
    h = h.reindex(full)
    h.index.name = "time_utc"
    h["rh_pct"] = rh_from_dewpoint(h.t_c, h.td_c)
    h["wetbulb_c"] = stull_wetbulb(h.t_c, h.rh_pct)
    h["station"] = code
    comp = {
        "station": code,
        "hours_expected": int(len(full)),
        "hours_missing_temp": int(h.t_c.isna().sum()),
        "hours_missing_dewpoint": int(h.td_c.isna().sum()),
        "hours_missing_wetbulb": int(h.wetbulb_c.isna().sum()),
        "hours_missing_pressure": int(h.stn_p_hpa.isna().sum()),
        "frac_missing_wetbulb": float(h.wetbulb_c.isna().mean()),
        "hours_from_fm16": int((h.REPORT_TYPE == "FM-16").sum()),
    }
    return h.reset_index(), comp


def run(download_first: bool = True) -> pd.DataFrame:
    if download_first:
        download()
    out, comps = [], []
    for code in STATIONS:
        h, c = load_station(code)
        out.append(h)
        comps.append(c)
    w = pd.concat(out, ignore_index=True)
    w.to_parquet(PROCESSED / "weather_hourly.parquet", index=False)
    pd.DataFrame(comps).to_csv(PROCESSED / "weather_completeness.csv", index=False)
    log_exclusions("weather", [
        {"record_id": f"{v['usaf_wban']}_2025", "record_name": f"{k} 2025",
         "reason": "incomplete calendar year in NCEI global-hourly at download (ends Aug 2025); outside 2005-2024 window"}
        for k, v in STATIONS.items()])
    return w


if __name__ == "__main__":
    run()
