"""Water Quality Portal (WQP) retrieval of makeup-water chemistry near each matched plant.

For every matched municipal plant (the unique ``plant_npdes_id`` values of results/supply_screen.csv plus the
Falls same-state option Morrisville Borough STP, PA0026701) the module queries the WQP REST ``Station`` and
``Result`` services (CSV output) within ``RADIUS_MI`` of the plant, keeps stream and river stations, and selects
the station with the most silica results since 2000 (ties broken by distance to the plant). It then computes the
median, sample count and date range of dissolved silica, calcium, alkalinity, pH, chloride, orthophosphate and
phosphorus at that station.

Every raw download is written under data/raw/wqp/ and recorded in data/raw/MANIFEST.md with
``paths.record_download``; a cached file is reused on rerun, so reruns are offline. If the portal cannot be
reached (network restriction, proxy refusal or outage), or ``--offline`` is set and no cached file exists, the
module stops after the first failed request, writes the failure to results/wqp_status.json, and writes
results/wqp_makeup.csv with ``source = 'wqp_unavailable'`` for every plant, so that peakflow.cycles falls back
to the literature makeup quality and marks every row 'assumed'.

Run: ``PYTHONPATH=src python -m peakflow.wqp [--offline]``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .paths import PROCESSED, RAW, RESULTS, USER_AGENT, record_download

WQP_HOST = "www.waterqualitydata.us"
WQP = f"https://{WQP_HOST}"
STATION_URL = f"{WQP}/data/Station/search"
RESULT_URL = f"{WQP}/data/Result/search"
WQP_DIR = RAW / "wqp"
STATUS_JSON = RESULTS / "wqp_status.json"
MAKEUP_CSV = RESULTS / "wqp_makeup.csv"
HEADERS = {"User-Agent": USER_AGENT}

RADIUS_MI = 10.0                 # search radius around each plant (WQP 'within', miles)
SINCE = "01-01-2000"             # WQP startDateLo format MM-DD-YYYY
TIMEOUT_S = 30
EXTRA_PLANTS = ["PA0026701"]     # Morrisville Borough STP, the Falls same-state option
STREAM_TYPES = ("stream", "river")

# Output column -> WQP CharacteristicName values accepted for it.
CHARACTERISTICS = {
    "silica": ["Silica"],
    "calcium": ["Calcium"],
    "alkalinity": ["Alkalinity", "Alkalinity, total"],
    "ph": ["pH"],
    "chloride": ["Chloride"],
    "orthophosphate": ["Orthophosphate"],
    "phosphorus": ["Phosphorus"],
}


class WQPUnavailable(RuntimeError):
    """The Water Quality Portal could not be reached (network block, proxy refusal or outage)."""


# ------------------------------------------------------------------------------------------------ plants
def plant_list(supply_screen: Path = RESULTS / "supply_screen.csv",
               majors: Path = PROCESSED / "wwtp_majors.csv") -> pd.DataFrame:
    """Matched plants: unique plant_npdes_id of the supply screen plus EXTRA_PLANTS, with wwtp_majors attributes."""
    ss = pd.read_csv(supply_screen)
    ids = [i for i in ss.plant_npdes_id.dropna().unique()]
    ids += [i for i in EXTRA_PLANTS if i not in ids]
    w = pd.read_csv(majors)
    cols = ["npdes_id", "name", "state", "lat", "lon", "receiving_water", "in_drb", "median_flow_mgd",
            "chloride_mg_l", "chloride_n_months", "tds_mg_l", "tds_n_months", "total_p_mg_l", "total_p_n_months"]
    out = w.loc[w.npdes_id.isin(ids), cols].copy()
    missing = set(ids) - set(out.npdes_id)
    if missing:
        raise ValueError(f"plants missing from wwtp_majors.csv: {sorted(missing)}")
    sites = ss.groupby("plant_npdes_id").site_id.apply(lambda s: ", ".join(sorted(s))).rename("site_ids")
    out = out.merge(sites, left_on="npdes_id", right_index=True, how="left")
    same = ss.dropna(subset=["same_state_npdes_id"]).groupby("same_state_npdes_id").site_id.apply(
        lambda s: ", ".join(sorted(s)))
    out["same_state_option_for"] = out.npdes_id.map(same)
    return out.sort_values("npdes_id").reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ geometry
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


# ------------------------------------------------------------------------------------------------ requests
def station_params(lat: float, lon: float, radius_mi: float = RADIUS_MI) -> dict:
    return {"lat": f"{lat:.5f}", "long": f"{lon:.5f}", "within": f"{radius_mi:g}",
            "siteType": "Stream", "mimeType": "csv", "zip": "no"}


def result_params(site_ids: list[str]) -> dict:
    names = [n for v in CHARACTERISTICS.values() for n in v]
    return {"siteid": ";".join(site_ids), "characteristicName": ";".join(dict.fromkeys(names)),
            "startDateLo": SINCE, "mimeType": "csv", "zip": "no", "dataProfile": "resultPhysChem"}


def _full_url(url: str, params: dict) -> str:
    return requests.Request("GET", url, params=params).prepare().url


def fetch_csv(url: str, params: dict, path: Path, offline: bool = False, getter=None) -> pd.DataFrame:
    """Return a WQP CSV as a DataFrame, from cache if present, else download, save and record in the MANIFEST."""
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, low_memory=False)
    if offline:
        raise WQPUnavailable(f"offline and no cached file {path.name}")
    getter = getter or (lambda u, p: requests.get(u, params=p, headers=HEADERS, timeout=TIMEOUT_S))
    try:
        r = getter(url, params)
    except requests.exceptions.RequestException as e:
        raise WQPUnavailable(f"{type(e).__name__}: {e}") from e
    blocked = r.headers.get("X-Proxy-Error", "")
    if r.status_code != 200 or blocked:
        raise WQPUnavailable(f"HTTP {r.status_code} {blocked}".strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    record_download(path, _full_url(url, params), note="WQP REST CSV")
    return pd.read_csv(io.BytesIO(r.content), low_memory=False)


# ------------------------------------------------------------------------------------------------ selection
def select_station(stations: pd.DataFrame, results: pd.DataFrame, lat: float, lon: float) -> pd.Series | None:
    """Stream or river station with the most silica results since SINCE; ties broken by distance to the plant."""
    if stations is None or stations.empty:
        return None
    st = stations.copy()
    typ = st.get("MonitoringLocationTypeName", pd.Series("", index=st.index)).fillna("").str.lower()
    st = st[typ.str.contains("|".join(STREAM_TYPES))]
    if st.empty:
        return None
    st["distance_km"] = haversine_km(lat, lon, st.LatitudeMeasure.astype(float), st.LongitudeMeasure.astype(float))
    res = results if results is not None else pd.DataFrame(columns=["MonitoringLocationIdentifier",
                                                                     "CharacteristicName"])
    sil = res[res.CharacteristicName.isin(CHARACTERISTICS["silica"])]
    counts = sil.groupby("MonitoringLocationIdentifier").size()
    st["n_silica"] = st.MonitoringLocationIdentifier.map(counts).fillna(0).astype(int)
    st = st.sort_values(["n_silica", "distance_km"], ascending=[False, True])
    return st.iloc[0]


def summarize(results: pd.DataFrame, station_id: str) -> dict:
    """Median, count and date range of each characteristic at one station."""
    r = results[results.MonitoringLocationIdentifier == station_id].copy()
    r["value"] = pd.to_numeric(r.ResultMeasureValue, errors="coerce")
    r["date"] = pd.to_datetime(r.ActivityStartDate, errors="coerce")
    out = {}
    for key, names in CHARACTERISTICS.items():
        s = r[r.CharacteristicName.isin(names) & r.value.notna()]
        out[f"{key}_median"] = float(s.value.median()) if len(s) else math.nan
        out[f"{key}_n"] = int(len(s))
        out[f"{key}_first"] = s.date.min().date().isoformat() if len(s) else ""
        out[f"{key}_last"] = s.date.max().date().isoformat() if len(s) else ""
        units = s.get("ResultMeasure/MeasureUnitCode", pd.Series(dtype=str)).dropna().unique()
        out[f"{key}_unit"] = ";".join(sorted(map(str, units)))
    return out


# ------------------------------------------------------------------------------------------------ run
def run(offline: bool = False, getter=None, plants: pd.DataFrame | None = None,
        status_json: Path = STATUS_JSON, makeup_csv: Path = MAKEUP_CSV, raw_dir: Path = WQP_DIR) -> dict:
    plants = plant_list() if plants is None else plants
    rows, status = [], {"service": WQP, "radius_mi": RADIUS_MI, "since": SINCE, "status": "ok",
                        "checked_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    for _, p in plants.iterrows():
        base = {"npdes_id": p.npdes_id, "name": p["name"], "receiving_water": p.receiving_water}
        if status["status"] != "ok":
            rows.append({**base, "source": "wqp_unavailable"})
            continue
        try:
            sp = station_params(p.lat, p.lon)
            stations = fetch_csv(STATION_URL, sp, raw_dir / f"station_{p.npdes_id}.csv", offline, getter)
            if stations.empty:
                rows.append({**base, "source": "no_station_within_radius"})
                continue
            ids = stations.MonitoringLocationIdentifier.dropna().unique().tolist()
            results = fetch_csv(RESULT_URL, result_params(ids), raw_dir / f"result_{p.npdes_id}.csv", offline,
                                getter)
            best = select_station(stations, results, p.lat, p.lon)
            if best is None:
                rows.append({**base, "source": "no_station_within_radius"})
                continue
            rows.append({**base, "source": "wqp", "station_id": best.MonitoringLocationIdentifier,
                         "station_name": best.get("MonitoringLocationName", ""),
                         "station_distance_km": float(best.distance_km),
                         **summarize(results, best.MonitoringLocationIdentifier)})
        except WQPUnavailable as e:
            status.update(status="unavailable", domain=WQP_HOST, error=str(e),
                          first_failed_url=_full_url(STATION_URL, station_params(p.lat, p.lon)),
                          note="Stopped after the first failed request. "
                               "peakflow.cycles uses the literature makeup quality for every plant.")
            rows.append({**base, "source": "wqp_unavailable"})
    out = pd.DataFrame(rows)
    makeup_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(makeup_csv, index=False)
    status["n_plants"] = int(len(out))
    status["n_wqp"] = int((out.source == "wqp").sum())
    status_json.write_text(json.dumps(status, indent=2) + "\n")
    return status


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true", help="use cached data/raw/wqp files only")
    a = ap.parse_args(argv)
    s = run(offline=a.offline)
    print(f"wqp: status {s['status']}; {s['n_wqp']} of {s['n_plants']} plants with WQP data"
          + (f"; {s.get('error', '')}" if s["status"] != "ok" else ""))


if __name__ == "__main__":
    main()
