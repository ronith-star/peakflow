"""Tests for reuse_ready.uncertainty (work order item 14) and its three figures."""
import json

import numpy as np
import pandas as pd
import pytest

from reuse_ready import uncertainty as U
from reuse_ready.paths import FIGURES, RESULTS

BUILT = (RESULTS / "peak_uncertainty.csv").exists() and (RESULTS / "peak_uncertainty.json").exists()
built = pytest.mark.skipif(not BUILT, reason="uncertainty results not built")
FIG_STEMS = ("peak_uncertainty", "sites_mc_ridgeline", "falls_mc_fan")


# ---------------------------------------------------------------- unit tests (no results needed)
def test_conversion_constant():
    assert U.GPD_PER_MW_PER_LKWH == pytest.approx(1000 * 24 / 3.785411784)
    assert U.GPD_PER_MW_PER_LKWH == pytest.approx(6340.13, abs=0.01)


def test_quantile_draw_hits_five_numbers():
    five = (0.0, 0.21, 0.42, 0.72, 1.56)
    assert np.allclose(U._quantile_draw(np.array([0, .25, .5, .75, 1.0]), five), five)
    assert U._quantile_draw(np.array([0.0]), (-0.02, 0.1, 0.2, 0.3, 0.4))[0] == 0.0   # negative whisker clipped


def test_grouped_weights_sum_to_one_and_every_system_grouped():
    for bar in U.FIG42_SHARES:
        assert set(U.FIG42_SHARES[bar]) <= set(U.LBNL_SYSTEM_GROUPS)
        w = U.grouped_weights(bar)
        assert sum(w.values()) == pytest.approx(1.0)
    assert U.grouped_weights("hyperscale")["hybrid"] > 0.9


def _toy_conv():
    return {"evaporative_tower": {"peak_to_average": 1.0, "peak_day_gpd_per_mw": 15000.0},
            "hybrid": {"peak_to_average": 32.6, "peak_day_gpd_per_mw": 13285.6},
            "variable_ratio_lookup": {"t_sw_c": [0, 1], "phi_mean": [0.01, 0.2], "phi_peak": [0.5, 1.0]}}


def test_per_mw_draws_air_cooled_zero_and_cap_holds():
    Uu = U.uniforms(2000, 3, seed=1)
    sc = U.Scenario("t", {"evaporative_tower": 0.3, "hybrid": 0.5, "air_cooled_chiller": 0.2})
    pm = U.per_mw_draws(Uu, sc, _toy_conv())
    assert (pm.loc[pm.arch == "air_cooled_chiller", "gpd_per_mw"] == 0).all()
    full = 15000.0 * pm.pue / 1.2
    assert (pm.loc[pm.arch == "hybrid", "gpd_per_mw"] <= full[pm.arch == "hybrid"] + 1e-9).all()
    assert pm.pue.between(*U.PUE_RANGE).all()
    share = pm.arch.value_counts(normalize=True)
    assert share["hybrid"] == pytest.approx(0.5, abs=0.04)


def test_seed_reproducible():
    a, b = U.uniforms(100, 2, seed=U.SEED), U.uniforms(100, 2, seed=U.SEED)
    assert all(np.array_equal(a[k], b[k]) for k in a)


def test_site_it_draws_stated_fixed_unstated_from_pool():
    ss = pd.DataFrame({"capacity_basis": ["stated_campus_MW_div_PUE", "assumed_100MW_IT", "stated_campus_MW_div_PUE"],
                       "it_mw": [250.0, 100.0, 1000.0]})
    Uu = U.uniforms(500, 3, seed=2)
    it, pool = U.site_it_draws(ss, Uu, U.Scenario("t", {}))
    assert (it[0] == 250).all() and (it[2] == 1000).all()
    assert set(np.unique(it[1])) <= {250.0, 1000.0}
    it2, _ = U.site_it_draws(ss, Uu, U.Scenario("t", {}, unstated_capacity="fixed_100"))
    assert (it2[1] == 100).all()


# ---------------------------------------------------------------- results
@built
def test_results_csv_schema_and_sites():
    d = pd.read_csv(RESULTS / "peak_uncertainty.csv")
    ss = pd.read_csv(RESULTS / "supply_screen.csv")
    for c in ("site_id", "name", "it_mw_basis", "p10_peak_day_gpd", "p50_peak_day_gpd", "p90_peak_day_gpd",
              "plant_median_gpd", "covers_p50", "covers_p90", "prob_covered"):
        assert c in d.columns
    assert len(d) == 24 and set(d.site_id) == set(ss.site_id)
    assert (d.p10_peak_day_gpd <= d.p50_peak_day_gpd).all() and (d.p50_peak_day_gpd <= d.p90_peak_day_gpd).all()
    assert d.prob_covered.between(0, 1).all()
    assert (~d.covers_p90 | d.covers_p50).all()
    m = d.merge(ss[["site_id", "plant_median_flow_mgd"]], on="site_id")
    assert np.allclose(m.plant_median_gpd.fillna(-1), (m.plant_median_flow_mgd * 1e6).fillna(-1))
    assert list(d.map_number) == list(range(1, 25))


