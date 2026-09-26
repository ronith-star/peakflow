"""EPA ECHO / ICIS-NPDES: major wastewater permittees in Delaware River Basin counties and their DMRs.

Selection logic (every excluded record is written to results/exclusions.csv):
  1. ECHO CWA facility search, NPDES individual permits flagged Major, states PA, NJ, DE, NY.
  2. Keep facilities whose county intersects the DRB boundary (WBD HUC6 020401 + 020402).
  3. Keep publicly owned treatment works (CWPFacilityTypeIndicator == "POTW"); non-POTW majors
     (power plants, refineries, industrial dischargers) are not municipal effluent sources.
  4. Keep facilities whose screening flow exceeds 1 MGD. Screening flow is the ECHO design flow; when that is
     null it falls back to the ECHO actual average flow, then the past-calendar-year average flow, then the
     median monthly DMR flow in the window (flow_basis records which was used). Records with no flow from any
     source are excluded as "null design flow and no fallback flow"; others as "screening flow 1 MGD or less".
  5. Keep facilities located inside the DRB boundary (reuse from outside would be an inter-basin transfer).
DMR window: 36 monitoring months, 2023-07-01 to 2026-06-30.
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely import make_valid

from .paths import PROCESSED, RAW, log_exclusions, record_download

ECHO = "https://echodata.epa.gov/echo"
STATES = {"PA": "42", "NJ": "34", "DE": "10", "NY": "36"}
QCOLUMNS = "1,2,12,13,14,19,24,25,26,27,28,29,51,54,60,97,148,159,162"
DMR_START = "07/01/2023"
DMR_END = "06/30/2026"
DMR_WINDOW = ("2023-07-01", "2026-06-30")

# ICIS parameter codes for the chemistry requested (value reported as monthly average concentration)
CHEM = {
    "tss_mg_l": ["00530"],
    "bod_mg_l": ["00310", "80082"],  # BOD5 or CBOD5
    "nh3_n_mg_l": ["00610"],
    "total_p_mg_l": ["00665"],
    "chloride_mg_l": ["00940"],
    "tds_mg_l": ["70295", "70300"],
    "silica_mg_l": ["00955"],
}
FLOW_CODE = "50050"

RAW_ECHO = RAW / "echo"
RAW_DMR = RAW_ECHO / "dmr"


def majors_url(st: str) -> str:
    return f"{ECHO}/cwa_rest_services.get_facilities?output=JSON&p_st={st}&p_maj=Y&p_ptype=NPD"


def download_majors(force: bool = False) -> None:
    """Majors facility CSV per state (get_facilities -> get_download). Cached files are reused unless force."""
    RAW_ECHO.mkdir(parents=True, exist_ok=True)
    for st in STATES:
        url = majors_url(st)
        out = RAW_ECHO / f"majors_{st}.csv"
        if not force and out.exists() and out.stat().st_size > 0:
            continue
        qid = requests.get(url, timeout=180).json()["Results"]["QueryID"]
        dl = f"{ECHO}/cwa_rest_services.get_download?qid={qid}&output=CSV&qcolumns={QCOLUMNS}"
        r = requests.get(dl, timeout=300)
        r.raise_for_status()
        out.write_bytes(r.content)
        record_download(out, url + " -> get_download (qcolumns " + QCOLUMNS + ")")


def drb_counties(boundary: gpd.GeoDataFrame, counties: gpd.GeoDataFrame) -> pd.DataFrame:
    c = counties.to_crs(5070).copy()
    c["geometry"] = c.geometry.apply(make_valid)
    b = make_valid(boundary.to_crs(5070).union_all())
    c["frac_in_drb"] = c.geometry.intersection(b).area / c.area
    c = c[c.frac_in_drb > 0]
    c["cty_key"] = c.STATE + "|" + c.NAME.str.upper().str.replace(" COUNTY", "", regex=False).str.strip()
    return c[["GEOID", "NAME", "STATE", "frac_in_drb", "cty_key"]]


def select_permittees(boundary: gpd.GeoDataFrame, counties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    m = pd.concat(
        [pd.read_csv(RAW_ECHO / f"majors_{s}.csv", encoding="latin-1", dtype={"FacDerivedHuc": str}).assign(state=s) for s in STATES],
        ignore_index=True,
    )
    dc = drb_counties(boundary, counties)
    cty_name = m.FacStdCountyName.fillna(m.CWPCounty.fillna("").str.upper() + " COUNTY")
    m["cty_key"] = m.state.map(STATES) + "|" + cty_name.str.upper().str.replace(" COUNTY", "", regex=False).str.strip()
    excl = []

    def drop(mask, reason):
        nonlocal m
        for _, r in m[mask].iterrows():
            excl.append({"record_id": r.SourceID, "record_name": r.CWPName, "reason": reason})
        m = m[~mask]

    drop(~m.cty_key.isin(dc.cty_key), "county does not intersect the DRB")
    n_county = len(m)
    m = m.copy()
    num = lambda c: pd.to_numeric(m[c], errors="coerce")
    design, actual, past = num("CWPTotalDesignFlowNmbr"), num("CWPActualAverageFlowNmbr"), num("PastCalYrAverageFlow")
    dmr_med = m.SourceID.map(lambda pid: _dmr_median_flow(pid))
    m["screening_flow_mgd"] = design.where(design.notna(), actual.where(actual.notna(), past.where(past.notna(), dmr_med)))
    m["flow_basis"] = np.select([design.notna(), actual.notna(), past.notna(), dmr_med.notna()],
                                ["design_flow", "actual_avg_flow", "past_cal_yr_avg_flow", "dmr_median_flow"], "none")
    drop(m.screening_flow_mgd.isna(), "null design flow and no fallback flow (actual, past-year or DMR)")
    drop(~(m.screening_flow_mgd > 1), "screening flow 1 MGD or less")
    log_exclusions("echo_permittees", excl)
    # All remaining majors are retained. Facility type, permit status and basin location are flags,
    # not filters; the supply screen applies its own documented eligibility rule (supply_screen.py).
    g = gpd.GeoDataFrame(m, geometry=gpd.points_from_xy(m.FacLong, m.FacLat), crs=4326)
    g["in_drb"] = g.within(make_valid(boundary.to_crs(4326).union_all()))
    g["is_potw"] = g.CWPFacilityTypeIndicator.eq("POTW")
    m = g
    g = m.rename(
        columns={
            "SourceID": "npdes_id", "CWPName": "name", "FacLat": "lat", "FacLong": "lon",
            "CWPTotalDesignFlowNmbr": "design_flow_mgd", "CWPActualAverageFlowNmbr": "actual_avg_flow_mgd",
            "PastCalYrAverageFlow": "past_cal_yr_avg_flow_mgd", "CWPPermitStatusDesc": "permit_status",
            "FacStdCountyName": "county", "CWPStateWaterBodyName": "receiving_water",
            "CWPFacilityTypeIndicator": "facility_type",
        }
    )
    keep = ["npdes_id", "name", "state", "county", "lat", "lon", "facility_type", "is_potw", "in_drb",
            "design_flow_mgd", "actual_avg_flow_mgd", "past_cal_yr_avg_flow_mgd", "screening_flow_mgd", "flow_basis",
            "permit_status", "receiving_water", "geometry"]
    g = g[keep].reset_index(drop=True)
    g.attrs["n_major_in_drb_counties"] = n_county
    return g


def _dmr_median_flow(pid: str) -> float:
    """Median monthly DMR effluent flow (MGD) from a cached DMR file, or NaN."""
    d = _read_dmr(RAW_DMR / f"{pid}.csv")
    if d.empty:
        return np.nan
    s = monthly_flow(d)
    return float(s.median()) if len(s) else np.nan


def null_design_ids(boundary: gpd.GeoDataFrame, counties: gpd.GeoDataFrame) -> list[str]:
    """NPDES ids in DRB counties whose design flow is null (DMRs are fetched for these so the fallback can use them)."""
    m = pd.concat([pd.read_csv(RAW_ECHO / f"majors_{s}.csv", encoding="latin-1", dtype={"FacDerivedHuc": str}).assign(state=s)
                   for s in STATES], ignore_index=True)
    dc = drb_counties(boundary, counties)
    cty_name = m.FacStdCountyName.fillna(m.CWPCounty.fillna("").str.upper() + " COUNTY")
    key = m.state.map(STATES) + "|" + cty_name.str.upper().str.replace(" COUNTY", "", regex=False).str.strip()
    m = m[key.isin(dc.cty_key) & pd.to_numeric(m.CWPTotalDesignFlowNmbr, errors="coerce").isna()]
    return list(m.SourceID)


def download_dmrs(npdes_ids: list[str], sleep: float = 0.3) -> None:
    RAW_DMR.mkdir(parents=True, exist_ok=True)
    for pid in npdes_ids:
        out = RAW_DMR / f"{pid}.csv"
        if out.exists() and out.stat().st_size > 0:
            continue
        url = f"{ECHO}/eff_rest_services.download_effluent_chart?p_id={pid}&start_date={DMR_START}&end_date={DMR_END}"
        for attempt in range(4):
            try:
                r = requests.get(url, timeout=300)
                r.raise_for_status()
                out.write_bytes(r.content)
                record_download(out, url)
                break
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))
        time.sleep(sleep)


def _read_dmr(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    d = pd.read_csv(path, encoding="latin-1", dtype=str, low_memory=False)
    if d.empty:
        return d
    d["value"] = pd.to_numeric(d.dmr_value_standard_units, errors="coerce")
    d["period_end"] = pd.to_datetime(d.monitoring_period_end_date, format="%m/%d/%Y", errors="coerce")
    lo, hi = pd.Timestamp(DMR_WINDOW[0]), pd.Timestamp(DMR_WINDOW[1])
    d = d[(d.period_end >= lo) & (d.period_end <= hi)]
    # one value per DMR value id (rows repeat across limit sets)
    return d.drop_duplicates("dmr_value_id")


def monthly_flow(d: pd.DataFrame) -> pd.Series:
    """Monthly-average effluent flow (MGD), summed over external outfalls, per monitoring month.
    The statistic is "MO AVG"; permits that report no MO AVG flow but report "DAILY AV" (the monthly average of
    daily values, used in Delaware permits such as DE0020320) use DAILY AV instead."""
    base = d[(d.parameter_code == FLOW_CODE) & (d.standard_unit_desc == "MGD")
             & (d.monitoring_location_desc == "Effluent Gross") & (d.perm_feature_type_code == "EXO")].dropna(subset=["value"])
    f = base[base.statistical_base_short_desc == "MO AVG"]
    if f.empty:
        f = base[base.statistical_base_short_desc == "DAILY AV"]
    if f.empty:
        return pd.Series(dtype=float)
    f = f.assign(month=f.period_end.dt.to_period("M"))
    per_outfall = f.groupby(["month", "perm_feature_nmbr"]).value.max()
    return per_outfall.groupby("month").sum()


def chem_medians(d: pd.DataFrame) -> dict:
    """Median of monthly effluent concentrations (mg/L) per chemistry column in CHEM.
    Uses the "MO AVG" statistic; for a parameter with no MO AVG values, "DAILY AV" (the monthly average of daily
    values reported by Delaware permits such as DE0020320) is used instead, as in monthly_flow."""
    out = {}
    base = d[(d.monitoring_location_desc == "Effluent Gross") & (d.standard_unit_desc == "mg/L")]
    for col, codes in CHEM.items():
        pv = base[base.parameter_code.isin(codes)].dropna(subset=["value"])
        v = pv[pv.statistical_base_short_desc == "MO AVG"]
        if v.empty:
            v = pv[pv.statistical_base_short_desc == "DAILY AV"]
        # one value per monitoring month: mean across external outfalls / parameter variants
        per_month = v.groupby(v.period_end.dt.to_period("M")).value.mean()
        out[col] = float(per_month.median()) if len(per_month) else np.nan
        out[col.replace("_mg_l", "_n_months")] = int(len(per_month))
    return out


def summarize(permittees: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    rows, monthly = [], []
    for pid in permittees.npdes_id:
        d = _read_dmr(RAW_DMR / f"{pid}.csv")
        s = monthly_flow(d) if not d.empty else pd.Series(dtype=float)
        rec = {"npdes_id": pid, "dmr_flow_months": int(len(s)),
               "median_flow_mgd": float(s.median()) if len(s) else np.nan,
               "p10_flow_mgd": float(s.quantile(0.1)) if len(s) else np.nan,
               "min_flow_mgd": float(s.min()) if len(s) else np.nan,
               "max_flow_mgd": float(s.max()) if len(s) else np.nan}
        rec.update(chem_medians(d) if not d.empty else {})
        rows.append(rec)
        if len(s):
            monthly.append(pd.DataFrame({"npdes_id": pid, "month": s.index.astype(str), "flow_mgd": s.values}))
    summ = permittees.merge(pd.DataFrame(rows), on="npdes_id", how="left")
    return summ, (pd.concat(monthly) if monthly else pd.DataFrame())


def run(download: bool = True) -> gpd.GeoDataFrame:
    boundary = gpd.read_file(PROCESSED / "drb_boundary.geojson")
    counties = gpd.read_file(RAW / "gis" / "counties_pa_nj_de_ny.geojson")
    if download:
        download_majors()
    if download:
        download_dmrs(null_design_ids(boundary, counties))
    perm = select_permittees(boundary, counties)
    if download:
        download_dmrs(list(perm.npdes_id))
    summ, monthly = summarize(perm)
    no_flow = summ[summ.dmr_flow_months == 0]
    log_exclusions("echo_no_dmr_flow", [
        {"record_id": r.npdes_id, "record_name": r.name,
         "reason": "no monthly-average effluent flow DMR in 2023-07 to 2026-06; kept in permittee list, excluded from supply screen"}
        for r in no_flow.itertuples()])
    summ.attrs = perm.attrs
    summ.to_file(PROCESSED / "wwtp_majors.geojson", driver="GeoJSON")
    pd.DataFrame(summ.drop(columns="geometry")).to_csv(PROCESSED / "wwtp_majors.csv", index=False)
    monthly.to_csv(PROCESSED / "wwtp_monthly_flow.csv", index=False)
    return summ


if __name__ == "__main__":
    run()
