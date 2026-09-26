"""Planned data center sites in the Delaware River Basin.

Primary list: a hand-built export of the trackdatacenters.com DRB records supplied by the author
(data/raw/trackdatacenters_drb.csv, 40 rows; data/raw/trackdatacenters_drb_nearmiss.csv, 23 rows
outside the basin). The tracker is cited once as the site list [trackdatacenters_2026]; each row's
source_url is that site's primary citation. The tracker's API was not scraped.

Rules (applied in this order):
  1. Map and counts use record_type == "Data Center" only; zoning ordinances, site advertisements and
     zoning challenges stay in the CSV (on_map = False).
  2. Active = proposed, preliminary, delayed, construction; inactive = rejected, withdrawn. Map active only.
  3. location_confidence "exact" -> verified_location True (solid outline); "approximate" / "uncertain"
     -> verified_location False (dashed outline).
  4. stated_mw missing -> assume 100 MW IT (capacity_basis = "assumed_100MW_IT"); stated_mw present ->
     treated as total campus power, IT load = stated_mw / PUE (calibrated PUE), capacity_basis =
     "stated_campus_MW_div_PUE".
  5. Point-in-polygon against the DRB boundary (WBD HUC6 020401+020402) in EPSG:5070; distance to the
     boundary is recorded and sites within 2 km are flagged near_divide.
Near-miss rows are kept out of the map and every headline count.

Source verification (source_verified; dashed outline when False):
  * The cached HTTP check in data/processed/site_url_check.csv is written only by `make urls`
    (peakflow.urlcheck); run(check=False), used by `make map`, never touches the network.
  * The hand content check in data/processed/site_url_verification.csv records whether the page names the site.
  * data/sites/source_url_overrides.csv replaces dead or bot-blocked sources with a Wayback snapshot or an
    alternate outlet (original kept in original_url).
  * FORCE_UNVERIFIED lists sites classed as unverified regardless of the checks above, with the reason written
    to verification_note.
Every row not drawn on the map is logged to results/exclusions.csv with stage 'sites' and its reason.
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from . import urlcheck
from .paths import PROCESSED, RAW, RESULTS, SITES, log_exclusions

MAIN = RAW / "trackdatacenters_drb.csv"
NEARMISS = RAW / "trackdatacenters_drb_nearmiss.csv"
OVERRIDES = SITES / "source_url_overrides.csv"
ACTIVE = {"proposed", "preliminary", "delayed", "construction"}
INACTIVE = {"rejected", "withdrawn"}
ASSUMED_IT_MW = 100.0
NEAR_DIVIDE_KM = 2.0
BOT_BLOCK_DOMAINS = urlcheck.BOT_BLOCK_DOMAINS
EXCLUSION_STAGE = "sites"
# Sites whose source is classed as unverified regardless of the URL and content checks; the note states why.
FORCE_UNVERIFIED = {
    "DRB07": "a live fetch on 2026-09-25 returned HTTP 403 where the cached check had recorded 200; a later fetch "
             "that day returned 200 and the page names DataOne and Vineland, but the only Wayback capture is a 404, "
             "so the source is classed as unverified",
    "DRB33": "the original Limerick document URL is session-bound and returns 'Download has expired'; the Wayback "
             "capture of the township hearings page (2026-07-16) names the applicant, address and Linfield, but it "
             "was not compared against the original document, so the source is classed as unverified",
}

# Sources whose content check was done by eye because the page has no machine-readable text.
MANUAL_CHECK = {
    "DRB10": "manual check: source is a scanned 5-page PDF without a text layer (Andover Ordinance #2026-13), "
             "read visually",
    "DRB22": "manual check: source is a YouTube video; only the title and description were checked",
}

# Aliases for peakflow.urlcheck.check_url and check_urls.
check_url = urlcheck.check_url
check_urls = urlcheck.check_urls


def classify(df: pd.DataFrame, pue: float, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    d = df.copy()
    d["is_data_center"] = d.record_type.eq("Data Center")
    d["active"] = d.status.isin(ACTIVE)
    d["on_map"] = d.is_data_center & d.active
    d["verified_location"] = d.location_confidence.eq("exact")
    d["capacity_basis"] = np.where(d.stated_mw.notna(), "stated_campus_MW_div_PUE", "assumed_100MW_IT")
    d["it_mw"] = np.where(d.stated_mw.notna(), d.stated_mw / pue, ASSUMED_IT_MW)
    g = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.lon, d.lat), crs=4326).to_crs(5070)
    poly = boundary.to_crs(5070).union_all()
    g["in_drb"] = g.within(poly)
    g["dist_to_divide_km"] = g.geometry.distance(poly.boundary) / 1000.0
    g["near_divide"] = g.dist_to_divide_km <= NEAR_DIVIDE_KM
    return g


def exclusion_records(out: pd.DataFrame) -> list[dict]:
    """One record per planned-site row not drawn on the map, with the first rule that drops it."""
    recs = []
    for r in out[~out.on_map.astype(bool)].itertuples():
        if r.list == "near_miss":
            km = getattr(r, "km_outside_drb", np.nan)
            reason = ("near-miss list: outside the Delaware River Basin polygon"
                      + (f" ({float(km):.1f} km outside)" if pd.notna(km) else ""))
        elif not bool(r.is_data_center):
            reason = f"not a data center record (record_type '{r.record_type}')"
        elif not bool(r.active):
            reason = f"inactive status '{r.status}'"
        elif not bool(r.in_drb):
            reason = f"active data center outside the basin polygon ({float(r.dist_to_divide_km):.1f} km from divide)"
        else:
            reason = "not drawn on the map (unclassified reason)"
        recs.append({"record_id": r.site_id, "record_name": r.name, "reason": reason})
    return recs


def _apply_overrides(d: pd.DataFrame, ov: pd.DataFrame, uc: pd.DataFrame | None) -> None:
    ovm = ov.set_index("original_url")
    d["original_url"] = ""
    d["replacement_kind"] = ""
    hit = d.source_url.isin(ovm.index)
    d.loc[hit, "original_url"] = d.loc[hit, "source_url"]
    d.loc[hit, "replacement_kind"] = d.loc[hit, "source_url"].map(ovm.replacement_kind)
    d.loc[hit, "source_url"] = d.loc[hit, "original_url"].map(ovm.source_url)
    d.loc[hit, "url_check"] = "resolves_via_replacement"
    d.loc[hit, "content_match"] = True
    if uc is not None:  # a replacement that the cached check found missing does not verify the site
        rep = uc.set_index("source_url").url_check
        gone = hit & d.source_url.map(rep).eq("not_found")
        d.loc[gone, "url_check"] = "replacement_not_found"
        d.loc[gone, "content_match"] = False


def run(check: bool = False) -> dict:
    """Classify planned sites and write data/sites/planned_sites.csv, results/sites_summary.json and the
    'sites' rows of results/exclusions.csv. check=True refreshes the live URL check first (network)."""
    cal = json.loads((RESULTS / "calibration.json").read_text())
    pue = float(cal["primary"]["pue"])
    boundary = gpd.read_file(PROCESSED / "drb_boundary.geojson")
    main = pd.read_csv(MAIN)
    near = pd.read_csv(NEARMISS)
    g = classify(main, pue, boundary)
    gn = classify(near, pue, boundary)
    g["site_id"] = [f"DRB{i+1:02d}" for i in range(len(g))]
    gn["site_id"] = [f"NM{i+1:02d}" for i in range(len(gn))]
    uc = urlcheck.run() if check else urlcheck.load()
    if uc is None:
        uc = pd.DataFrame(columns=urlcheck.COLUMNS)
    uc = uc.drop_duplicates("source_url")
    g = g.merge(uc, on="source_url", how="left")
    gn = gn.merge(uc, on="source_url", how="left")
    for d in (g, gn):
        d["url_check"] = d.url_check.fillna("not_checked")
    # Content verification (page names the site) from data/processed/site_url_verification.csv.
    ver_path = PROCESSED / "site_url_verification.csv"
    for d in (g, gn):
        d["content_match"] = np.nan
    if ver_path.exists():
        ver = pd.read_csv(ver_path)[["source_url", "url_check", "content_match", "page_title"]]
        ver = ver.rename(columns={"url_check": "url_check_v"}).drop_duplicates("source_url")
        for d in (g, gn):
            mm = d[["source_url"]].merge(ver, on="source_url", how="left")
            d["url_check"] = mm.url_check_v.fillna(d.url_check).values
            d["content_match"] = mm.content_match.values
    # Replacement URLs (Wayback or alternate outlet) for sources that no longer resolve; originals kept.
    ov = pd.read_csv(OVERRIDES) if OVERRIDES.exists() else pd.DataFrame(
        columns=["original_url", "source_url", "replacement_kind", "note"])
    for d in (g, gn):
        d["content_match"] = d.content_match.astype(object)
        _apply_overrides(d, ov, uc)
        # source_verified: the cited page (or its replacement) was opened and names the site.
        d["source_verified"] = d.url_check.isin(["resolves", "resolves_via_replacement"]) & \
            d.content_match.astype(str).str.lower().eq("true")
        forced = d.site_id.isin(FORCE_UNVERIFIED)
        d.loc[forced, "source_verified"] = False
        d["verification_note"] = d.site_id.map(FORCE_UNVERIFIED).fillna(d.site_id.map(MANUAL_CHECK)).fillna("")
        # Dashed outline (unverified) if location is not exact OR the source is not confirmed.
        d["unverified"] = ~(d.verified_location & d.source_verified)
    g["list"] = "main"
    gn["list"] = "near_miss"
    g["on_map"] = g.on_map & g.in_drb
    gn["on_map"] = False
    cols = ["site_id", "list", "name", "developer", "county", "municipality", "address_or_intersection",
            "record_type", "status", "is_data_center", "active", "on_map", "stated_mw", "capacity_basis",
            "it_mw", "lat", "lon", "location_confidence", "verified_location", "in_drb", "dist_to_divide_km",
            "near_divide", "source_url", "original_url", "replacement_kind", "source_date", "url_check",
            "url_http_code", "url_final", "content_match", "source_verified", "unverified", "verification_note",
            "tracker_updated"]
    out = pd.concat([pd.DataFrame(g[cols + (["km_outside_drb"] if "km_outside_drb" in g else [])]),
                     pd.DataFrame(gn[cols + ["km_outside_drb"]])], ignore_index=True)
    SITES.mkdir(parents=True, exist_ok=True)
    out.to_csv(SITES / "planned_sites.csv", index=False)
    excl = exclusion_records(out)
    log_exclusions(EXCLUSION_STAGE, excl)
    dc = g[g.is_data_center]
    act = dc[dc.active]
    summary = {
        "main_rows": int(len(g)), "data_center_rows": int(len(dc)),
        "non_data_center_rows": int((~g.is_data_center).sum()),
        "active": int(len(act)), "inactive": int((~dc.active).sum()),
        "inactive_by_status": dc[~dc.active].status.value_counts().to_dict(),
        "active_outside_polygon": int((~act.in_drb).sum()),
        "active_location_confidence": act.location_confidence.value_counts().to_dict(),
        "active_stated_mw": int(act.stated_mw.notna().sum()),
        "active_assumed_mw": int(act.stated_mw.isna().sum()),
        "active_near_divide": act.loc[act.near_divide, ["name", "dist_to_divide_km"]].to_dict("records"),
        "active_source_verified": int(act.source_verified.sum()),
        "active_unverified_dashed": int(act.unverified.sum()),
        "active_url_check": act.url_check.value_counts().to_dict(),
        "active_source_not_verified": act.loc[~act.source_verified, ["name", "url_check"]].to_dict("records"),
        "active_forced_unverified": sorted(set(act.site_id) & set(FORCE_UNVERIFIED)),
        "active_replacement_sources": act.loc[act.replacement_kind.ne(""), ["site_id", "replacement_kind"]]
        .to_dict("records"),
        "near_miss_rows": int(len(gn)),
        "url_check_main": g.url_check.value_counts().to_dict(),
        "url_check_near_miss": gn.url_check.value_counts().to_dict(),
        "excluded_rows_logged": int(len(excl)),
        "url_check_cache": "live (make urls)" if check else "cached data/processed/site_url_check.csv",
        "pue_used": pue,
    }
    (RESULTS / "sites_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    print(json.dumps(run(check=False), indent=2, default=str))
