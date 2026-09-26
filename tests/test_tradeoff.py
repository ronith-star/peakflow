"""Water-energy tradeoff: LBNL Figure 4.4 digitization, unit conversions, table invariants, figure checks."""
import numpy as np
import pandas as pd
import pytest

from peakflow import tradeoff as tr
from peakflow.paths import PROCESSED, RESULTS

needs_pdf = pytest.mark.skipif(not tr.LBNL_PDF.exists(), reason="data/raw/lbnl_2024.pdf not present")
needs_model = pytest.mark.skipif(not (PROCESSED / "weather_hourly.parquet").exists()
                                 or not (RESULTS / "calibration.json").exists()
                                 or not (PROCESSED / "flow_daily.parquet").exists(),
                                 reason="weather or calibration outputs not built")


def test_conversions():
    assert tr.KWH_PER_MW_YEAR == 8_760_000
    assert tr.energy_kwh_per_mw_year(1.2) == pytest.approx(1_752_000)
    assert tr.wue_to_gal_per_mw_year(1.0) == pytest.approx(8_760_000 / 3.785411784)
    assert tr.gal_per_mw_year_to_wue(tr.wue_to_gal_per_mw_year(0.37)) == pytest.approx(0.37)


@pytest.fixture(scope="module")
def lbnl():
    return tr.digitize_fig44()


@needs_pdf
def test_fig44_digitization(lbnl):
    # box-plot order on both axes, and PUE within the axis (1.0 to 2.5)
    for pan in ("pue", "wue"):
        v = lbnl[[f"{pan}_{k}" for k in ("whisker_low", "q1", "median", "q3", "whisker_high")]].to_numpy()
        assert (np.diff(v, axis=1) >= 0).all()
    assert lbnl.pue_whisker_low.min() >= 1.0 and lbnl.pue_whisker_high.max() <= 2.5
    # anchor readings, checked visually on an overlay (one pixel = 0.005 PUE, 0.014 L/kWh)
    L = lbnl.loc["large_waterside_econ_wcc"]
    assert L.pue_median == pytest.approx(1.12, abs=0.01) and L.wue_median == pytest.approx(2.18, abs=0.03)
    A = lbnl.loc["midsize_air_cooled_chiller"]
    assert A.pue_median == pytest.approx(1.83, abs=0.01) and A.wue_median == 0.0
    # LBNL: evaporative systems more energy efficient than air-cooled chillers (p. 45)
    assert lbnl.loc["midsize_water_cooled_chiller"].pue_median < A.pue_median


@needs_pdf
@needs_model
def test_table_invariants(lbnl):
    t = tr.build_table(lbnl).set_index("arch_key")
    for k, r in t.iterrows():
        assert r.water_low <= r.water_central <= r.water_high, k
        assert r.energy_low <= r.energy_central <= r.energy_high, k
    assert t.loc["air_cooled_chiller", "water_high"] == 0.0
    assert t.loc["evaporative_tower", "water_central"] > t.loc["hybrid", "water_central"] > 0
    assert t.loc["air_cooled_chiller", "energy_central"] > t.loc["hybrid", "energy_central"]
    # Falls point = 135,000 gal/day x 365 / calibrated P_IT; the hybrid is calibrated to it
    cal = tr.model_annual_water_per_mw()["calibration"]
    f = t.loc["falls_township"]
    assert f.water_central == pytest.approx(135_000 * 365 / cal["p_it_mw"])
    assert f.energy_central == pytest.approx(0.2 * 8_760_000)
    assert t.loc["hybrid", "water_central"] == pytest.approx(f.water_central, rel=0.01)


@needs_pdf
@needs_model
def test_figure_clean(lbnl):
    t = tr.build_table(lbnl)
    fig, axes, texts, data = tr.render_figure(t)
    assert tr.overlap_report(fig) == []
    assert tr.symbol_label_hits(fig, axes, texts, t) == []
    assert min(tr.edge_margins_mm(fig).values()) >= tr.MIN_EDGE_MM
    w, h = fig.get_size_inches() * 25.4
    assert w == pytest.approx(85.0)
    assert len(data) == int(t.plotted.sum())