@built
def test_results_json_records_seed_and_sources():
    j = json.loads((RESULTS / "peak_uncertainty.json").read_text())
    assert j["seed"] == U.SEED and j["n_draws"] == U.N_DRAWS == 10_000
    assert "shehabi_2024" in j["distributions"]["wue_source"]
    assert j["distributions"]["pue"]["low"] == 1.15 and j["distributions"]["pue"]["high"] == 1.35
    assert j["conversion"]["model"]["evaporative_tower"]["peak_to_average"] == pytest.approx(1.0)
    rates = json.loads((RESULTS / "supply_summary.json").read_text())["demand_rates"]
    assert j["conversion"]["model"]["hybrid"]["peak_day_gpd_per_mw"] == pytest.approx(rates["peak_day_gpd_per_mw"])
    p = j["scenarios"]["primary"]
    d = pd.read_csv(RESULTS / "peak_uncertainty.csv")
    assert p["n_covers_p90"] == int(d.covers_p90.sum())
    assert j["ridgeline_p90_above_plant"]["n"] == p["n_p90_above_plant"]


@built
def test_digitized_constants_match_pdf():
    if not U.LBNL_PDF.exists():
        pytest.skip("LBNL PDF not present")
    d = U.digitize_figure_4_4()
    for k, v in U.LBNL_WUE.items():
        assert np.allclose(np.maximum(d["wue"][k], 0), v, atol=0.011), k
    for k, v in U.LBNL_PUE.items():
        assert np.allclose(d["pue"][k], v, atol=0.002), k
    g = U.digitize_figure_4_2()
    for bar, sh in U.FIG42_SHARES.items():
        for k, v in sh.items():
            assert g[bar][k] == pytest.approx(v, abs=0.07), (bar, k)


@built
def test_fan_daily_matches_cooling_model():
    from reuse_ready import blindspot as B
    x, _ = U._falls_weather()
    cal = json.loads((RESULTS / "calibration.json").read_text())
    P = U.fan_parameters(cal, n=2, seed=5)
    D = U.fan_daily(x, P)
    w, c, _, _ = B.load_inputs("primary")
    for i, r in P.iterrows():
        p = B.config_params(r.p_it_mw, "hybrid", {**c, "gamma": r.gamma})
        p.pue = r.pue
        s = B.daily_series(w, p)
        s = s[s.index.year == r.weather_year]
        ref = np.full(366, np.nan)
        ref[s.index.dayofyear - 1] = s.values
        assert np.allclose(ref, D[i], equal_nan=True, rtol=1e-9, atol=1e-6)


# ---------------------------------------------------------------- figures
@pytest.mark.skipif(not all((FIGURES / f"{s}.png").exists() for s in FIG_STEMS), reason="figures not built")
class TestFigures:
    @pytest.mark.parametrize("stem", FIG_STEMS)
    def test_files_exist(self, stem):
        for ext in ("png", "pdf", "svg"):
            assert (FIGURES / f"{stem}.{ext}").stat().st_size > 1000
        cap = (FIGURES / f"{stem}_caption.md").read_text()
        assert "**Figure X.**" in cap
        assert "\u2014" not in cap and "\u2013" not in cap and "!" not in cap
        assert (FIGURES / f"{stem}_data.csv").exists()

    def test_range_bar_rows(self):
        d = pd.read_csv(FIGURES / "peak_uncertainty_data.csv")
        assert len(d) == 24 and d.site_id.nunique() == 24
        assert d.p50_peak_day_gpd.is_monotonic_increasing
        assert set(d.right_margin_note.fillna("")) <= {"", "P90 exceeds plant", "Plant covers P90", "No plant within 10 mi"}

    def test_ridgeline_rows(self):
        d = pd.read_csv(FIGURES / "sites_mc_ridgeline_data.csv")
        s = d[d.element == "site_summary"]
        assert len(s) == 24 and s.site_id.nunique() == 24
        assert s.median_gpd.is_monotonic_increasing
        c = d[d.element == "density_curve"]
        assert c.groupby("site_id").size().eq(400).all()
        j = json.loads((RESULTS / "peak_uncertainty.json").read_text())
        assert int(s.p90_above_plant.sum()) == j["ridgeline_p90_above_plant"]["n"]

    def test_fan_traces(self):
        d = pd.read_csv(FIGURES / "falls_mc_fan_data.csv")
        t = d[d.element == "trace"]
        assert t.trace.nunique() == 300 and t.draw.nunique() == 300
        assert len(t) == 300 * 366
        assert (t.plotted_gpd.dropna() >= U.FAN_FLOOR_GPD).all()
        assert t.weather_year.between(2005, 2024).all()
        for q in ("p10_all_draws", "p50_all_draws", "p90_all_draws"):
            assert (d.element == q).sum() == 366

    def test_figure_checks_clean(self):
        c = json.loads((RESULTS / "peak_uncertainty_figure_check.json").read_text())
        for stem in FIG_STEMS:
            assert c[stem]["text_overlaps"] == []
            assert c[stem]["size_mm"][0] == 180.0
        assert c["falls_mc_fan"]["size_mm"][1] == 80.0
