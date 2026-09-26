"""Synthetic-fixture tests for the supply screen classes and the 10-mile cutoff (EPSG:5070 meters)."""
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from peakflow.supply_screen import RADIUS_M, classify, eligible_mask

FIX = Path(__file__).parent / "fixtures"


def _gdf(name):
    d = pd.read_csv(FIX / name)
    return gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.x, d.y), crs=5070)


@pytest.fixture
def sites():
    return _gdf("supply_sites.csv").set_index("site_id", drop=False)


@pytest.fixture
def plants():
    return _gdf("supply_plants.csv")


def test_radius_is_ten_miles():
    assert RADIUS_M == pytest.approx(10 * 1609.344)


def test_eligibility(plants):
    assert set(plants[eligible_mask(plants)].npdes_id) == {"P_BIG", "P_SMALL", "P_OUTSIDE", "P_EDGE"}
    assert "P_IND" in set(plants[eligible_mask(plants, include_non_potw=True)].npdes_id)
    assert "P_SHORT" not in set(plants[eligible_mask(plants, include_non_potw=True)].npdes_id)


def test_three_classes_and_cutoff(sites, plants):
    r = classify(sites, plants[eligible_mask(plants)], sites.peak_day_gpd)
    assert r.loc["S_MATCH", "class"] == "matchable"
    assert r.loc["S_MATCH", "plant_npdes_id"] == "P_BIG"
    assert r.loc["S_MATCH", "coverage_ratio"] == pytest.approx(2.0)
    assert r.loc["S_MATCH", "distance_mi"] == pytest.approx(10000 / 1609.344)
    # P_OUTSIDE (5 MGD) is 16.1 km away, beyond the cutoff, so only the small plant counts
    assert r.loc["S_PARTIAL", "class"] == "partial"
    assert r.loc["S_PARTIAL", "plant_npdes_id"] == "P_SMALL"
    assert r.loc["S_PARTIAL", "n_eligible_within_10mi"] == 1
    assert r.loc["S_PARTIAL", "coverage_ratio"] == pytest.approx(0.5)
    assert not r.loc["S_PARTIAL", "largest_alone_matchable"]
    # P_EDGE is 16094 m away (> 16093.44 m); P_IND is non-POTW; P_SHORT has 6 DMR months
    assert r.loc["S_NONE", "class"] == "none"
    assert r.loc["S_NONE", "n_eligible_within_10mi"] == 0


def test_plant_just_inside_cutoff_counts(sites, plants):
    p = plants[eligible_mask(plants)].copy()
    p.loc[p.npdes_id == "P_EDGE", "geometry"] = gpd.points_from_xy([300000 + RADIUS_M - 0.5], [0])
    r = classify(sites, p, sites.peak_day_gpd)
    assert r.loc["S_NONE", "class"] == "matchable"


def test_sensitivity_non_potw(sites, plants):
    r = classify(sites, plants[eligible_mask(plants, include_non_potw=True)], sites.peak_day_gpd)
    assert r.loc["S_NONE", "class"] == "matchable"
    assert r.loc["S_NONE", "plant_npdes_id"] == "P_IND"


def test_demand_scaling_changes_class(sites, plants):
    r = classify(sites, plants[eligible_mask(plants)], sites.peak_day_gpd * 3)
    assert r.loc["S_MATCH", "class"] == "partial"
