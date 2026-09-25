"""Tests for reuse_ready.cycles and reuse_ready.wqp (work order items 12 and 13)."""
import json
import math

import numpy as np
import pandas as pd
import pytest
import requests

from reuse_ready import cycles as C
from reuse_ready import wqp as W


def test_hem_constants_interpolate_table33():
    k = C.hem_logk(30.0)
    assert k["log_ks"] == pytest.approx(1.837)
    assert k["log_k1"] == pytest.approx(-6.327)
    assert C.hem_logk(35.0)["log_ks"] == pytest.approx((1.837 + 1.685) / 2)


def test_lsi_increases_with_cycles_and_temperature():
    a = C.lsi(2.0, 60.0, 131.0, 730.0)["lsi"]
    b = C.lsi(6.0, 60.0, 131.0, 730.0)["lsi"]
    assert b > a
    assert C.lsi(4.0, 60.0, 131.0, 730.0, t_c=40.0)["lsi"] > C.lsi(4.0, 60.0, 131.0, 730.0, t_c=20.0)["lsi"]


def test_lsi_hand_calculation():
    # pH fixed at the cap; I -> 0 limit gives pHs = log Ks - log[Ca] - log[HCO3] with molar concentrations.
    r = C.lsi(1.0, 40.078, 50.04, 1e-9, ph_cap=8.0)
    assert r["ph_s"] == pytest.approx(C.hem_logk()["log_ks"] + 3.0 + 3.0, abs=1e-6)
    assert r["lsi"] == pytest.approx(8.0 - r["ph_s"], abs=1e-9)


def test_equilibrium_ph_air():
    # {HCO3-} = 1 mM at I -> 0: pH = -(logK1 + logKh + log PCO2) + log{HCO3-}
    r = C.lsi(1.0, 40.078, 50.04, 1e-9, ph_cap=99.0)
    k = C.hem_logk()
    assert r["ph_eq"] == pytest.approx(-(k["log_k1"] + k["log_kh"] + math.log10(C.PCO2_ATM)) - 3.0, abs=1e-6)


def test_cycles_lsi_root():
    c = C.cycles_lsi(60.0, 131.0, 730.0)
    assert 1.0 < c < 200.0
    assert C.lsi(c, 60.0, 131.0, 730.0)["lsi"] == pytest.approx(C.LSI_MAX, abs=1e-6)


def test_water_balance_identities():
    wb = C.water_balance(4.0)
    assert wb["makeup_per_evap"] == pytest.approx(4 / 3)
    assert wb["blowdown_per_evap"] == pytest.approx(1 / 3)
    assert wb["min_return_flow_pct"] == pytest.approx(25.0)
    assert wb["makeup_per_evap"] - wb["blowdown_per_evap"] == pytest.approx(1.0)
    assert np.isnan(C.water_balance(0.9)["makeup_per_evap"])


def test_binding_is_minimum():
    cc = {"silica": 10.0, "chloride": 5.0, "phosphate": 2.0, "lsi": 7.0}
    assert C.binding(cc) == ("phosphate", 2.0)
    assert C.binding(cc, ["silica", "chloride", "lsi"]) == ("chloride", 5.0)


def _plant(**kw):
    base = dict(npdes_id="X1", name="TEST", state="PA", lat=40.0, lon=-75.0, receiving_water="R", in_drb=True,
                median_flow_mgd=1.0, chloride_mg_l=np.nan, chloride_n_months=np.nan, tds_mg_l=np.nan,
                tds_n_months=np.nan, total_p_mg_l=np.nan, total_p_n_months=np.nan, site_ids="S1",
                same_state_option_for=np.nan)
    base.update(kw)
    return pd.DataFrame([base])


def test_makeup_prefers_dmr_chloride_then_proxy_then_literature():
    m = C.makeup_quality(_plant(chloride_mg_l=200.0), None, 0.3)
    assert m.chloride[0] == 200.0 and m.chloride_basis[0] == "plant DMR"
    m = C.makeup_quality(_plant(tds_mg_l=500.0, tds_n_months=12), None, 0.3)
    assert m.chloride[0] == pytest.approx(150.0) and "assumed" in m.chloride_basis[0]
    m = C.makeup_quality(_plant(), None, 0.3)
    assert m.chloride[0] == C.LIT["chloride"] and m.status[0] == "assumed"


