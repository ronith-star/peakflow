"""Per-site blind-spot test (work order item 11): linear scaling, agreement with the grid, supplier join."""
import pandas as pd
import pytest

from reuse_ready import blindspot as B
from reuse_ready import site_blindspot as SB
from reuse_ready.paths import PROCESSED, RESULTS

pytestmark = pytest.mark.skipif(not (PROCESSED / "flow_daily.parquet").exists()
                                or not (RESULTS / "supply_screen.csv").exists(),
                                reason="flow, calibration or supply screen outputs not built")


@pytest.fixture(scope="module")
def d1():
    return SB.per_mw_series()


def test_linear_scaling_matches_direct_run(d1):
    w, cal, _, _ = B.load_inputs("primary")
    d = B.daily_series(w, B.config_params(241.666667, "hybrid", cal))
    m = SB.site_metrics(d1, 241.666667)
    assert m["peak_day_max_gpd"] == pytest.approx(float(d.max()), rel=1e-9)
    r30 = d.rolling(B.WINDOW_DAYS, min_periods=B.WINDOW_MIN_VALID).mean()
    assert m["r30_max_gpd"] == pytest.approx(float(r30.max()), rel=1e-9)


def test_agrees_with_grid_at_100mw(d1):
    raw = pd.read_csv(RESULTS / "blindspot_raw.csv")
    h = raw[(raw.architecture == "hybrid") & (raw.it_load_mw == 100)].iloc[0]
    m = SB.site_metrics(d1, 100)
    assert m["r30_max_gpd"] == pytest.approx(h.r30_max_gpd, rel=1e-9)
    assert m["peak_day_max_gpd"] == pytest.approx(h.peak_day_max_gpd, rel=1e-9)
    assert m["days_per_year_30day_over"] == pytest.approx(h.days_per_year_30day_window_over_trigger, rel=1e-9)


def test_flags_and_band(d1):
    lo, hi = SB.band_mw(d1)
    assert SB.site_metrics(d1, (lo + hi) / 2)["averaging_blind_spot"]
    assert not SB.site_metrics(d1, lo * 0.9)["averaging_blind_spot"]
    assert SB.site_metrics(d1, hi * 1.1)["review_if_self_supplied"]


def test_site_file():
    t = pd.read_csv(RESULTS / "site_blindspot.csv")
    assert list(t.columns) == SB.OUT_COLS and len(t) == 24 and t.site_id.is_unique
    assert (t.review_if_self_supplied == ~t.below_trigger_30day).all()
    assert (t.averaging_blind_spot == (t.below_trigger_30day & (t.peak_day_max_gpd > B.TRIGGER_GPD))).all()


def test_join_suppliers(tmp_path):
    t = pd.DataFrame({"site_id": ["A", "B", "C", "D"], "review_if_self_supplied": [True, True, True, False]})
    p = tmp_path / "s.csv"
    pd.DataFrame({"site_id": ["A", "B", "D"], "supplier_class": ["public_or_authority", "self_supplied",
                                                                  "unknown"]}).to_csv(p, index=False)
    j, c = SB.join_suppliers(t, p)
    assert c["n_review_if_self_supplied_and_public_or_authority"] == 1
    assert c["n_review_if_self_supplied_and_self_supplied"] == 1
    assert c["n_review_if_self_supplied_and_unknown"] == 1          # C missing from file -> unknown
    assert c["n_sites_missing_from_supplier_file"] == 1
