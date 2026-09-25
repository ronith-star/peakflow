"""Every planned-site row not drawn on the map is logged in exclusions.csv (stage 'sites'); forced flags hold."""
import pandas as pd
import pytest

from reuse_ready import paths, sites


def _rows():
    base = dict(developer="d", record_type="Data Center", status="proposed", is_data_center=True, active=True,
                in_drb=True, on_map=True, dist_to_divide_km=5.0, km_outside_drb=float("nan"))
    rows = [
        dict(base, site_id="DRB01", name="kept", list="main"),
        dict(base, site_id="DRB02", name="rejected one", list="main", status="rejected", active=False, on_map=False),
        dict(base, site_id="DRB03", name="ordinance", list="main", record_type="Zoning Ordinance",
             is_data_center=False, on_map=False),
        dict(base, site_id="DRB04", name="outside polygon", list="main", in_drb=False, on_map=False,
             dist_to_divide_km=0.4),
        dict(base, site_id="NM01", name="near miss", list="near_miss", in_drb=False, on_map=False,
             km_outside_drb=3.25),
    ]
    return pd.DataFrame(rows)


def test_exclusion_records_one_per_dropped_row_with_reason():
    recs = {r["record_id"]: r["reason"] for r in sites.exclusion_records(_rows())}
    assert set(recs) == {"DRB02", "DRB03", "DRB04", "NM01"}
    assert recs["DRB02"] == "inactive status 'rejected'"
    assert recs["DRB03"].startswith("not a data center record")
    assert "outside the basin polygon" in recs["DRB04"]
    assert recs["NM01"].startswith("near-miss list") and "3.2 km outside" in recs["NM01"]


def test_log_exclusions_replaces_only_its_stage(tmp_path, monkeypatch):
    f = tmp_path / "exclusions.csv"
    monkeypatch.setattr(paths, "EXCLUSIONS", f)
    paths.log_exclusions("other", [{"record_id": "X", "record_name": "x", "reason": "r"}])
    paths.log_exclusions("sites", sites.exclusion_records(_rows()))
    paths.log_exclusions("sites", sites.exclusion_records(_rows()))  # idempotent
    e = pd.read_csv(f)
    assert e.stage.value_counts().to_dict() == {"sites": 4, "other": 1}


@pytest.mark.skipif(not (paths.SITES / "planned_sites.csv").exists() or not paths.EXCLUSIONS.exists(),
                    reason="pipeline outputs not built")
def test_repository_exclusions_cover_every_off_map_site():
    s = pd.read_csv(paths.SITES / "planned_sites.csv")
    e = pd.read_csv(paths.EXCLUSIONS)
    off = set(s.loc[~s.on_map.astype(bool), "site_id"])
    logged = set(e.loc[e.stage == "sites", "record_id"])
    assert off == logged
    assert not set(s.loc[s.on_map.astype(bool), "site_id"]) & logged


@pytest.mark.skipif(not (paths.SITES / "planned_sites.csv").exists(), reason="pipeline outputs not built")
def test_forced_unverified_sites_stay_unverified():
    s = pd.read_csv(paths.SITES / "planned_sites.csv").set_index("site_id")
    for sid in sites.FORCE_UNVERIFIED:
        assert not bool(s.loc[sid, "source_verified"]), sid
        assert bool(s.loc[sid, "unverified"]), sid
    assert {"DRB07", "DRB33"} <= set(sites.FORCE_UNVERIFIED)