def test_makeup_uses_wqp_when_present():
    wq = pd.DataFrame([{"npdes_id": "X1", "source": "wqp", "silica_median": 9.0, "calcium_median": 30.0,
                        "alkalinity_median": 80.0, "chloride_median": 40.0, "orthophosphate_median": 0.5}])
    m = C.makeup_quality(_plant(), wq, 0.3)
    assert (m.silica[0], m.calcium[0], m.alkalinity[0], m.chloride[0]) == (9.0, 30.0, 80.0, 40.0)
    assert m.status[0] == "measured"


def test_dmr_total_p_converted_to_po4():
    m = C.makeup_quality(_plant(total_p_mg_l=1.0, total_p_n_months=36), None, 0.3)
    assert m.po4[0] == pytest.approx(94.971 / 30.974)


# ---------------------------------------------------------------------------------------------- wqp
class _Resp:
    def __init__(self, status=200, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


def test_wqp_blocked_falls_back(tmp_path):
    def getter(url, params):
        raise requests.exceptions.ProxyError("Tunnel connection failed: 403 Forbidden")
    plants = _plant()
    s = W.run(getter=getter, plants=plants, status_json=tmp_path / "s.json", makeup_csv=tmp_path / "m.csv",
              raw_dir=tmp_path / "wqp")
    assert s["status"] == "unavailable" and s["n_wqp"] == 0
    assert pd.read_csv(tmp_path / "m.csv").source.eq("wqp_unavailable").all()
    assert not (tmp_path / "wqp").exists()
    assert json.loads((tmp_path / "s.json").read_text())["domain"] == W.WQP_HOST


def test_wqp_proxy_403_header_is_unavailable(tmp_path):
    with pytest.raises(W.WQPUnavailable):
        W.fetch_csv(W.STATION_URL, {}, tmp_path / "x.csv",
                    getter=lambda u, p: _Resp(403, b"", {"X-Proxy-Error": "blocked-by-allowlist"}))


def test_wqp_cache_is_offline(tmp_path):
    f = tmp_path / "station_X1.csv"
    f.write_text("MonitoringLocationIdentifier,LatitudeMeasure,LongitudeMeasure\nA,40,-75\n")
    df = W.fetch_csv(W.STATION_URL, {}, f, offline=True, getter=lambda u, p: pytest.fail("network used"))
    assert df.MonitoringLocationIdentifier.tolist() == ["A"]


def test_select_station_most_silica_then_nearest():
    st = pd.DataFrame({"MonitoringLocationIdentifier": ["A", "B", "C", "D"],
                       "MonitoringLocationTypeName": ["Stream", "River/Stream", "Stream", "Well"],
                       "LatitudeMeasure": [40.0, 40.1, 40.01, 40.0], "LongitudeMeasure": [-75.0] * 4})
    res = pd.DataFrame({"MonitoringLocationIdentifier": ["B", "B", "C", "C", "D", "D", "D"],
                        "CharacteristicName": ["Silica"] * 7})
    assert W.select_station(st, res, 40.0, -75.0).MonitoringLocationIdentifier == "C"


def test_summarize_medians():
    res = pd.DataFrame({"MonitoringLocationIdentifier": ["A"] * 3, "CharacteristicName": ["Silica"] * 3,
                        "ResultMeasureValue": ["5", "7", "x"], "ActivityStartDate": ["2001-01-01", "2010-05-05",
                                                                                     "2011-01-01"]})
    s = W.summarize(res, "A")
    assert s["silica_median"] == 6.0 and s["silica_n"] == 2 and s["silica_last"] == "2010-05-05"
    assert s["calcium_n"] == 0


# ---------------------------------------------------------------------------------------------- outputs
def test_results_table_consistent():
    p = C.OUT_CSV
    if not p.exists():
        pytest.skip("results/cycles_by_plant.csv not generated")
    t = pd.read_csv(p)
    assert len(t) == len(W.plant_list())
    assert {"NJ0020923", "PA0026701"} <= set(t.npdes_id)
    cc = t[[f"cycles_{k}" for k in C.CONSTRAINTS]].to_numpy()
    assert np.allclose(t.allowable_cycles, cc.min(axis=1), rtol=1e-3)
    ok = t.allowable_cycles > 1
    assert np.allclose(t.min_return_flow_pct[ok], 100 / t.allowable_cycles[ok], rtol=1e-3)
    assert set(t.status) == {"assumed"} or "measured" in set(t.status)
