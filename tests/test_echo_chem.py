"""N02: Delaware permits report DAILY AV rather than MO AVG; chemistry must use the same fallback as flow."""
from pathlib import Path

import pandas as pd

from reuse_ready import echo

FIX = Path(__file__).parent / "fixtures" / "dmr_DE0020320_chem.csv"


def test_daily_av_fallback_recovers_delaware_chemistry(tmp_path, monkeypatch):
    d = echo._read_dmr(FIX)
    assert not d.empty
    assert "MO AVG" not in set(d.statistical_base_short_desc)
    m = echo.chem_medians(d)
    assert m["tss_n_months"] == 36 and m["bod_n_months"] == 36
    assert 5.0 < m["tss_mg_l"] < 20.0
    assert len(echo.monthly_flow(d)) == 36


def test_mo_avg_preferred_when_present():
    d = echo._read_dmr(FIX)
    mo = d[d.parameter_code == "00530"].copy()
    mo["statistical_base_short_desc"] = "MO AVG"
    mo["value"] = 1.0
    both = pd.concat([d, mo], ignore_index=True)
    assert echo.chem_medians(both)["tss_mg_l"] == 1.0
