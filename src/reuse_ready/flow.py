"""Delaware River at Trenton (USGS 01463500) low-flow statistics and DRBC drought-action table.

Inputs
  data/raw/usgs/dv_01463500.rdb  USGS NWIS daily values, parameter 00060 (discharge, cfs), statistic
                                 00003 (daily mean), TS_ID 97504 [usgs_nwis_01463500].
  https://www.nj.gov/drbc/programs/flow/drbc-drought.html  "Dates of DRBC-Declared Basinwide Drought
                                 Actions" table [drbc_drought_page].

Methods
  7Q10: the annual minimum of the 7-day moving-average flow is taken per climatic year (1 April to
  31 March, labelled by the calendar year in which it ends, USGS convention). 7-day windows lie wholly
  inside the climatic year and require 7 non-missing days. Only complete climatic years (every day
  present) are used. The 10-year recurrence (non-exceedance probability 0.1) is estimated with a
  log-Pearson Type III distribution fitted by the method of moments on log10 annual minima (mean,
  standard deviation, unadjusted sample skew; no regional-skew weighting, no low-outlier test) - a
  simplified Bulletin-17B-style fit, stated as such in results.md. The empirical value is the Weibull
  plotting-position (i / (n + 1)) 0.1 quantile of the same annual minima.
  Day-of-year percentiles: p10/p25/p50 of daily mean flow for each calendar month-day, over (a) the
  full record and (b) the 2005-2024 analysis window. Feb 29 is pooled with Feb 28 and Mar 1 values
  because it has few observations.
  Provisional ('P') values are kept and flagged; they occur only at the end of the record.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .paths import PROCESSED, RAW, RESULTS, USER_AGENT, record_download

RDB = RAW / "usgs" / "dv_01463500.rdb"
RDB_URL = ("https://waterservices.usgs.gov/nwis/dv/?format=rdb&sites=01463500&parameterCd=00060"
           "&statCd=00003&startDT=1900-01-01&siteStatus=all")
Q_COL = "97504_00060_00003"
DROUGHT_URL = "https://www.nj.gov/drbc/programs/flow/drbc-drought.html"
DROUGHT_HTML = RAW / "drbc" / "drbc-drought.html"
WINDOW = (2005, 2024)
DROUGHT_COLS = ["enter_watch", "enter_warning", "end_watch_warning", "enter_drought",
                "declare_emergency", "end_emergency"]


# ----------------------------------------------------------------------------- daily flow
def rdb_retrieved_utc(path: Path = RDB):
    """UTC retrieval timestamp from the RDB header line '# retrieved: YYYY-MM-DD HH:MM:SS -04:00'."""
    import datetime as dt

    with open(path, errors="ignore") as fh:
        for ln in fh:
            m = re.match(r"#\s*retrieved:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([+-]\d{2}:\d{2})", ln)
            if m:
                return dt.datetime.fromisoformat(f"{m.group(1)}{m.group(2)}").astimezone(dt.timezone.utc)
            if not ln.startswith("#"):
                break
    return None


def record_rdb(path: Path = RDB) -> None:
    when = rdb_retrieved_utc(path)
    note = "downloaded_utc taken from the RDB '# retrieved' header" if when else "recorded from existing file"
    record_download(path, RDB_URL, when=when, note=note)


def read_rdb(path: Path = RDB) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", comment="#", dtype=str)
    df = df.iloc[1:]  # drop the RDB column-format row (5s 15s 20d ...)
    out = pd.DataFrame({
        "date": pd.to_datetime(df["datetime"]),
        "flow_cfs": pd.to_numeric(df[Q_COL], errors="coerce"),
        "qual_cd": df[Q_COL + "_cd"].fillna(""),
    })
    out["provisional"] = out.qual_cd.str.startswith("P")
    out["estimated"] = out.qual_cd.str.contains(":e", regex=False)
    out["climatic_year"] = out.date.dt.year + (out.date.dt.month >= 4).astype(int)
    out["month_day"] = out.date.dt.strftime("%m-%d")
    return out.sort_values("date").reset_index(drop=True)


def annual_7day_minima(q: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cy, g in q.groupby("climatic_year"):
        start, end = pd.Timestamp(cy - 1, 4, 1), pd.Timestamp(cy, 3, 31)
        n_expected = (end - start).days + 1
        g = g.set_index("date").reindex(pd.date_range(start, end, freq="D"))
        n_valid = int(g.flow_cfs.notna().sum())
        r7 = g.flow_cfs.rolling(7, min_periods=7).mean()
        rows.append({"climatic_year": int(cy), "n_days": n_valid, "complete": n_valid == n_expected,
                     "n_provisional": int(g.provisional.fillna(False).astype(bool).sum()),
                     "min7_cfs": float(r7.min()) if r7.notna().any() else np.nan,
                     "min7_end_date": r7.idxmin().date().isoformat() if r7.notna().any() else None})
    return pd.DataFrame(rows)


def lp3_quantile(x: np.ndarray, p: float = 0.1) -> dict:
    y = np.log10(np.asarray(x, float))
    m, s, g = float(y.mean()), float(y.std(ddof=1)), float(stats.skew(y, bias=False))
    k = float(stats.pearson3.ppf(p, g))  # standardized frequency factor
    return {"value_cfs": float(10 ** (m + k * s)), "log10_mean": m, "log10_sd": s, "log10_skew": g,
            "frequency_factor_K": k, "n_years": int(len(y))}


def empirical_quantile(x: np.ndarray, p: float = 0.1) -> float:
    return float(np.quantile(np.asarray(x, float), p, method="weibull"))


def seven_q_ten(mins: pd.DataFrame, first: int | None = None, last: int | None = None) -> dict:
    sel = mins[mins.complete & mins.min7_cfs.notna()]
    if first is not None:
        sel = sel[sel.climatic_year >= first]
    if last is not None:
        sel = sel[sel.climatic_year <= last]
    x = sel.min7_cfs.to_numpy()
    out = lp3_quantile(x)
    out.update({"empirical_weibull_cfs": empirical_quantile(x),
                "first_climatic_year": int(sel.climatic_year.min()),
                "last_climatic_year": int(sel.climatic_year.max()),
                "provisional_days_in_years_used": int(sel.n_provisional.sum())})
    return out


def doy_percentiles(q: pd.DataFrame, years: tuple[int, int] | None = None) -> pd.DataFrame:
    d = q[q.flow_cfs.notna()]
    if years is not None:
        d = d[(d.date.dt.year >= years[0]) & (d.date.dt.year <= years[1])]
    keys = sorted(d.month_day.unique())
    rows = []
    for k in keys:
        pool = [k] if k != "02-29" else ["02-28", "02-29", "03-01"]
        v = d.loc[d.month_day.isin(pool), "flow_cfs"].to_numpy()
        rows.append({"month_day": k, "n": len(v), "p10": np.percentile(v, 10), "p25": np.percentile(v, 25),
                     "p50": np.percentile(v, 50)})
    return pd.DataFrame(rows)


def flow_with_percentiles(q: pd.DataFrame) -> pd.DataFrame:
    full = doy_percentiles(q).rename(columns={c: f"{c}_full" for c in ("n", "p10", "p25", "p50")})
    win = doy_percentiles(q, WINDOW).rename(columns={c: f"{c}_2005_2024" for c in ("n", "p10", "p25", "p50")})
    return q.merge(full, on="month_day", how="left").merge(win, on="month_day", how="left")


# ----------------------------------------------------------------------------- DRBC drought table
def fetch_drought_page(path: Path = DROUGHT_HTML) -> Path:
    import requests

    path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(DROUGHT_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    record_download(path, DROUGHT_URL)
    return path


def _clean(cell: str) -> str:
    s = re.sub(r"<[^>]+>", "", cell).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def _iso(date_text: str) -> str:
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", date_text)
    if not m:
        return date_text
    mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yr < 100:
        yr += 1900 if yr >= 50 else 2000  # table spans the 1960s-2010s; '01'/'02' are 2001/2002
    return f"{yr:04d}-{mo:02d}-{dy:02d}"


def parse_drought_table(html: str) -> pd.DataFrame:
    """Rows carrying a decade label (first cell like '1980s', possibly rowspan) have label + up to 6
    action cells; continuation rows under a rowspan omit the label, so their cells are shifted one
    column left relative to labelled rows. Several rows in the source HTML also omit trailing empty
    cells, so cells are assigned left to right starting at enter_watch and missing trailing cells are
    blank. 'Conditional' annotations are moved to `notes`; '--' is kept in its cell and explained in
    `notes` using the page's footnote 2."""
    tables = re.findall(r"<table.*?</table>", html, re.S | re.I)
    assert len(tables) == 1, f"expected one table, found {len(tables)}"
    trs = re.findall(r"<tr.*?</tr>", tables[0], re.S | re.I)
    rows, period = [], None
    for tr in trs[1:]:  # first row is the header
        cells = [_clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S | re.I)]
        labelled = bool(cells) and re.fullmatch(r"\d{4}s", cells[0]) is not None
        if labelled:
            period, cells = cells[0], cells[1:]
        assert len(cells) <= 6, cells
        cells = cells + [""] * (6 - len(cells))
        rec = {"period": period, "period_label_in_row": labelled}
        notes = []
        for col, val in zip(DROUGHT_COLS, cells):
            if "Conditional" in val:
                val = val.replace("Conditional", "").strip()
                notes.append(f"{col}: Conditional")
            if val == "--":
                notes.append(f"{col}: '--' = basin returned to normal operations before drought warning "
                             "operations were triggered (page footnote 2)")
            rec[col] = _iso(val) if val else ""
        rec["notes"] = "; ".join(notes)
        rows.append(rec)
    return pd.DataFrame(rows, columns=["period", "period_label_in_row", *DROUGHT_COLS, "notes"])


