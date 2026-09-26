"""Allowable cycles of concentration for municipal-effluent makeup at each matched plant.

For each matched plant (peakflow.wqp.plant_list: the unique plant_npdes_id of results/supply_screen.csv plus
Morrisville Borough STP) the allowable cycles of concentration C is the minimum over four constraints:

  silica     C_Si  = SIO2_LIMIT / SiO2_makeup
  chloride   C_Cl  = CL_LIMIT / Cl_makeup
  phosphate  C_P   = PO4_LIMIT / PO4_makeup
  LSI        C_LSI = the largest C at which LSI(C) <= LSI_MAX

The Langelier saturation index follows Hem (1985): LSI = pH - pH_s, with the calcite solubility constant
Ks = {Ca2+}{HCO3-}/{H+} (Hem 1985, Table 33), so pH_s = log Ks - log{Ca2+} - log{HCO3-}. Activities are molar
concentrations times Debye-Hueckel activity coefficients, -log g = A z^2 sqrt(I) / (1 + B a sqrt(I)) with Hem's
A, B and ion-size parameters a (Hem 1985, p. 15 to 16, Table 5). Ionic strength I = sum(m z^2)/2 is computed
from the complete literature secondary-effluent composition (Vidic and Dzombak 2009, Table 2.1) and scaled
linearly with C and with the plant's DMR TDS relative to the literature TDS. The equilibrium constants are
interpolated linearly in temperature to the bulk-water temperature T_BULK_C. The pH of the concentrated water is
the pH in equilibrium with atmospheric CO2 (pH = -log(K1 Kh PCO2 / {HCO3-}), Hem 1985 Table 33 constants and
PCO2 of 0.0003 atm, Hem 1985 p. 92), capped at PH_CAP, the upper end of the pH range computed for municipal
wastewater open to air (Vidic and Dzombak 2009, PDF p. 167). Bicarbonate is taken equal to total alkalinity
(valid below pH 8.3; at the pH cap carbonate is under 2 percent of bicarbonate by Hem Table 33 K2).

Makeup quality: the Water Quality Portal is queried by peakflow.wqp. When it has no data for a plant (or is
unavailable), the literature secondary-effluent values are used and the row is marked 'assumed'. The plant's
own DMR values (wwtp_majors.csv) are preferred where they exist: chloride_mg_l (none of the matched plants report
it), tds_mg_l, and total_p_mg_l (converted to phosphate as PO4 and treated conservatively as orthophosphate).
Where DMR chloride is absent the chloride proxy is the plant's DMR TDS times the median chloride/TDS ratio of
the eligible POTWs that report both, or the literature chloride where DMR TDS is also absent.

Water balance per unit evaporation E: makeup M = C/(C-1), blowdown B = 1/(C-1). The implied minimum
return-flow percentage for a term sheet is defined as blowdown / makeup = 1/C (the share of the delivered
effluent that the tower returns as blowdown).

Run: ``PYTHONPATH=src python -m peakflow.cycles`` (reads results/wqp_makeup.csv written by peakflow.wqp).
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from .paths import PROCESSED, RESULTS
from .supply_screen import eligible_mask
from . import wqp

OUT_CSV = RESULTS / "cycles_by_plant.csv"
OUT_MD = RESULTS / "cycles_by_plant.md"
OUT_JSON = RESULTS / "cycles_summary.json"

MODEL_CYCLES = 4.0                          # results/calibration.json primary.cycles [peakflow_model]
PEAK_DAY_GPD_PER_MW = 13285.5865386001      # results/supply_summary.json demand_rates.peak_day_gpd_per_mw

# ------------------------------------------------------------------------------------------ tower limits
SIO2_LIMIT = 150.0     # mg/L as SiO2, amorphous silica solubility limit [midkiff_1977, PDF p. 3; dogra_2023, PDF p. 5]
CL_LIMIT = 1060.0      # mg/L chloride carried without localized corrosion, mixed low carbon steel, stainless steel,
                       # copper/nickel and copper metallurgy [geiger_1993, PDF pp. 2, 4, 7 (Table 1)]
PO4_LIMIT = 15.0       # mg/L orthophosphate as PO4 held without calcium phosphate precipitation [geiger_1993, PDF p. 5]
LSI_MAX = 2.5          # treated with a phosphonate/copolymer program at 20 cycles [geiger_1993, PDF p. 3]
T_BULK_C = 35.0        # bulk tower water temperature, stated assumption [peakflow_model]
PH_CAP = 8.5           # upper end of pH computed for MWW open to air [vidic_2009, PDF p. 167]
PCO2_ATM = 0.0003      # normal air [hem_1985, p. 92]

# ------------------------------------------------------------------------------------------ Hem (1985)
# Table 33 (p. 253), ionic strength 0.0: T, log Kw, log Kh, log K1, log K2, log Ks
HEM_T33 = pd.DataFrame(
    [[0, -14.955, -1.114, -6.579, -10.625, 2.274],
     [10, -14.534, -1.270, -6.464, -10.490, 2.131],
     [20, -14.161, -1.406, -6.381, -10.377, 1.983],
     [30, -13.833, -1.521, -6.327, -10.290, 1.837],
     [40, -13.533, -1.620, -6.298, -10.220, 1.685],
     [50, -13.263, -1.705, -6.285, -10.172, 1.537]],
    columns=["t_c", "log_kw", "log_kh", "log_k1", "log_k2", "log_ks"])
DH_A, DH_B = 0.5085, 0.3281                # water at 25 C [hem_1985, p. 15 to 16]
ION_SIZE = {"Ca": 6.0, "HCO3": 4.0}        # Table 5 [hem_1985, p. 16]

# ------------------------------------------------------------------------------------------ literature makeup
# General secondary effluent quality, Table 2.1 [vidic_2009, PDF p. 29]; alkalinity is the Williams (1982) column.
LIT = {"silica": None, "calcium": 60.0, "alkalinity": 131.0, "chloride": 130.0, "tds": 730.0, "po4": 8.0,
       "ph": 7.5}
# Complete Table 2.1 ionic composition (mg/L) for ionic strength: ion -> (mg/L, molar mass g/mol, charge)
LIT_IONS = {"Na": (135.0, 22.990, 1), "K": (15.0, 39.098, 1), "Ca": (60.0, 40.078, 2), "Mg": (25.0, 24.305, 2),
            "NH4": (16.0 * 18.038 / 14.007, 18.038, 1), "Cl": (130.0, 35.453, -1), "HCO3": (300.0, 61.017, -1),
            "SO4": (100.0, 96.06, -2), "HPO4": (8.0 * 95.98 / 94.97, 95.98, -2),
            "NO3": (3.0 * 62.004 / 14.007, 62.004, -1)}
# Silica: effluent silica is taken to track source water (assumption stated in [dogra_2023, PDF p. 14]); the
# central value is the Davis (1964) median for surface water reported by [hem_1985, p. 73].
SILICA_CENTRAL = 14.0
# Secondary effluent ranges, Table 2.2 [vidic_2009, PDF p. 30]: (favourable, adverse)
LIT_RANGE = {"silica": (8.3, 50.0), "calcium": (28.0, 185.0), "alkalinity": (100.0, 250.0)}
LIT_PH_RANGE = (7.0, 8.0)                  # Table 2.2; central 7.5 is the midpoint (makeup pH only, not used in LSI)

P_TO_PO4 = 94.971 / 30.974                 # mg P -> mg PO4
MG_CACO3_PER_MEQ = 50.04

CONSTRAINTS = ["silica", "chloride", "phosphate", "lsi"]
LABELS = {"silica": "Silica", "chloride": "Chloride", "phosphate": "Phosphate", "lsi": "LSI"}


# ------------------------------------------------------------------------------------------ chemistry
def hem_logk(t_c: float = T_BULK_C) -> dict:
    """Hem Table 33 constants linearly interpolated to t_c."""
    return {c: float(np.interp(t_c, HEM_T33.t_c, HEM_T33[c])) for c in HEM_T33.columns if c != "t_c"}


def ionic_strength_lit() -> float:
    return 0.5 * sum(mg / 1000.0 / mw * z * z for mg, mw, z in LIT_IONS.values())


def log_gamma(z: int, a: float, ionic: float) -> float:
    s = math.sqrt(ionic)
    return -DH_A * z * z * s / (1.0 + DH_B * a * s)


def lsi(cycles: float, ca_mg_l: float, alk_mg_l_caco3: float, tds_mg_l: float, t_c: float = T_BULK_C,
        ph_cap: float = PH_CAP, pco2_atm: float = PCO2_ATM) -> dict:
    """LSI of makeup concentrated by `cycles` (no precipitation), Hem (1985) formulation."""
    k = hem_logk(t_c)
    ionic = cycles * ionic_strength_lit() * tds_mg_l / LIT["tds"]
    lg_ca = log_gamma(2, ION_SIZE["Ca"], ionic)
    lg_hco3 = log_gamma(1, ION_SIZE["HCO3"], ionic)
    log_a_ca = math.log10(cycles * ca_mg_l / 1000.0 / 40.078) + lg_ca
    log_a_hco3 = math.log10(cycles * alk_mg_l_caco3 / MG_CACO3_PER_MEQ / 1000.0) + lg_hco3
    ph_s = k["log_ks"] - log_a_ca - log_a_hco3
    ph_eq = -(k["log_k1"] + k["log_kh"] + math.log10(pco2_atm) - log_a_hco3)
    ph = min(ph_eq, ph_cap)
    return {"lsi": ph - ph_s, "ph": ph, "ph_eq": ph_eq, "ph_s": ph_s, "ionic_strength": ionic}


def cycles_lsi(ca, alk, tds, lsi_max: float = LSI_MAX, c_max: float = 200.0, **kw) -> float:
    """Largest C in [1, c_max] with LSI(C) <= lsi_max (LSI increases monotonically with C); < 1 if infeasible."""
    f = lambda c: lsi(c, ca, alk, tds, **kw)["lsi"] - lsi_max
    if f(1.0) > 0:
        return float("nan")
    if f(c_max) <= 0:
        return c_max
    lo, hi = 0.0, math.log(c_max)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(math.exp(mid)) <= 0 else (lo, mid)
    return math.exp(lo)


def water_balance(c: float) -> dict:
    if not np.isfinite(c) or c <= 1.0:
        return {"makeup_per_evap": np.nan, "blowdown_per_evap": np.nan, "min_return_flow_pct": np.nan}
    return {"makeup_per_evap": c / (c - 1.0), "blowdown_per_evap": 1.0 / (c - 1.0),
            "min_return_flow_pct": 100.0 / c}


def constraint_cycles(silica, chloride, po4, ca, alk, tds) -> dict:
    return {"silica": SIO2_LIMIT / silica, "chloride": CL_LIMIT / chloride, "phosphate": PO4_LIMIT / po4,
            "lsi": cycles_lsi(ca, alk, tds)}


def binding(cc: dict, keys=CONSTRAINTS) -> tuple[str, float]:
    k = min(keys, key=lambda x: cc[x] if np.isfinite(cc[x]) else -np.inf)
    return k, cc[k]


# ------------------------------------------------------------------------------------------ makeup quality
def chloride_tds_ratio(majors=None) -> dict:
    w = pd.read_csv(PROCESSED / "wwtp_majors.csv") if majors is None else majors
    e = w[eligible_mask(w)]
    b = e[e.chloride_mg_l.notna() & e.tds_mg_l.notna()]
    r = b.chloride_mg_l / b.tds_mg_l
    return {"ratio": float(r.median()), "n": int(len(b)), "q25": float(r.quantile(0.25)),
            "q75": float(r.quantile(0.75))}


def makeup_quality(plants: pd.DataFrame, wq: pd.DataFrame | None, cl_ratio: float) -> pd.DataFrame:
    wq = wq.set_index("npdes_id") if wq is not None and len(wq) else pd.DataFrame()
    rows = []
    for _, p in plants.iterrows():
        w = wq.loc[p.npdes_id] if p.npdes_id in wq.index else pd.Series(dtype=object)
        have = w.get("source") == "wqp"
        wv = lambda k: float(w.get(f"{k}_median")) if have and pd.notna(w.get(f"{k}_median")) else None
        r = {"npdes_id": p.npdes_id, "wqp_source": w.get("source", "not_run")}
        # silica, calcium, alkalinity: WQP station median, else literature
        for k, lit in (("silica", SILICA_CENTRAL), ("calcium", LIT["calcium"]), ("alkalinity", LIT["alkalinity"])):
            v = wv(k)
            r[k], r[f"{k}_basis"] = (v, "WQP station median") if v is not None else (lit, "literature (assumed)")
        # TDS: DMR, else literature
        if pd.notna(p.tds_mg_l):
            r["tds"], r["tds_basis"] = float(p.tds_mg_l), f"plant DMR ({int(p.tds_n_months)} months)"
        else:
            r["tds"], r["tds_basis"] = LIT["tds"], "literature (assumed)"
        # chloride: DMR, else WQP, else ratio x DMR TDS, else literature
        if pd.notna(p.chloride_mg_l):
            r["chloride"], r["chloride_basis"] = float(p.chloride_mg_l), "plant DMR"
        elif wv("chloride") is not None:
            r["chloride"], r["chloride_basis"] = wv("chloride"), "WQP station median"
        elif pd.notna(p.tds_mg_l):
            r["chloride"], r["chloride_basis"] = cl_ratio * float(p.tds_mg_l), "DMR TDS x median Cl/TDS (assumed)"
        else:
            r["chloride"], r["chloride_basis"] = LIT["chloride"], "literature (assumed)"
        # phosphate: DMR total P as PO4, else WQP orthophosphate, else literature
        if pd.notna(p.total_p_mg_l):
            r["po4"] = float(p.total_p_mg_l) * P_TO_PO4
            r["po4_basis"] = f"plant DMR total P as PO4 ({int(p.total_p_n_months)} months)"
        elif wv("orthophosphate") is not None:
            r["po4"], r["po4_basis"] = wv("orthophosphate"), "WQP station median"
        else:
            r["po4"], r["po4_basis"] = LIT["po4"], "literature (assumed)"
        bases = [r[f"{k}_basis"] for k in ("silica", "calcium", "alkalinity", "chloride")]
        r["status"] = "assumed" if any("assumed" in b for b in bases) else "measured"
        rows.append(r)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------ table
def compute(plants: pd.DataFrame | None = None, wq: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    plants = wqp.plant_list() if plants is None else plants
    if wq is None:
        wq = pd.read_csv(wqp.MAKEUP_CSV) if wqp.MAKEUP_CSV.exists() else None
    clr = chloride_tds_ratio()
    mq = makeup_quality(plants, wq, clr["ratio"])
    df = plants[["npdes_id", "name", "state", "receiving_water", "site_ids", "same_state_option_for",
                 "median_flow_mgd"]].merge(mq, on="npdes_id")
    out = []
    for _, r in df.iterrows():
        cc = constraint_cycles(r.silica, r.chloride, r.po4, r.calcium, r.alkalinity, r.tds)
        b, c = binding(cc)
        b_np, c_np = binding(cc, [k for k in CONSTRAINTS if k != "phosphate"])
        # range: favourable / adverse literature silica, calcium and alkalinity (DMR values held fixed)
        lo_cc = constraint_cycles(LIT_RANGE["silica"][1], r.chloride, r.po4, LIT_RANGE["calcium"][1],
                                  LIT_RANGE["alkalinity"][1], r.tds)
        hi_cc = constraint_cycles(LIT_RANGE["silica"][0], r.chloride, r.po4, LIT_RANGE["calcium"][0],
                                  LIT_RANGE["alkalinity"][0], r.tds)
        at4 = lsi(MODEL_CYCLES, r.calcium, r.alkalinity, r.tds)
        c_lsi_nocap = cycles_lsi(r.calcium, r.alkalinity, r.tds, ph_cap=99.0)
        wb = water_balance(c)
        row = {**r.to_dict(), **{f"cycles_{k}": v for k, v in cc.items()}, "binding_constraint": b,
               "allowable_cycles": c, "feasible_above_1": bool(np.isfinite(c) and c > 1.0), **wb,
               "allowable_cycles_low": binding(lo_cc)[1], "allowable_cycles_high": binding(hi_cc)[1],
               "binding_without_phosphate": b_np, "allowable_cycles_without_phosphate": c_np,
               "min_return_flow_pct_without_phosphate": 100.0 / c_np,
               "cycles_lsi_uncapped_ph": c_lsi_nocap,
               "lsi_at_model_cycles": at4["lsi"], "ph_at_model_cycles": at4["ph"],
               "ph_eq_at_model_cycles": at4["ph_eq"],
               "model_cycles": MODEL_CYCLES,
               "model_min_return_flow_pct": 100.0 / MODEL_CYCLES,
               "makeup_vs_model": (wb["makeup_per_evap"] / (MODEL_CYCLES / (MODEL_CYCLES - 1.0)))
               if np.isfinite(wb["makeup_per_evap"]) else np.nan}
        row["peak_day_makeup_gpd_per_mw_it"] = PEAK_DAY_GPD_PER_MW * row["makeup_vs_model"]
        out.append(row)
    t = pd.DataFrame(out).sort_values("allowable_cycles", na_position="first").reset_index(drop=True)
    k = hem_logk()
    summary = {
        "n_plants": int(len(t)), "n_assumed": int((t.status == "assumed").sum()),
        "n_dmr_chloride": int(t.chloride_basis.eq("plant DMR").sum()),
        "binding_counts": t.binding_constraint.value_counts().to_dict(),
        "n_below_model_cycles": int((t.allowable_cycles < MODEL_CYCLES).sum()),
        "n_not_feasible_above_1": int((~t.feasible_above_1).sum()),
        "allowable_cycles_median": float(t.allowable_cycles.median()),
        "allowable_cycles_min": float(t.allowable_cycles.min()),
        "allowable_cycles_max": float(t.allowable_cycles.max()),
        "allowable_cycles_without_phosphate_median": float(t.allowable_cycles_without_phosphate.median()),
        "allowable_cycles_without_phosphate_min": float(t.allowable_cycles_without_phosphate.min()),
        "allowable_cycles_without_phosphate_max": float(t.allowable_cycles_without_phosphate.max()),
        "binding_without_phosphate_counts": t.binding_without_phosphate.value_counts().to_dict(),
        "cycles_lsi_range": [float(t.cycles_lsi.min()), float(t.cycles_lsi.max())],
        "cycles_lsi_uncapped_ph_range": [float(t.cycles_lsi_uncapped_ph.min()), float(t.cycles_lsi_uncapped_ph.max())],
        "ph_eq_at_model_cycles_range": [float(t.ph_eq_at_model_cycles.min()), float(t.ph_eq_at_model_cycles.max())],
        "n_phosphate_infeasible": int((t.cycles_phosphate <= 1.0).sum()),
        "min_return_flow_pct_median": float(t.min_return_flow_pct.median()),
        "min_return_flow_pct_without_phosphate_range": [float(t.min_return_flow_pct_without_phosphate.min()),
                                                        float(t.min_return_flow_pct_without_phosphate.max())],
        "cycles_silica_central": SIO2_LIMIT / SILICA_CENTRAL,
        "cycles_silica_range": [SIO2_LIMIT / LIT_RANGE["silica"][1], SIO2_LIMIT / LIT_RANGE["silica"][0]],
        "lsi_at_model_cycles_range": [float(t.lsi_at_model_cycles.min()), float(t.lsi_at_model_cycles.max())],
        "chloride_tds_ratio": clr,
        "ionic_strength_lit": ionic_strength_lit(),
        "hem_logk_at_t_bulk": k, "limits": {"silica_mg_l_sio2": SIO2_LIMIT, "chloride_mg_l": CL_LIMIT,
                                            "po4_mg_l": PO4_LIMIT, "lsi_max": LSI_MAX, "t_bulk_c": T_BULK_C,
                                            "ph_cap": PH_CAP, "pco2_atm": PCO2_ATM},
        "model_cycles": MODEL_CYCLES,
        "makeup_lit": {**LIT, "silica": SILICA_CENTRAL},
    }
    return t, summary


def _fmt(x, d=1):
    return "" if not np.isfinite(x) else f"{x:.{d}f}"


def write_md(t: pd.DataFrame, s: dict, path=OUT_MD):
    lines = ["# Allowable cycles of concentration by matched plant", "",
             "Source: results/cycles_by_plant.csv [cycles_by_plant.csv], produced by `python -m peakflow.cycles`. "
             "Every row is marked 'assumed' because Water Quality Portal records were not retrieved for the matched "
             "plants [wqp_status.json]. "
             "Silica, calcium and alkalinity are literature values [vidic_2009, hem_1985], TDS and phosphate are the "
             "plant's own DMR medians where reported [epa_echo], and chloride is a TDS-based proxy because no matched "
             "plant reports chloride [epa_echo]. Return flow is defined as blowdown / makeup = 1/C.", "",
             "| Plant | NPDES | Sites | C silica | C chloride | C phosphate | C LSI | Binding | Allowable C "
             "(range) | Makeup/E | Blowdown/E | Min return flow % | C without phosphate | Status |",
             "|---|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|"]
    for _, r in t.iterrows():
        sites = r.site_ids if isinstance(r.site_ids, str) else f"same-state option for {r.same_state_option_for}"
        lines.append(
            f"| {r['name'].title()} | {r.npdes_id} | {sites} | {_fmt(r.cycles_silica)} | {_fmt(r.cycles_chloride)} | "
            f"{_fmt(r.cycles_phosphate)} | {_fmt(r.cycles_lsi)} | {LABELS[r.binding_constraint]} | "
            f"{_fmt(r.allowable_cycles)} ({_fmt(r.allowable_cycles_low)} to {_fmt(r.allowable_cycles_high)}) | "
            f"{_fmt(r.makeup_per_evap, 2)} | {_fmt(r.blowdown_per_evap, 2)} | {_fmt(r.min_return_flow_pct, 0)} | "
            f"{_fmt(r.allowable_cycles_without_phosphate)} ({LABELS[r.binding_without_phosphate]}) | {r.status} |")
    lines += ["", f"The model assumes {MODEL_CYCLES:g} cycles [peakflow_model], which implies makeup of "
              f"{MODEL_CYCLES / (MODEL_CYCLES - 1):.2f} times evaporation and a minimum return flow of "
              f"{100 / MODEL_CYCLES:.0f} percent [peakflow_model]. Blank makeup and blowdown cells mark plants whose "
              "makeup already exceeds a tower limit (allowable C at or below 1), which require treatment before "
              "use. The range brackets the favourable and adverse literature silica, calcium and alkalinity "
              "[vidic_2009, PDF p. 30]."]
    path.write_text("\n".join(lines) + "\n")


def run():
    t, s = compute()
    t.to_csv(OUT_CSV, index=False, float_format="%.4g")
    write_md(t, s)
    OUT_JSON.write_text(json.dumps(s, indent=2, default=float) + "\n")
    return t, s


def main():
    t, s = run()
    print(f"cycles: {s['n_plants']} plants; binding {s['binding_counts']}; median allowable "
          f"{s['allowable_cycles_median']:.2f}; {s['n_below_model_cycles']} below {MODEL_CYCLES:g}")


if __name__ == "__main__":
    main()
