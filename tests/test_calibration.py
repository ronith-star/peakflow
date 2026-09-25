"""The primary (peak-day) calibration in results/calibration.json reproduces its recorded targets,
and those targets match the ones currently defined in reuse_ready.calibration (staleness check)."""
import json

import numpy as np
import pytest

from reuse_ready.calibration import TARGETS, load_kttn, model_stats
from reuse_ready.paths import PROCESSED, RESULTS

pytestmark = pytest.mark.skipif(not (RESULTS / "calibration.json").exists()
                                or not (PROCESSED / "weather_hourly.parquet").exists(),
                                reason="calibration or weather data not built")


def _primary():
    return json.loads((RESULTS / "calibration.json").read_text())["primary"]


def test_primary_reproduces_recorded_targets():
    p = _primary()
    tg = p["targets"]
    assert p["interpretation"] == "peak_day"
    s = model_stats([p["t_sw_c"], p["gamma"], p["p_it_mw"]], load_kttn(), p["twb_ref_c"])
    assert abs(s["avg_gpd"] / tg["avg_gpd"] - 1) < 0.01
    assert abs(s["peak_day_gpd"] / tg["peak_gpd"] - 1) < 0.01
    assert abs(s["wet_hour_frac"] / tg["wet_hour_frac"] - 1) < 0.01
    assert np.isclose(s["avg_gpd"], p["achieved"]["avg_gpd"], rtol=1e-9)


def test_calibration_json_matches_current_targets():
    """Fails when calibration.py targets change but results/calibration.json was not regenerated."""
    tg = _primary()["targets"]
    for k in ("avg_gpd", "peak_gpd", "wet_hour_frac"):
        assert tg[k] == pytest.approx(TARGETS[k]), f"{k}: json {tg[k]} vs calibration.TARGETS {TARGETS[k]}"