# ----------------------------------------------------------------------------- driver
def run(fetch: bool = True) -> dict:
    record_rdb()
    q = read_rdb()
    daily = flow_with_percentiles(q)
    daily.to_parquet(PROCESSED / "flow_daily.parquet", index=False)

    mins = annual_7day_minima(q)
    mins.to_csv(RESULTS / "flow_annual_7day_minima.csv", index=False)
    primary = seven_q_ten(mins)
    window = seven_q_ten(mins, first=WINDOW[0] + 1, last=WINDOW[1])
    # Approved data only: drop every climatic year (Apr 1-Mar 31, labelled by ending year) that contains a
    # provisional day. The first provisional day falls in March 2025, so this ends at climatic year 2024.
    first_prov = q.loc[q.provisional, "date"].min()
    last_approved_cy = (first_prov.year if first_prov.month >= 4 else first_prov.year - 1)
    approved = seven_q_ten(mins, last=int(last_approved_cy))

    win = doy_percentiles(q, WINDOW)
    full = doy_percentiles(q)
    stats_out = {
        "site": "USGS 01463500 Delaware River at Trenton NJ",
        "source_file": "data/raw/usgs/dv_01463500.rdb",
        "record": {"first_date": q.date.min().date().isoformat(), "last_date": q.date.max().date().isoformat(),
                   "n_days": int(q.flow_cfs.notna().sum()),
                   "n_provisional": int(q.provisional.sum()), "n_estimated": int(q.estimated.sum()),
                   "first_provisional_date": q.loc[q.provisional, "date"].min().date().isoformat()},
        "seven_q_ten": {
            "method": ("log-Pearson Type III, method of moments on log10 annual minimum 7-day mean flow, "
                       "unadjusted sample skew, no regional skew or low-outlier screening; climatic years "
                       "Apr 1-Mar 31 labelled by ending year; complete years only"),
            "primary_full_record": primary,
            "sensitivity_cy2006_2024": window,
            "sensitivity_approved_only": approved,
            "n_complete_years": int(mins.complete.sum()),
            "incomplete_years": mins.loc[~mins.complete, "climatic_year"].astype(int).tolist(),
        },
        "doy_percentiles": {
            "method": "p10/p25/p50 of daily mean flow by calendar month-day; Feb 29 pooled with Feb 28 and Mar 1",
            "full_record_years": [int(q.date.dt.year.min()), int(q.date.dt.year.max())],
            "window_years": list(WINDOW),
            "annual_median_of_doy_p25_cfs": {"full_record": float(full.p25.median()),
                                             "window_2005_2024": float(win.p25.median())},
            "min_of_doy_p25_cfs": {"full_record": float(full.p25.min()), "window_2005_2024": float(win.p25.min())},
            "blindspot_basis": "window_2005_2024",
        },
    }
    if fetch or not DROUGHT_HTML.exists():
        fetch_drought_page()
    dr = parse_drought_table(DROUGHT_HTML.read_text(encoding="utf-8", errors="replace"))
    dr.to_csv(PROCESSED / "drbc_drought_actions.csv", index=False)
    stats_out["drbc_drought_actions"] = {"rows": int(len(dr)), "file": "data/processed/drbc_drought_actions.csv",
                                         "source_url": DROUGHT_URL}
    (RESULTS / "flow_stats.json").write_text(json.dumps(stats_out, indent=2))
    return stats_out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
