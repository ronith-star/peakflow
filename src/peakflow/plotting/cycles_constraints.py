"""Allowable cycles of concentration by constraint, one row per matched plant (report figure style, 180 mm wide).

  figures/cycles_constraints.{png,pdf,svg}, _caption.md, _data.csv; checks in results/cycles_figure_check.json.
Input: results/cycles_by_plant.csv (peakflow.cycles). Run: PYTHONPATH=src python -m peakflow.plotting.cycles_constraints
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import matplotlib.text as mtext
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, NullFormatter, NullLocator

from .. import cycles as CY
from .. import styles as S
from ..paths import FIGURES, RESULTS
from .supply_figures import text_overlaps

STEM = "cycles_constraints"
W_MM, H_MM = 180.0, 118.0
XLIM = (0.7, 30.0)
XTICKS = [1, 2, 3, 4, 5, 7, 10, 20, 30]
MARKERS = {"silica": "o", "chloride": "s", "phosphate": "D", "lsi": "^"}
MS = {"silica": 4.2, "chloride": 3.8, "phosphate": 3.6, "lsi": 4.4}
SOURCE = "Sources: EPA ECHO; Vidic and Dzombak 2009; Hem 1985; Geiger et al. 1993; Midkiff and Foyt 1977."

ABBR = [("SEWERAGE AUTHORITY", "Sew. Auth."), ("SEWER UTILITY", "Sewer Utility"), ("MUN SEW AUTH", "Mun. Sew. Auth."),
        ("WATER POLLUTION CONTROL PLANT", "WPCP"), ("WASTEWATER TREATMENT PLANT", "WWTP"),
        ("TREATMENT FACILITY", "Treatment Fac."), ("JOINT AUTHORITY", "Jt. Auth."), ("JT SEW AUTH", "Jt. Sew. Auth."),
        ("BOROUGH", "Boro."), ("SUMMIT HLL SEW", "Summit Hill Sew."), ("(WTP) CITY OF", "City"),
        ("NORTHAMPTON BORO/ SEW", "Northampton Boro. Sew."), ("BORO AUTH", "Boro. Auth."), ("LCA ", "LCA "),
        ("GR HAZLETON", "Greater Hazleton"), (" JR ", " Jr. ")]
KEEP_UPPER = {"STP", "WWTP", "WPCP", "LCA", "S."}


def plant_label(name: str, npdes: str) -> str:
    s = name.strip()
    for a, b in ABBR:
        s = s.replace(a, b)
    words = [w if (w in KEEP_UPPER or w.endswith(".") and w[:-1].isupper() and len(w) <= 3) else
             (w if any(c.islower() for c in w) else w.title()) for w in s.split()]
    return f"{' '.join(words)} ({npdes})"


def _tbb(t, r):
    return t.get_window_extent(renderer=r)


def render(t: pd.DataFrame | None = None):
    t = pd.read_csv(CY.OUT_CSV) if t is None else t
    t = t.sort_values(["allowable_cycles", "npdes_id"], ascending=[False, True]).reset_index(drop=True)
    S.register_fonts()
    S.figure_rc()
    narrow = S.narrow_family()
    mm = 1 / S.MM_PER_IN
    fig = plt.figure(figsize=(W_MM * mm, H_MM * mm))
    left, right, top, bottom = 62.0, 30.0, 12.0, 17.0
    ax = fig.add_axes([left / W_MM, bottom / H_MM, 1 - (left + right) / W_MM, 1 - (top + bottom) / H_MM])
    n = len(t)
    y = np.arange(n)[::-1]
    ax.set_xscale("log")
    ax.set_xlim(*XLIM)
    ax.set_ylim(-0.7, n - 0.3)
    ax.xaxis.set_major_locator(FixedLocator(XTICKS))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.xaxis.set_minor_locator(NullLocator())
    ax.axvspan(XLIM[0], 1.0, color=S.FIG_OUTSIDE, lw=0, zorder=0.5)
    for yi in y[::2]:
        ax.axhspan(yi - 0.5, yi + 0.5, color="#F4F4F4", lw=0, zorder=0)
    ax.axvline(CY.MODEL_CYCLES, color=S.FIG_BLACK, lw=S.FIG_LW_SECONDARY, ls=S.FIG_DASH, zorder=1)
    ax.text(CY.MODEL_CYCLES * 1.03, n - 0.35, "Model, 4 cycles", ha="left", va="bottom", fontsize=S.FIG_FONT_SIZE,
            color=S.FIG_BLACK, clip_on=False)
    ax.text(XLIM[0] * 1.02, n - 0.35, "Makeup exceeds limit", ha="left", va="bottom", fontsize=S.FIG_FONT_SIZE,
            color=S.FIG_GRAY_DARK, clip_on=False, family=narrow)
    rows = []
    for yi, (_, r) in zip(y, t.iterrows()):
        vals = {k: float(r[f"cycles_{k}"]) for k in CY.CONSTRAINTS}
        shown = {k: min(max(v, XLIM[0] * 1.02), XLIM[1] / 1.02) for k, v in vals.items()}
        ax.plot([min(shown.values()), max(shown.values())], [yi, yi], color=S.FIG_GRAY_LIGHT,
                lw=S.FIG_LW_SECONDARY, zorder=2, solid_capstyle="butt")
        for k in CY.CONSTRAINTS:
            b = k == r.binding_constraint
            ax.plot(shown[k], yi, marker=MARKERS[k], ms=MS[k] + (0.6 if b else 0), ls="none", zorder=4 if b else 3,
                    mfc=S.FIG_ACCENT if b else "white", mec=S.FIG_ACCENT if b else S.FIG_GRAY_DARK,
                    mew=S.FIG_LW_SECONDARY)
            rows.append({"npdes_id": r.npdes_id, "plant": r["name"], "row_y": int(yi), "constraint": k,
                         "allowable_cycles": vals[k], "plotted_x": shown[k], "binding": b,
                         "status": r.status, "model_cycles": CY.MODEL_CYCLES})
        ax.text(-0.012, yi, plant_label(r["name"], r.npdes_id), transform=ax.get_yaxis_transform(), ha="right",
                va="center", fontsize=S.FIG_FONT_SIZE, family=narrow, color=S.FIG_BLACK)
        c = r.allowable_cycles
        ax.text(1.07, yi, f"{c:.1f}", transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=S.FIG_FONT_SIZE, color=S.FIG_ACCENT)
        rf = "n/a" if not np.isfinite(r.min_return_flow_pct) else f"{r.min_return_flow_pct:.0f}"
        ax.text(1.25, yi, rf, transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=S.FIG_FONT_SIZE, color=S.FIG_BLACK)
    ax.text(1.07, n - 0.35, "C", transform=ax.get_yaxis_transform(), ha="right", va="bottom",
            fontsize=S.FIG_FONT_SIZE, color=S.FIG_ACCENT)
    ax.text(1.25, n - 0.35, "Return %", transform=ax.get_yaxis_transform(), ha="right", va="bottom",
            fontsize=S.FIG_FONT_SIZE, color=S.FIG_BLACK)
    ax.set_yticks([])
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel("Allowable cycles of concentration (log scale)")
    handles = [Line2D([], [], marker=MARKERS[k], ls="none", ms=MS[k], mfc="white", mec=S.FIG_GRAY_DARK,
                      mew=S.FIG_LW_SECONDARY, label=CY.LABELS[k]) for k in CY.CONSTRAINTS]
    handles.append(Line2D([], [], marker="o", ls="none", ms=MS["silica"] + 0.6, mfc=S.FIG_ACCENT, mec=S.FIG_ACCENT,
                          label="Binding constraint"))
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(left / W_MM, 1 - 1.5 / H_MM), ncol=5,
               frameon=False, fontsize=S.FIG_FONT_SIZE, handletextpad=0.3, columnspacing=1.6, borderaxespad=0)
    S.figure_source_line(fig, SOURCE)
    return fig, pd.DataFrame(rows), t


def write_caption(t: pd.DataFrame, s: dict, path=None):
    path = path or FIGURES / f"{STEM}_caption.md"
    L = s["limits"]
    nb = s["binding_counts"]
    txt = (
        f"# Figure 9 ({STEM})\n\n"
        "**Figure 9.**\n\n"
        "The chart shows the allowable cycles of concentration for a cooling tower supplied with secondary effluent "
        f"from each of the {s['n_plants']} matched municipal plants [cycles_by_plant.csv]. Each row is one plant, "
        "sorted by allowable cycles. The open markers give the cycles at which the concentrated water reaches each "
        "of four limits. The first is the silica limit of "
        f"{L['silica_mg_l_sio2']:.0f} mg/L as SiO2 [midkiff_1977, PDF p. 3] [dogra_2023, PDF p. 5]. The second is "
        f"the chloride level of {L['chloride_mg_l']:.0f} mg/L carried by mixed carbon steel, stainless steel and "
        f"copper alloy metallurgy [geiger_1993, PDF pp. 2, 4, 7]. The third is {L['po4_mg_l']:.0f} mg/L "
        f"orthophosphate as PO4 [geiger_1993, PDF p. 5]. The fourth is a Langelier saturation index of "
        f"{L['lsi_max']:.1f} [geiger_1993, PDF p. 3], evaluated at {L['t_bulk_c']:.0f} C bulk water with pH capped "
        f"at {L['ph_cap']:.1f} [vidic_2009, PDF p. 167] [hem_1985, pp. 15, 19, 253]. The filled accent marker is "
        f"the binding constraint, which is phosphate at {nb.get('phosphate', 0)} plants, the saturation index at "
        f"{nb.get('lsi', 0)} and chloride at {nb.get('chloride', 0)} [cycles_by_plant.csv]. The dashed line marks "
        f"the {s['model_cycles']:.0f} cycles assumed by the cooling model [peakflow_model]. The shaded band marks "
        "makeup that already exceeds a limit. The right-hand columns give the allowable cycles C and the implied "
        "minimum return flow, 100/C percent [cycles_by_plant.csv]. Return flow is defined as blowdown divided by "
        "makeup.\n\n"
        "Every row is marked assumed because Water Quality Portal records were not retrieved for the matched plants "
        "[wqp_status.json]. Silica, "
        "calcium and alkalinity are therefore literature secondary-effluent values [vidic_2009, PDF p. 29] "
        "[hem_1985, p. 73]. Chloride is DMR total dissolved solids times a chloride ratio of "
        f"{s['chloride_tds_ratio']['ratio']:.2f} [epa_echo, cycles_summary.json]. Phosphate and dissolved solids are "
        "each plant's DMR median where reported [epa_echo].\n\n"
        "The citation keys are epa_echo, vidic_2009, hem_1985, geiger_1993, midkiff_1977, dogra_2023 and "
        f"peakflow_model. Plotted values are in figures/{STEM}_data.csv.\n")
    path.write_text(txt)


def check(fig) -> dict:
    ov = text_overlaps(fig)
    fs = [t.get_fontsize() for t in fig.findobj(mtext.Text) if t.get_visible() and t.get_text().strip()]
    return {"overlaps": [list(map(str, o)) for o in ov], "min_font_pt": float(min(fs)), "max_font_pt": float(max(fs)),
            "width_mm": float(fig.get_size_inches()[0] * S.MM_PER_IN),
            "height_mm": float(fig.get_size_inches()[1] * S.MM_PER_IN)}


def run():
    t = pd.read_csv(CY.OUT_CSV)
    s = json.loads(CY.OUT_JSON.read_text())
    fig, data, _ = render(t)
    FIGURES.mkdir(exist_ok=True)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(FIGURES / f"{STEM}.{ext}", dpi=S.FIG_DPI)
    data.to_csv(FIGURES / f"{STEM}_data.csv", index=False, float_format="%.4g")
    write_caption(t, s)
    c = check(fig)
    (RESULTS / "cycles_figure_check.json").write_text(json.dumps(c, indent=2) + "\n")
    plt.close(fig)
    return c


if __name__ == "__main__":
    c = run()
    print(f"{STEM}: overlaps {len(c['overlaps'])}; font {c['min_font_pt']}-{c['max_font_pt']} pt; "
          f"{c['width_mm']:.0f} x {c['height_mm']:.0f} mm")
    for o in c["overlaps"]:
        print("  ", o)
