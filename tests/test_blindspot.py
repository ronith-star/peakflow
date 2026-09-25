"""Blind-spot grid sanity: air-cooled uses no makeup; tower > hybrid at every IT load."""
import pytest

from reuse_ready import blindspot as bs
from reuse_ready.paths import PROCESSED, RESULTS

pytestmark = pytest.mark.skipif(not (PROCESSED / "flow_daily.parquet").exists()
                                or not (RESULTS / "calibration.json").exists(),
                                reason="flow or calibration outputs not built")


@pytest.fixture(scope="module")
def inputs():
    return bs.load_inputs()


def test_air_cooled_zero(inputs):
    w, cal, _, _ = inputs
    for mw in bs.MW_GRID:
        d = bs.daily_series(w, bs.config_params(mw, "air_cooled_chiller", cal))
        assert d.dropna().abs().max() == 0.0


def test_tower_exceeds_hybrid(inputs):
    w, cal, q7q10, flow = inputs
    for mw in bs.MW_GRID:
        tw = bs.summarize(bs.daily_series(w, bs.config_params(mw, "evaporative_tower", cal)), flow, q7q10)
        hy = bs.summarize(bs.daily_series(w, bs.config_params(mw, "hybrid", cal)), flow, q7q10)
        assert tw["annual_mean_gpd"] > hy["annual_mean_gpd"] > 0
        assert tw["r30_max_gpd"] > hy["r30_max_gpd"]
        assert tw["peak_day_max_gpd"] > hy["peak_day_max_gpd"]


def test_headline_consistency():
    import pandas as pd

    t = pd.read_csv(RESULTS / "blindspot_raw.csv")
    assert len(t) == 12
    strict = t.below_trigger_30day & (t.peak_day_max_gpd > bs.TRIGGER_GPD)
    assert (strict == t.blind_spot_strict).all()
    assert (t.r30_max_gpd[t.below_trigger_30day] <= bs.TRIGGER_GPD).all()


def test_sig3():
    assert bs.sig3(751_422.6) == "751,000"
    assert bs.sig3(98_794.9) == "98,800"
    assert bs.sig3(7.6) == "7.60"
    assert bs.sig3(0.0) == "0"
    assert bs.sig3(float("nan")) == "n/a"
    assert bs.sig3(1794.85) == "1,790"


def test_displayed_values_identical():
    """results CSV, figure data CSV, Markdown table and the drawn PNG cells carry the same strings."""
    import pandas as pd

    from reuse_ready.paths import FIGURES

    a = pd.read_csv(RESULTS / "table_blindspot.csv", dtype=str, keep_default_na=False)
    b = pd.read_csv(FIGURES / "table_blindspot_data.csv", dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(a, b)
    md = (RESULTS / "table_blindspot.md").read_text()
    rows = [ln for ln in md.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
    cols = [c[0] for c in bs.DISPLAY_COLUMNS]
    assert len(rows) == len(a) == 13  # 12 configurations + Falls reference row
    for ln, (_, r) in zip(rows, a.iterrows()):
        cells = [c.strip().strip("*") for c in ln.strip().strip("|").split("|")]
        assert cells == [r[c] for c in cols]
    text = md + (FIGURES / "table_blindspot_caption.md").read_text()
    assert "\u2014" not in text and "\u2013" not in text


def test_figure_draws_display_strings():
    import matplotlib

    matplotlib.use("Agg")
    t = bs.run()
    fig, _ = bs.render_figure(t, stem="_test_table_blindspot")
    assert len(fig._drawn_cells) == 13
    from reuse_ready.paths import FIGURES

    for ext in ("png", "pdf"):
        (FIGURES / f"_test_table_blindspot.{ext}").unlink()
    df = bs.display_frame(t)
    cols = [c[0] for c in bs.DISPLAY_COLUMNS]
    assert fig._drawn_cells == df[cols].values.tolist()
    r = fig.canvas.get_renderer()
    texts = [(x, x.get_window_extent(r)) for x in fig.findobj(matplotlib.text.Text)
             if x.get_text().strip() and x.get_visible()]
    fb = fig.bbox
    assert not [x.get_text() for x, b in texts if b.x0 < fb.x0 or b.x1 > fb.x1 or b.y0 < fb.y0 or b.y1 > fb.y1]
    assert not [(a.get_text(), c.get_text()) for i, (a, ba) in enumerate(texts) for c, bc in texts[i + 1:]
                if ba.overlaps(bc)]


def test_two_mechanisms():
    import pandas as pd

    t = pd.read_csv(RESULTS / "blindspot_raw.csv")
    assert (~t.review_if_purchased).all()
    assert (t.review_if_self_supplied == ~t.below_trigger_30day).all()
    d = pd.read_csv(RESULTS / "table_blindspot.csv", dtype=str, keep_default_na=False)
    falls = d.iloc[-1]
    assert falls["Configuration"] == bs.FALLS_LABEL
    assert falls[bs.DISPLAY_COLUMNS[2][0]] == "135,000" + bs.FN_FALLS
    assert falls[bs.DISPLAY_COLUMNS[5][0]] == "4,400,000" + bs.FN_FALLS
    col = {c[0].split("{")[0]: c[0] for c in bs.DISPLAY_COLUMNS}
    self_col = next(c[0] for c in bs.DISPLAY_COLUMNS if c[0].startswith("Review if self-supplied"))
    buy_col = next(c[0] for c in bs.DISPLAY_COLUMNS if c[0].startswith("Review if purchased"))
    assert falls[self_col] == "Yes" and falls[buy_col] == "No"
    assert falls[bs.SHADE_COL] == "No"  # reference row never counted


def test_hybrid_params_read_from_calibration():
    import json

    cal = json.loads((RESULTS / "calibration.json").read_text())
    for name, path in bs.CALIBRATIONS.items():
        c = cal
        for k in path:
            c = c[k]
        t = pd_read(RESULTS / bs.RAW_FILES[name])
        assert t.hybrid_gamma.iloc[0] == c["gamma"] and t.hybrid_t_sw_c.iloc[0] == c["t_sw_c"]


def pd_read(path):
    import pandas as pd

    return pd.read_csv(path)


def test_days_column_uses_30day_window_and_valid_years():
    """The trigger-test days column counts days whose trailing 30-day average exceeds the trigger, divided by
    valid window-years; the single-day count is a separate column (audit G06)."""
    import pandas as pd

    t = pd.read_csv(RESULTS / "blindspot_raw.csv")
    w, cal, q, fl = bs.load_inputs("primary")
    h = t[(t.architecture == "hybrid") & (t.it_load_mw == 100)].iloc[0]
    d = bs.daily_series(w, bs.config_params(100, "hybrid", cal))
    r30 = d.rolling(bs.WINDOW_DAYS, min_periods=bs.WINDOW_MIN_VALID).mean()
    exp = (r30 > bs.TRIGGER_GPD).sum() / (r30.notna().sum() / 365.25)
    assert h.days_per_year_30day_window_over_trigger == pytest.approx(exp, rel=1e-9)
    assert h.days_per_year_over_trigger == pytest.approx((d > bs.TRIGGER_GPD).sum() / (d.notna().sum() / 365.25), rel=1e-9)
    names = [c[0] for c in bs.DISPLAY_COLUMNS]
    assert any(n.startswith("Days/yr, 30-day avg") for n in names)
    assert any("not the trigger test" in n for n in names)
