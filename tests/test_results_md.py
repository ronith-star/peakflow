"""results.md is hand-written prose; this test ties its key numbers to the generated result files so a rerun
that changes a number fails until the prose is updated (audit G08). It also checks the prose rules: a citation
key in every sentence that contains a digit, no em or en dashes, no exclamation marks."""
import json
import re

import pandas as pd
import pytest

from peakflow.paths import RESULTS

MD = RESULTS / "results.md"
pytestmark = pytest.mark.skipif(not MD.exists() or not (RESULTS / "supply_summary.json").exists(),
                                reason="results not built")


# A sentence may not start with a numeral, so counts that open a sentence are written as words.
_WORDS = {n: w for n, w in enumerate("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
                                     "Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen Twenty".split())}


def _j(name):
    return json.loads((RESULTS / name).read_text())


def _fmt(v, nd=0):
    return f"{v:,.{nd}f}"


def expected_phrases():
    s, c, b = _j("supply_summary.json"), _j("calibration.json"), _j("blindspot_summary.json")["primary"]
    w, f = _j("falls_implied_wue.json"), _j("flow_stats.json")
    hi, bins = s["headline_capacity_independent"], s["covered_it_bins"]
    acs = s["assumed_capacity_sensitivity"]
    ss = pd.read_csv(RESULTS / "supply_screen.csv").set_index("site_id")
    fal = ss.loc["DRB12"]
    raw = pd.read_csv(RESULTS / "blindspot_raw.csv")
    hyb = raw[raw.architecture == "hybrid"].sort_values("it_load_mw")
    p, a = c["primary"], c["alternative"]
    lo, hi_mw = b["hybrid_strict_band_mw"]
    ph = [
        f"{hi['n_within_10mi_of_eligible_potw']} lie within 10 miles", f"{_WORDS.get(hi['n_no_published_capacity'], hi['n_no_published_capacity'])} of the 24 sites do not publish",
        f"{bins['over 200 MW']} sites exceed 200 MW", f"{bins['50 to 200 MW']} fall between 50 and 200 MW",
        f"{bins['no eligible plant within 10 mi']} have no eligible plant within 10 miles",
        _fmt(s["demand_rates"]["peak_day_gpd_per_mw"]) + " gal/day per MW",
        f"moves by {acs['matchable_spread_max_minus_min']} sites",
        *[f"| {mw} MW | {acs[f'{mw}MW']['matchable']} | {acs[f'{mw}MW']['partial']} | {acs[f'{mw}MW']['none']} |" for mw in (50, 100, 200)],
        f"{fal.distance_mi:.2f} miles away with a median flow of {fal.plant_median_flow_mgd:.2f} million gal/day, enough for {fal.covered_it_mw:,.0f} MW",
        f"{fal.same_state_distance_mi:.2f} miles away with {fal.same_state_median_flow_mgd:.2f} million gal/day, enough for {fal.same_state_covered_it_mw:,.0f} MW",
        "counts to {matchable}, {partial} and {none}".format(**s["sensitivity"]["a_non_potw_eligible"]),
        f"part-load exponent of {p['gamma']:.3f} and {p['p_it_mw']:.0f} MW", f"{a['p_it_mw']:.0f} MW and {a['gamma']:.3f}",
        f"{p['t_sw_c']:.1f} °C",
        f"{c['sensitivity_wet_2pct']['peak_day']['achieved']['peak_gpd'] / 1e6:.2f} million gal/day",
        f"near {round(c['sensitivity_wet_2pct']['design_rate']['achieved']['avg_gpd'], -3):,.0f} gal/day",
        f"about {w['peak_to_average_ratio']:.0f} times",
        f"{w['implied']['peak_day_fit_primary']['implied_wue_l_per_kwh']:.4f} L/kWh on the primary fit",
        f"{w['implied']['design_rate_fit_sensitivity']['implied_wue_l_per_kwh']:.4f} on the design-rate",
        f"{w['implied']['unverified_253MW']['implied_wue_l_per_kwh']:.4f} at 253 MW",
        f"{w['implied']['wet_2pct_peak_day_achieved_avg']['implied_wue_l_per_kwh']:.4f} for the 2 percent case",
        f"about {100 * w['implied']['peak_day_fit_primary']['implied_wue_l_per_kwh'] / 0.36:.0f} percent of the United States",
        f"about {100 * w['implied']['peak_day_fit_primary']['implied_wue_l_per_kwh'] / 0.27:.0f} percent of Microsoft",
        f"between {lo:.2f} and {hi_mw:.1f} MW", f"{b['n_averaging_blind_spot_loose_annual_mean']} of 12 would qualify",
        f"{b['n_review_if_self_supplied']} of the 12".replace("8 of", "Eight of"),
        f"{p['diagnostics']['max_30day_avg_gpd'] / 1e6:.2f} million gal/day",
        f"{f['seven_q_ten']['record_provisional_days'] if 'record_provisional_days' in f['seven_q_ten'] else f['seven_q_ten']['primary_full_record']['provisional_days_in_years_used']} provisional days",
        f"{f['seven_q_ten']['sensitivity_approved_only']['value_cfs']:,.0f} cfs",
        f"{f['seven_q_ten']['primary_full_record']['value_cfs']:,.0f} cfs",
    ]
    days = [f"{v:.3g}" for v in hyb.days_per_year_30day_window_over_trigger]
    ph.append(f"on {days[0]}, {days[1]}, {days[2]} and {days[3]} days per year")
    sh = hyb.share_over_days_flow_below_doy_p25 * 100
    ph.append(f"on {sh.min():.1f} to {sh.max():.1f} percent of days")
    return ph


def test_numbers_match_results():
    text = MD.read_text()
    missing = [p for p in expected_phrases() if p not in text]
    assert not missing, f"results.md is stale; phrases not found: {missing}"


def test_prose_rules():
    text = MD.read_text()
    assert "\u2014" not in text and "\u2013" not in text and "!" not in text
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith(("#", "|"))]
    sentences = [s for ln in body for s in re.split(r"(?<=[.])\s+(?=[A-Z])", re.sub(r"^\d+\.\s+", "", ln))]
    unkeyed = [s for s in sentences if re.search(r"\d", re.sub(r"\[[^\]]+\]", "", s)) and not re.search(r"\[[a-z0-9_]+", s)]
    assert not unkeyed, unkeyed


# Plain-prose rule (2026-09-25): no semicolons, em dashes or en dashes in the written documents and captions.
# Verbatim regulatory quotes in sources.md end before the semicolon that closes each CFR item.
from peakflow.paths import ROOT as _ROOT  # noqa: E402

PROSE_FILES = ["README.md", "LICENSES.md", "results/results.md", "sources.md", "results/brief_numbers.md"]


def _prose_files():
    fs = [_ROOT / f for f in PROSE_FILES] + sorted((_ROOT / "figures").glob("*_caption.md"))
    return [f for f in fs if f.exists()]


@pytest.mark.parametrize("path", _prose_files(), ids=lambda p: p.relative_to(_ROOT).as_posix())
def test_prose_no_semicolons_or_dashes(path):
    bad = [(i, ln[:80]) for i, ln in enumerate(path.read_text().splitlines(), 1)
           if ";" in ln or "\u2014" in ln or "\u2013" in ln]
    assert not bad, bad
