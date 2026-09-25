"""Falls duration curve and drought coincidence (work order items 9, 10): statistics, percentile ranks, intervals."""
import json

import numpy as np
import pandas as pd
import pytest

from reuse_ready import falls_figures as F
from reuse_ready.paths import FIGURES, PROCESSED, RESULTS

pytestmark = pytest.mark.skipif(not (PROCESSED / "flow_daily.parquet").exists()
                                or not (RESULTS / "calibration.json").exists(),
                                reason="flow or calibration outputs not built")


@pytest.fixture(scope="module")
def series():
    return F.falls_daily("primary")


def test_weibull_positions():
    s = pd.Series([3.0, np.nan, 1.0, 2.0, 0.0], index=pd.date_range("2020-01-01", periods=5))
    ex = F.weibull_exceedance(s)
    assert ex.makeup_gpd.tolist() == [3.0, 2.0, 1.0, 0.0]
    assert np.allclose(ex.pct_exceeded, [20, 40, 60, 80])


def test_duration_stats_match_calibration(series):
    d, cal = series
    st = F.duration_stats(d)
    assert st["n_valid_days"] + st["n_nan_days"] == st["n_days_total"] == 7305
    assert st["mean_gpd"] == pytest.approx(cal["targets"]["avg_gpd"], rel=1e-9)
    assert st["max_gpd"] == pytest.approx(cal["targets"]["peak_gpd"], rel=1e-9)
    assert st["peak_to_average_ratio"] == pytest.approx(32.6, abs=0.05)
    assert 0 < st["share_zero_days"] < 1
    assert st["pct_days_above_peak_4400000"] == 0.0
    assert st["pct_days_above_trigger_100000"] > st["pct_days_above_avg_135000"]


def test_doy_rank_agrees_with_p25():
    flow = pd.read_parquet(PROCESSED / "flow_daily.parquet")[["date", "flow_cfs", "p25_2005_2024"]]
    rank = F.doy_percentile_rank(flow)
    assert rank.between(0, 100).all() and len(rank) == 7305
    f = flow.set_index("date").reindex(rank.index)
    # 20 values per ordinary calendar day: rank < 25 selects exactly the flows below numpy's p25 (non-leap days)
    nonleap = ~rank.index.strftime("%m-%d").isin(["02-28", "02-29", "03-01"])
    a = (rank[nonleap] < 25).to_numpy()
    b = (f.flow_cfs[nonleap] < f.p25_2005_2024[nonleap]).to_numpy()
    assert (a == b).mean() > 0.995


def test_table_interval_rules():
    dr = pd.DataFrame([{"period": "x", "enter_watch": "2001-01-01", "enter_warning": "2001-02-01",
                        "end_watch_warning": "", "enter_drought": "", "declare_emergency": "2001-03-01",
                        "end_emergency": ""}])
    iv = F.table_intervals(dr, end_close=pd.Timestamp("2001-12-31"))
    w = iv[iv.kind == "warning"].iloc[0]
    e = iv[iv.kind == "emergency"].iloc[0]
    assert w.end == pd.Timestamp("2001-03-01") and "next later" in w.end_rule
    assert e.end == pd.Timestamp("2001-12-31") and "analysis end" in e.end_rule


def test_drought_intervals_window():
    iv = F.drought_intervals()
    assert (iv.source == "table").sum() == 0          # the basinwide table has no warning/emergency in 2005-2024
    assert (iv.end_clipped <= F.B.END).all() and (iv.start_clipped >= F.B.START).all()
    assert set(iv.kind) <= {"warning", "emergency"}


def test_outputs_consistent():
    s = json.loads((RESULTS / "falls_figures_summary.json").read_text())
    for k in ("falls_duration_curve", "drought_coincidence"):
        assert s["figure_checks"][k]["text_text"] == [] and s["figure_checks"][k]["text_outside_figure"] == []
        for e in ("png", "pdf", "svg"):
            assert (FIGURES / f"{k}.{e}").exists()
        cap = (FIGURES / f"{k}_caption.md").read_text()
        assert "**Figure" in cap and "\u2014" not in cap and "\u2013" not in cap and "!" not in cap
    c = s["coincidence"]
    assert c["share_top5_below_flow_p25"] == pytest.approx(c["share_top5_below_flow_p25_check_vs_p25_cfs"], abs=0.02)
    dc = pd.read_csv(FIGURES / "drought_coincidence_data.csv")
    assert int(dc.top5pct_demand.sum()) == c["n_top5_days"]
    dd = pd.read_csv(FIGURES / "falls_duration_curve_data.csv")
    assert int((dd.element == "daily_makeup").sum()) == s["duration"]["n_valid_days"]
