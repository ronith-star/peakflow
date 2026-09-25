"""Supply screen: can a nearby municipal treatment plant's effluent cover a planned site's peak cooling makeup?

Rule (all distances in EPSG:5070 meters; 10 miles = 16093.44 m):
  Sites   : data/sites/planned_sites.csv rows with on_map == True.
  Demand  : peak-day makeup (gal/day) = it_mw * (peak_day_gpd / p_it_mw) from the calibrated hybrid
            (results/calibration.json, key 'primary'); the cooling model is linear in P_IT. The 99th
            percentile day is scaled the same way from cooling_model.daily_makeup on KTTN 2005-2024.
  Eligible plants (primary): is_potw & dmr_flow_months >= 12 & median_flow_mgd not null. Plants on either
            side of the DRB divide are eligible; a plant outside the basin is carried as an inter-basin flag.
  Class   : nearest eligible plant within 10 mi decides the class.
            matchable - nearest plant's median monthly flow (MGD * 1e6 gal/day) >= site peak-day makeup
            partial   - an eligible plant is within 10 mi but the nearest one's median flow is below it
            none      - no eligible plant within 10 mi
  Sensitivities: (a) non-POTW majors also eligible; (b) uniform 100 MW IT at every site;
            (c) assumed-capacity: sites with capacity_basis 'assumed_100MW_IT' at 50/100/200 MW IT.
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from .paths import PROCESSED, RESULTS, SITES, log_exclusions

RADIUS_M = 16093.44  # 10 statute miles
M_PER_MI = 1609.344
MIN_FLOW_MONTHS = 12
CRS = 5070
ASSUMED_BASIS = "assumed_100MW_IT"
ASSUMED_MW = (50, 100, 200)  # assumed-capacity sensitivity for sites without a stated MW
COVER_BINS = ["no eligible plant within 10 mi", "50 to 200 MW", "over 200 MW"]  # covered_it_mw bins for map and bar chart
NO_PLANT_BIN = COVER_BINS[0]


# ---------------------------------------------------------------- inputs
def per_mw_rates(calibration_path=RESULTS / "calibration.json", compute_p99: bool = True) -> dict:
    with open(calibration_path) as fh:
        cal = json.load(fh)["primary"]
    p_it = float(cal["p_it_mw"])
    out = {"p_it_mw_calibrated": p_it,
           "peak_day_gpd_calibrated": float(cal["diagnostics"]["peak_day_gpd"]),
           "peak_day_gpd_per_mw": float(cal["diagnostics"]["peak_day_gpd"]) / p_it}
    if compute_p99:
        from .calibration import load_kttn
        from .cooling_model import CoolingParams, daily_makeup

        p = CoolingParams(p_it_mw=p_it, pue=float(cal["pue"]), cycles=float(cal["cycles"]),
                          t_sw_c=float(cal["t_sw_c"]), gamma=float(cal["gamma"]),
                          twb_ref_c=float(cal["twb_ref_c"]), architecture="hybrid")
        d = daily_makeup(load_kttn(), p)
        out["p99_day_gpd_calibrated"] = float(d.makeup_gpd.quantile(0.99))
        out["peak_day_gpd_recomputed"] = float(d.makeup_gpd.max())
        out["n_valid_days"] = int(d.makeup_gpd.notna().sum())
    else:
        out["p99_day_gpd_calibrated"] = float(cal["diagnostics"]["p99_day_gpd"])
    out["p99_day_gpd_per_mw"] = out["p99_day_gpd_calibrated"] / p_it
    return out


def load_sites() -> gpd.GeoDataFrame:
    s = pd.read_csv(SITES / "planned_sites.csv")
    s = s[s.on_map.astype(str).str.lower() == "true"].copy()
    return gpd.GeoDataFrame(s, geometry=gpd.points_from_xy(s.lon, s.lat), crs=4326).to_crs(CRS)


def load_plants() -> gpd.GeoDataFrame:
    p = pd.read_csv(PROCESSED / "wwtp_majors.csv", dtype={"npdes_id": str})
    p = p[p.lat.notna() & p.lon.notna()].copy()
    return gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p.lon, p.lat), crs=4326).to_crs(CRS)


def eligible_mask(plants: pd.DataFrame, include_non_potw: bool = False) -> pd.Series:
    ok = (plants.dmr_flow_months.fillna(0) >= MIN_FLOW_MONTHS) & plants.median_flow_mgd.notna()
    if not include_non_potw:
        ok &= plants.is_potw.astype(str).str.lower() == "true"
    return ok


# ---------------------------------------------------------------- core
def classify(sites: gpd.GeoDataFrame, plants: gpd.GeoDataFrame, demand_gpd: pd.Series,
             radius_m: float = RADIUS_M) -> pd.DataFrame:
    """Per-site match against an already-filtered set of eligible plants (both GeoDataFrames in meters)."""
    sx, sy = sites.geometry.x.to_numpy(), sites.geometry.y.to_numpy()
    px, py = plants.geometry.x.to_numpy(), plants.geometry.y.to_numpy()
    dist = np.hypot(sx[:, None] - px[None, :], sy[:, None] - py[None, :]) if len(px) else np.empty((len(sx), 0))
    med = plants.median_flow_mgd.to_numpy(dtype=float) * 1e6
    rows = []
    for i, dem in enumerate(np.asarray(demand_gpd, dtype=float)):
        within = np.where(dist[i] <= radius_m)[0] if dist.shape[1] else np.array([], int)
        r = {"n_eligible_within_10mi": int(len(within))}
        if len(within) == 0:
            r["class"] = "none"
            if dist.shape[1]:
                j = int(np.argmin(dist[i]))
                r["nearest_any_eligible_mi"] = dist[i, j] / M_PER_MI
            rows.append(r)
            continue
        j = within[np.argmin(dist[i, within])]
        k = within[np.argmax(med[within])]
        r.update({
            "class": "matchable" if med[j] >= dem else "partial",
            "plant_idx": int(j), "distance_mi": dist[i, j] / M_PER_MI, "coverage_ratio": med[j] / dem,
            "largest_idx": int(k), "largest_distance_mi": dist[i, k] / M_PER_MI,
            "largest_coverage_ratio": med[k] / dem, "largest_alone_matchable": bool(med[k] >= dem),
            "nearest_any_eligible_mi": dist[i, j] / M_PER_MI,
        })
        rows.append(r)
    out = pd.DataFrame(rows, index=sites.index)
    pl = plants.reset_index(drop=True)
    for pre, idx in (("plant", "plant_idx"), ("largest", "largest_idx")):
        if idx not in out:
            out[idx] = np.nan
        sel = out[idx].dropna().astype(int)
        for col, src in (("npdes_id", "npdes_id"), ("name", "name"), ("median_flow_mgd", "median_flow_mgd"),
                         ("design_flow_mgd", "design_flow_mgd"), ("in_drb", "in_drb"),
                         ("facility_type", "facility_type"), ("permit_status", "permit_status")):
            if src in pl:
                out.loc[sel.index, f"{pre}_{col}"] = pl.loc[sel.values, src].to_numpy()
        out = out.drop(columns=idx)
    return out


# ---------------------------------------------------------------- pipeline
def run() -> dict:
    rates = per_mw_rates()
    sites = load_sites()
    plants = load_plants()

    bad = sites[sites.lat.isna() | sites.lon.isna() | sites.it_mw.isna()]
    excl = [{"record_id": r.site_id, "record_name": r.name, "reason": "site missing lat/lon or it_mw"}
            for r in bad.itertuples()]
    sites = sites.drop(bad.index)

    elig = eligible_mask(plants)
    for r in plants[~elig & (plants.is_potw.astype(str).str.lower() == "true")].itertuples():
        excl.append({"record_id": r.npdes_id, "record_name": r.name,
                     "reason": f"POTW ineligible for supply screen: {int(r.dmr_flow_months or 0)} DMR flow months "
                               f"(< {MIN_FLOW_MONTHS}) or no median flow"})
    for r in plants[plants.is_potw.astype(str).str.lower() != "true"].itertuples():
        excl.append({"record_id": r.npdes_id, "record_name": r.name,
                     "reason": f"non-POTW major (facility_type={r.facility_type}); eligible only in sensitivity (a)"})
    log_exclusions("supply_screen", excl)

    sites["peak_day_gpd"] = sites.it_mw * rates["peak_day_gpd_per_mw"]
    sites["p99_day_gpd"] = sites.it_mw * rates["p99_day_gpd_per_mw"]
    pe = plants[elig]
    base = classify(sites, pe, sites.peak_day_gpd)
    base["plant_inter_basin"] = base.plant_in_drb.map(lambda v: None if pd.isna(v) else str(v).lower() != "true")
    p99 = classify(sites, pe, sites.p99_day_gpd)
    sens_a = classify(sites, plants[eligible_mask(plants, include_non_potw=True)], sites.peak_day_gpd)
    sens_b = classify(sites, pe, pd.Series(100.0 * rates["peak_day_gpd_per_mw"], index=sites.index))

    assumed = sites.capacity_basis.eq(ASSUMED_BASIS)
    assumed_cls = {}
    for mw in ASSUMED_MW:
        it = sites.it_mw.where(~assumed, float(mw))
        assumed_cls[mw] = classify(sites, pe, it * rates["peak_day_gpd_per_mw"])["class"]

    keep = ["site_id", "name", "municipality", "county", "it_mw", "capacity_basis", "verified_location",
            "near_divide", "lat", "lon", "peak_day_gpd", "p99_day_gpd"]
    keep += [c for c in ("source_verified", "unverified", "status", "developer", "source_url", "original_url")
             if c in sites.columns]
    out = pd.concat([sites[keep], base], axis=1)
    out["class_p99_day"] = p99["class"]
    out["class_sens_a_non_potw_eligible"] = sens_a["class"]
    out["sens_a_plant_name"] = sens_a.get("plant_name")
    out["sens_a_plant_facility_type"] = sens_a.get("plant_facility_type")
    out["class_sens_b_100mw_it"] = sens_b["class"]
    for mw in ASSUMED_MW:
        out[f"class_assumed_{mw}"] = assumed_cls[mw]
    out["class_any_plant_within_10mi"] = np.where(
        out["class"] == "none", "none", np.where(out.largest_alone_matchable.fillna(False), "matchable", "partial"))

    # Capacity-independent measures.
    out["eligible_potw_within_10mi"] = out["class"].ne("none")
    out["stated_mw"] = sites["stated_mw"] if "stated_mw" in sites else np.nan
    per_mw = rates["peak_day_gpd_per_mw"]
    # Largest IT load (MW) whose calibrated peak-day makeup the nearest eligible plant's median flow covers.
    # Sites with no eligible plant within 10 mi get 0 (they fall in the lowest bin) and are flagged above.
    out["covered_it_mw"] = np.where(out.eligible_potw_within_10mi,
                                    out.plant_median_flow_mgd * 1e6 / per_mw, 0.0)
    # The lowest bin is exactly the sites with no eligible plant within 10 mi (covered_it_mw = 0). A site that has
    # an eligible plant covering under 50 MW would need its own bin; fail loudly rather than mislabel it.
    low = out.eligible_potw_within_10mi & (out.covered_it_mw < 50)
    if low.any():
        raise ValueError(f"sites with an eligible plant covering < 50 MW need a separate bin: {list(out.loc[low, 'site_id'])}")
    out["covered_it_bin"] = np.where(~out.eligible_potw_within_10mi, NO_PLANT_BIN,
                                     np.where(out.covered_it_mw >= 200, "over 200 MW", "50 to 200 MW"))

    # Nearest eligible plant in the site's own state (cross-state matches are flagged).
    site_state = sites["county"].str.extract(r",\s*([A-Z]{2})\s*$")[0]
    out["site_state"] = site_state
    out["plant_state"] = out.plant_npdes_id.map(plants.set_index("npdes_id")["state"]) if "state" in plants else np.nan
    out["match_crosses_state_line"] = out.eligible_potw_within_10mi & out.plant_state.ne(out.site_state)
    for c in ("same_state_npdes_id", "same_state_name", "same_state_distance_mi",
              "same_state_median_flow_mgd", "same_state_coverage_ratio", "same_state_covered_it_mw"):
        out[c] = np.nan
    out[["same_state_npdes_id", "same_state_name"]] = out[["same_state_npdes_id", "same_state_name"]].astype(object)
    for i in out.index:
        st = site_state.get(i)
        cand = pe[pe["state"] == st] if "state" in pe else pe.iloc[0:0]
        if not len(cand):
            continue
        d = cand.geometry.distance(sites.geometry.loc[i])
        j = d.idxmin()
        med = float(cand.loc[j, "median_flow_mgd"])
        out.loc[i, "same_state_npdes_id"] = cand.loc[j, "npdes_id"]
        out.loc[i, "same_state_name"] = cand.loc[j, "name"]
        out.loc[i, "same_state_distance_mi"] = float(d.loc[j]) / M_PER_MI
        out.loc[i, "same_state_median_flow_mgd"] = med
        out.loc[i, "same_state_coverage_ratio"] = med * 1e6 / float(out.loc[i, "peak_day_gpd"])
        out.loc[i, "same_state_covered_it_mw"] = med * 1e6 / per_mw
    cols_first = keep + ["stated_mw", "eligible_potw_within_10mi", "covered_it_mw", "covered_it_bin",
                         "class", "distance_mi", "plant_npdes_id", "plant_name", "plant_median_flow_mgd",
                         "plant_design_flow_mgd", "coverage_ratio", "plant_in_drb", "plant_inter_basin", "plant_permit_status",
                         "n_eligible_within_10mi"]
    out = out[cols_first + [c for c in out.columns if c not in cols_first]]
    out.to_csv(RESULTS / "supply_screen.csv", index=False)

    classes = ["matchable", "partial", "none"]
    cnt = lambda s: {c: int((s == c).sum()) for c in classes}  # noqa: E731
    n, m = int((out["class"] == "matchable").sum()), len(out)
    summary = {
        "n_sites": m,
        "n_plants_total": int(len(plants)),
        "n_plants_eligible_primary": int(elig.sum()),
        "n_plants_eligible_sens_a": int(eligible_mask(plants, include_non_potw=True).sum()),
        "radius_m": RADIUS_M, "min_dmr_flow_months": MIN_FLOW_MONTHS,
        "demand_rates": rates,
        "headline_capacity_independent": {
            "n_within_10mi_of_eligible_potw": int(out.eligible_potw_within_10mi.sum()), "of": m,
            "text": f"{int(out.eligible_potw_within_10mi.sum())} of {m} active planned data center sites sit within "
                    f"10 miles of an eligible municipal treatment plant",
            "n_no_published_capacity": int(out.capacity_basis.eq(ASSUMED_BASIS).sum()),
        },
        "covered_it_bins": {b: int((out.covered_it_bin == b).sum()) for b in COVER_BINS},
        "covered_it_bins_note": "covered_it_mw = nearest eligible POTW median flow / calibrated peak-day makeup per MW IT; "
                                "sites with no eligible POTW within 10 mi are set to 0 and fall in the lowest bin",
        "n_match_crosses_state_line": int(out.match_crosses_state_line.sum()),
        "class_counts": cnt(out["class"]),
        "headline": f"{n} of {m} planned sites sit within 10 miles of a treatment plant that could cover their "
                    f"peak cooling demand",
        "sensitivity": {
            "a_non_potw_eligible": cnt(out.class_sens_a_non_potw_eligible),
            "b_uniform_100mw_it": cnt(out.class_sens_b_100mw_it),
            "p99_day_demand": cnt(out.class_p99_day),
            "any_plant_within_10mi_not_just_nearest": cnt(out.class_any_plant_within_10mi),
        },
        "assumed_capacity_sensitivity": {
            "note": f"sites with capacity_basis == '{ASSUMED_BASIS}' re-run at each IT load; stated-MW sites unchanged; "
                    "main class (map) uses 100 MW",
            "n_assumed_sites": int(assumed.sum()),
            **{f"{mw}MW": cnt(out[f"class_assumed_{mw}"]) for mw in ASSUMED_MW},
            "matchable_spread_max_minus_min": int(max((out[f"class_assumed_{mw}"] == "matchable").sum() for mw in ASSUMED_MW)
                                                  - min((out[f"class_assumed_{mw}"] == "matchable").sum() for mw in ASSUMED_MW)),
            "sites_changing_class": {
                r.site_id: {f"{mw}MW": r[f"class_assumed_{mw}"] for mw in ASSUMED_MW}
                for _, r in out.iterrows() if len({r[f"class_assumed_{mw}"] for mw in ASSUMED_MW}) > 1},
        },
        "n_matched_plant_outside_drb": int(out.plant_inter_basin.eq(True).sum()),
        "by_capacity_basis": {k: cnt(g["class"]) for k, g in out.groupby("capacity_basis")},
        "by_verified_location": {str(k): cnt(g["class"]) for k, g in out.groupby("verified_location")},
        "sites_by_class": {c: out.loc[out["class"] == c, "site_id"].tolist() for c in classes},
    }
    (RESULTS / "supply_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
