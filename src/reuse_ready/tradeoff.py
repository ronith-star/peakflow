"""Water-energy tradeoff by cooling architecture at Trenton (work order Part 5, item 15).

Outputs: results/water_energy_frontier.csv, results/lbnl_fig44_digitized.csv,
figures/water_energy_frontier.{png,pdf,svg}, _caption.md, _data.csv; results/water_energy_frontier_check.json.

Axes, per MW of IT load and per year (8,760 h):
  water  (gal per MW-year): modelled architectures from cooling_model on KTTN hourly wet-bulb 2005-2024 (hybrid
         calibrated by results/calibration.json 'primary'); LBNL-only architectures from Figure 4.4 site WUE,
         gal = WUE (L/kWh) x 8,760,000 kWh / 3.785411784 L/gal.
  energy (kWh per MW-year) = (PUE - 1) x 8,760,000, PUE from LBNL 2024 Figure 4.4 (report p. 46) [shehabi_2024].
         PUE - 1 is all non-IT energy (cooling plus power distribution and other overhead), so it bounds the
         cooling energy from above.

LBNL Figure 4.4 is a raster image (1002 x 756 px) embedded on PDF page 46. `digitize_fig44` reads it straight
from data/raw/lbnl_2024.pdf: axes are calibrated on the gridlines (PUE 1.00 to 2.50 at 0.25 steps, 49.6 px per
0.25; WUE 0 to 4 L/kWh, 73.3 px per 1), boxes are found by fill colour, the median is the dark line inside the
box, and the range is the whisker ends as drawn. Resolution is one pixel: 0.005 PUE and 0.014 L/kWh.
Central value = median; range = whisker ends. LBNL states the lower limits are best-practice efficiency in
favourable climates and the upper limits poor efficiency in hot, humid climates (p. 44).

Architecture to LBNL row mapping (hyperscale, i.e. 'Large-scale', rows used wherever LBNL draws one):
  evaporative_tower  -> Large-scale 'Waterside economizer (water-cooled chiller)': the tower rejects all heat
                        in every hour, as in the model (phi = 1). Sensitivity: Midsize 'Water-cooled chiller'.
  hybrid             -> Large-scale 'Dry cooler with adiabatic assist (air-cooled chiller)': dry heat rejection
                        with evaporative assist above a switchover, as in the calibrated hybrid.
  air_cooled_chiller -> Midsize 'Air-cooled chiller' (no Large-scale air-cooled chiller row exists; this
                        mixes space-type and cooling-type effects, see the like-for-like Midsize comparison).
  airside_adiabatic_wcc -> Large-scale 'Airside economizer & adiabatic cooling (water-cooled chiller)' (LBNL only).
  airside_adiabatic_acc -> Large-scale 'Airside economizer & adiabatic cooling (air-cooled chiller)' (LBNL only);
                        its simulated WUE is a collapsed box at about 0 L/kWh that LBNL itself calls likely low,
                        so the water axis uses the 0.1 to 0.3 L/kWh reported by hyperscale operators for similar
                        systems and the 0.2 L/kWh median LBNL uses for context (p. 47).

Modelled water at a given PUE: heat rejected = P_IT x PUE (cooling_model), so per-MW-IT makeup scales linearly
with PUE. Central = 20-year mean at the LBNL median PUE; low = lowest calendar-year total at the low-whisker
PUE; high = highest calendar-year total at the high-whisker PUE. Cycles of concentration fixed at 4.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import FIGURES, RAW, RESULTS

HOURS = 8760.0
KWH_PER_MW_YEAR = 1000.0 * HOURS          # 8,760,000
L_PER_GAL = 3.785411784
DAYS_PER_YEAR = 365.0
LBNL_PDF = RAW / "lbnl_2024.pdf"
FIG44_PAGE_INDEX = 45                      # zero-based; report page 46
FIG44_PAGE_LABEL = 46
FALLS_AVG_GPD = 135_000.0                  # [falls_levittown_2026]

# Pixel row bands (top, bottom) of each box in the native 1002 x 756 raster, and the fill colour of its series.
FIG44_ROWS = {
    "large_waterside_econ_wcc": ("Large-scale", "Waterside economizer (water-cooled chiller)", 541, 551, "blue"),
    "large_dry_cooler_adiabatic_acc": ("Large-scale", "Dry cooler with adiabatic assist (air-cooled chiller)",
                                       419, 429, "blue"),
    "large_airside_adiabatic_wcc": ("Large-scale", "Airside economizer & adiabatic cooling (water-cooled chiller)",
                                    500, 510, "blue"),
    "large_airside_adiabatic_acc": ("Large-scale", "Airside economizer & adiabatic cooling (air-cooled chiller)",
                                    459, 470, "blue"),
    "midsize_air_cooled_chiller": ("Midsize", "Air-cooled chiller", 188, 198, "orange"),
    "midsize_water_cooled_chiller": ("Midsize", "Water-cooled chiller", 310, 320, "orange"),
}
# Rows whose WUE is drawn as a collapsed box (a dark marker at about 0 L/kWh) rather than a coloured box.
FIG44_WUE_COLLAPSED = {"large_airside_adiabatic_acc", "midsize_air_cooled_chiller"}
PUE_GRID_PX = np.array([308, 358, 407, 457, 507, 556, 606]); PUE_GRID_V = np.arange(1.0, 2.51, 0.25)
WUE_GRID_PX = np.array([676, 749, 822, 896, 969]); WUE_GRID_V = np.arange(0.0, 4.01, 1.0)
PUE_PANEL = (296, 628); WUE_PANEL = (662, 993)

# LBNL p. 47 text: hyperscale operators report 0.1 to 0.3 L/kWh for systems similar to airside economizer with
# adiabatic cooling (air-cooled chiller); LBNL uses 0.2 L/kWh as an alternative median for context.
LBNL_P47_REPORTED_WUE = {"low": 0.1, "central": 0.2, "high": 0.3}

ARCHS = [
    # key, label, source of water axis, LBNL row, plotted
    ("evaporative_tower", "Evaporative tower", "model", "large_waterside_econ_wcc", True),
    ("hybrid", "Hybrid (calibrated)", "model", "large_dry_cooler_adiabatic_acc", True),
    ("air_cooled_chiller", "Air-cooled chiller", "model", "midsize_air_cooled_chiller", True),
    ("airside_adiabatic_wcc", "Airside economizer with adiabatic cooling (water-cooled chiller)", "lbnl_wue",
     "large_airside_adiabatic_wcc", True),
    ("airside_adiabatic_acc", "Airside economizer with adiabatic cooling (air-cooled chiller)", "lbnl_p47_reported",
     "large_airside_adiabatic_acc", True),
    ("evaporative_tower_midsize", "Evaporative tower, Midsize water-cooled chiller mapping (sensitivity)", "model",
     "midsize_water_cooled_chiller", False),
]


# ------------------------------------------------------------------------------------------ LBNL digitization
def fig44_image(pdf: Path = LBNL_PDF) -> np.ndarray:
    """The embedded Figure 4.4 raster (RGB uint8 array) from PDF page 46."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    page = doc[FIG44_PAGE_INDEX]
    imgs = [o for o in page.get_objects(max_depth=5) if o.type == 3]
    if len(imgs) != 1:
        raise RuntimeError(f"expected one image on PDF page {FIG44_PAGE_LABEL}, found {len(imgs)}")
    return np.asarray(imgs[0].get_bitmap(render=False).to_pil().convert("RGB")).astype(int)


def _masks(im):
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    return {"blue": (B > 130) & (R < 90) & (G > 90) & (G < 150),
            "orange": (R > 200) & (G > 100) & (G < 160) & (B < 80)}, im.max(2) < 120


def _read_box(im, fill, dark, y0, y1, x0, x1, coef):
    yc = (y0 + y1) // 2
    xs = np.where(dark[yc - 1:yc + 2, x0 + 3:x1 - 2].any(0))[0] + x0 + 3
    cols = np.where(fill[y0:y1 + 1, x0:x1].any(0))[0] + x0
    if not len(xs) or not len(cols):
        raise ValueError("no box found")
    lo, hi = cols.min(), cols.max()
    inner = dark[y0 + 1:y1, lo:hi + 1].sum(0)
    med = np.where(inner >= (y1 - y0 - 2))[0] + lo
    med = med[(med > lo + 1) & (med < hi - 1)]
    f = lambda x: float(np.polyval(coef, x))
    return {"whisker_low": f(xs.min()), "q1": f(lo - 1), "median": f(med.mean()), "q3": f(hi + 1),
            "whisker_high": f(xs.max())}


def digitize_fig44(pdf: Path = LBNL_PDF) -> pd.DataFrame:
    """PUE and site WUE box-plot statistics for the rows in FIG44_ROWS, read from the PDF raster."""
    im = fig44_image(pdf)
    fills, dark = _masks(im)
    cp = np.polyfit(PUE_GRID_PX, PUE_GRID_V, 1)
    cw = np.polyfit(WUE_GRID_PX, WUE_GRID_V, 1)
    rows = []
    for key, (cls, label, y0, y1, col) in FIG44_ROWS.items():
        pue = _read_box(im, fills[col], dark, y0, y1, *PUE_PANEL, cp)
        if key in FIG44_WUE_COLLAPSED:
            wue = {k: 0.0 for k in pue}
            wue_note = "collapsed box drawn at about 0 L/kWh; not resolvable"
        else:
            wue = {k: max(v, 0.0) for k, v in _read_box(im, fills[col], dark, y0, y1, *WUE_PANEL, cw).items()}
            wue_note = "negative pixel reading clipped to 0" if wue["whisker_low"] == 0.0 else ""
        rows.append({"row_key": key, "space_type": cls, "cooling_system": label,
                     **{f"pue_{k}": round(v, 3) for k, v in pue.items()},
                     **{f"wue_{k}": round(v, 3) for k, v in wue.items()}, "wue_note": wue_note,
                     "source": f"LBNL 2024 Figure 4.4, report p. {FIG44_PAGE_LABEL} [shehabi_2024]; digitized"})
    return pd.DataFrame(rows).set_index("row_key")


# ------------------------------------------------------------------------------------------------ model water
def model_annual_water_per_mw(name: str = "primary") -> dict:
    """Makeup per MW of IT load per year at PUE 1.0 (multiply by PUE): 20-year mean and calendar-year extremes."""
    from . import blindspot as bs

    w, cal, _, _ = bs.load_inputs(name)
    out = {}
    for arch in ("evaporative_tower", "hybrid", "air_cooled_chiller"):
        p = bs.config_params(1.0, arch, cal)
        p.pue = 1.0
        d = bs.daily_series(w, p)
        yr = d.groupby(d.index.year).mean() * DAYS_PER_YEAR
        out[arch] = {"mean": float(d.mean() * DAYS_PER_YEAR), "year_min": float(yr.min()),
                     "year_max": float(yr.max()), "year_min_year": int(yr.idxmin()),
                     "year_max_year": int(yr.idxmax()), "n_nan_days": int(d.isna().sum()),
                     "n_days": int(len(d))}
    out["calibration"] = {k: cal[k] for k in ("t_sw_c", "gamma", "p_it_mw", "pue", "cycles", "twb_ref_c")}
    return out


def wue_to_gal_per_mw_year(wue_l_per_kwh: float) -> float:
    return wue_l_per_kwh * KWH_PER_MW_YEAR / L_PER_GAL


def gal_per_mw_year_to_wue(gal: float) -> float:
    return gal * L_PER_GAL / KWH_PER_MW_YEAR


def energy_kwh_per_mw_year(pue: float) -> float:
    return (pue - 1.0) * KWH_PER_MW_YEAR


def falls_point(cal: dict) -> dict:
    water = FALLS_AVG_GPD * DAYS_PER_YEAR / cal["p_it_mw"]
    return {"arch_key": "falls_township", "label": "Falls Township (AWS Keystone)", "water_source":
            "135,000 gal/day x 365 / calibrated P_IT", "pue_central": cal["pue"], "water_central": water,
            "water_low": water, "water_high": water, "energy_central": energy_kwh_per_mw_year(cal["pue"]),
            "energy_low": energy_kwh_per_mw_year(cal["pue"]), "energy_high": energy_kwh_per_mw_year(cal["pue"]),
            "plotted": True}


def build_table(lbnl: pd.DataFrame | None = None, model: dict | None = None) -> pd.DataFrame:
    lbnl = digitize_fig44() if lbnl is None else lbnl
    model = model_annual_water_per_mw() if model is None else model
    rows = []
    for key, label, src, lrow, plotted in ARCHS:
        L = lbnl.loc[lrow]
        pl, pc, ph = L.pue_whisker_low, L.pue_median, L.pue_whisker_high
        r = {"arch_key": key, "label": label, "water_source": src, "lbnl_row": f"{L.space_type}: {L.cooling_system}",
             "pue_low": pl, "pue_central": pc, "pue_high": ph,
             "lbnl_wue_low": L.wue_whisker_low, "lbnl_wue_central": L.wue_median, "lbnl_wue_high": L.wue_whisker_high,
             "plotted": plotted}
        if src == "model":
            m = model[key if key != "evaporative_tower_midsize" else "evaporative_tower"]
            r.update(water_central=m["mean"] * pc, water_low=m["year_min"] * pl, water_high=m["year_max"] * ph,
                     model_year_min=m["year_min_year"], model_year_max=m["year_max_year"])
        elif src == "lbnl_wue":
            r.update(water_central=wue_to_gal_per_mw_year(L.wue_median),
                     water_low=wue_to_gal_per_mw_year(L.wue_whisker_low),
                     water_high=wue_to_gal_per_mw_year(L.wue_whisker_high))
        else:  # lbnl_p47_reported
            q = LBNL_P47_REPORTED_WUE
            r.update(water_central=wue_to_gal_per_mw_year(q["central"]), water_low=wue_to_gal_per_mw_year(q["low"]),
                     water_high=wue_to_gal_per_mw_year(q["high"]))
        r.update(energy_central=energy_kwh_per_mw_year(pc), energy_low=energy_kwh_per_mw_year(pl),
                 energy_high=energy_kwh_per_mw_year(ph))
        r["lbnl_wue_as_gal_central"] = wue_to_gal_per_mw_year(L.wue_median)
        r["implied_wue_central"] = gal_per_mw_year_to_wue(r["water_central"])
        rows.append(r)
    rows.append(falls_point(model["calibration"]))
    t = pd.DataFrame(rows)
    t["lbnl_page"] = FIG44_PAGE_LABEL
    cols = ["arch_key", "label", "plotted", "water_source", "lbnl_row", "lbnl_page", "water_low", "water_central",
            "water_high", "energy_low", "energy_central", "energy_high", "pue_low", "pue_central", "pue_high",
            "lbnl_wue_low", "lbnl_wue_central", "lbnl_wue_high", "lbnl_wue_as_gal_central", "implied_wue_central",
            "model_year_min", "model_year_max"]
    return t[cols]


# ------------------------------------------------------------------------------------------------------ figure
FIG_W_MM, FIG_H_MM = 85.0, 78.0
ZERO_W_MM = 7.0
LOG_XLIM = (2.0e4, 1.0e7)
Y_MAX = 12.5  # million kWh per MW-year

# Label placement. Keys in the log panel: (text, x_data or None for the point x, y in million kWh, ha, va); a thin
# gray leader joins the label to the top of the point's energy bar. Keys in the zero panel: offset in points.
LABELS = {
    "hybrid": ("Hybrid (calibrated)\nand Falls Township\nfiling (diamond)", None, 3.6, "center", "bottom"),
    "airside_adiabatic_acc": ("Airside economizer,\nadiabatic, air-cooled", None, 5.9, "right", "bottom"),
    "airside_adiabatic_wcc": ("Airside economizer,\nadiabatic,\nwater-cooled", None, 5.9, "left", "bottom"),
    "evaporative_tower": ("Evaporative\ntower", None, 2.9, "center", "bottom"),
}
ZERO_LABELS = {"air_cooled_chiller": ("Air-cooled\nchiller", 5.0, 0.0, "left", "center")}
LEADER_GAP_PT = 1.2


def render_figure(t: pd.DataFrame, stem: str = "water_energy_frontier", label_overrides: dict | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, LogLocator, NullFormatter, FuncFormatter

    from . import styles as S

    S.v2_rc()
    labels = {**LABELS, **(label_overrides or {})}  # falls_township shares the hybrid label
    mm = 1 / 25.4
    fig = plt.figure(figsize=(FIG_W_MM * mm, FIG_H_MM * mm))
    L, B, T, R = 14.0, 11.5, 2.5, 3.0
    gap = 1.6
    ax_h = FIG_H_MM - B - T
    main_w = FIG_W_MM - L - ZERO_W_MM - gap - R
    az = fig.add_axes([L / FIG_W_MM, B / FIG_H_MM, ZERO_W_MM / FIG_W_MM, ax_h / FIG_H_MM])
    ax = fig.add_axes([(L + ZERO_W_MM + gap) / FIG_W_MM, B / FIG_H_MM, main_w / FIG_W_MM, ax_h / FIG_H_MM],
                      sharey=az)
    for a in (az, ax):
        a.set_ylim(0, Y_MAX)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    az.set_xlim(-1, 1); az.set_xticks([0]); az.set_xticklabels(["0"])
    ax.spines["left"].set_visible(False); ax.tick_params(axis="y", left=False, labelleft=False)
    ax.patch.set_visible(False)  # the zero-panel label runs into the log panel's empty left margin
    ax.set_xscale("log"); ax.set_xlim(*LOG_XLIM)
    ax.xaxis.set_major_locator(FixedLocator([1e5, 1e6, 1e7]))
    ax.xaxis.set_minor_locator(FixedLocator([m * 10 ** e for e in (4, 5, 6) for m in range(2, 10)
                                             if LOG_XLIM[0] <= m * 10 ** e <= LOG_XLIM[1]]))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: {1e5: "0.1", 1e6: "1", 1e7: "10"}.get(v, "")))
    az.yaxis.set_major_locator(FixedLocator(np.arange(0, 12.1, 2)))
    az.set_ylabel("Non-IT energy (million kWh per MW-year)")
    # axis-break marks on the shared baseline
    k = dict(color=S.V2_BLACK, lw=S.V2_LW_SECONDARY, clip_on=False, transform=fig.transFigure)
    for xm in (L + ZERO_W_MM, L + ZERO_W_MM + gap):
        x = xm / FIG_W_MM; y = B / FIG_H_MM
        fig.add_artist(plt.Line2D([x - 0.5 / FIG_W_MM, x + 0.5 / FIG_W_MM], [y - 0.9 / FIG_H_MM, y + 0.9 / FIG_H_MM], **k))
    fig.text((L + ZERO_W_MM + gap + main_w / 2) / FIG_W_MM, 1.6 / FIG_H_MM,
             "Cooling water (million gallons per MW-year of IT load)", ha="center", va="bottom", fontsize=S.V2_FONT_SIZE)

    bar_kw = dict(color=S.V2_GRAY_DARK, lw=S.V2_LW_SECONDARY, solid_capstyle="butt", zorder=3)
    cap_pt = 1.6
    data_rows = []
    texts = {}
    leaders = []
    for _, r in t[t.plotted.astype(bool)].iterrows():
        e = np.array([r.energy_low, r.energy_central, r.energy_high]) / 1e6
        wl, wc, wh = r.water_low, r.water_central, r.water_high
        on_zero = wc <= 0
        a = az if on_zero else ax
        xc = 0.0 if on_zero else wc
        # vertical (energy) bar with caps
        if e[2] > e[0]:
            a.plot([xc, xc], [e[0], e[2]], **bar_kw)
            for ee in (e[0], e[2]):
                a.annotate("", (xc, ee), xytext=(-cap_pt, 0), textcoords="offset points",
                           arrowprops=dict(arrowstyle="-", lw=S.V2_LW_SECONDARY, color=S.V2_GRAY_DARK,
                                           shrinkA=0, shrinkB=0))
                a.annotate("", (xc, ee), xytext=(cap_pt, 0), textcoords="offset points",
                           arrowprops=dict(arrowstyle="-", lw=S.V2_LW_SECONDARY, color=S.V2_GRAY_DARK,
                                           shrinkA=0, shrinkB=0))
        # horizontal (water) bar; a zero low end continues across the break into the zero panel
        if not on_zero and wh > wl:
            lo = wl if wl > 0 else LOG_XLIM[0]
            ax.plot([lo, wh], [e[1], e[1]], clip_on=False, **bar_kw)
            ends = [wh] + ([wl] if wl > 0 else [])
            for xx in ends:
                ax.annotate("", (xx, e[1]), xytext=(0, cap_pt), textcoords="offset points",
                            arrowprops=dict(arrowstyle="-", lw=S.V2_LW_SECONDARY, color=S.V2_GRAY_DARK,
                                            shrinkA=0, shrinkB=0))
                ax.annotate("", (xx, e[1]), xytext=(0, -cap_pt), textcoords="offset points",
                            arrowprops=dict(arrowstyle="-", lw=S.V2_LW_SECONDARY, color=S.V2_GRAY_DARK,
                                            shrinkA=0, shrinkB=0))
            if wl <= 0:
                az.plot([0, 1], [e[1], e[1]], clip_on=False, **bar_kw)
                for dy in (cap_pt, -cap_pt):
                    az.annotate("", (0, e[1]), xytext=(0, dy), textcoords="offset points",
                                arrowprops=dict(arrowstyle="-", lw=S.V2_LW_SECONDARY, color=S.V2_GRAY_DARK,
                                                shrinkA=0, shrinkB=0))
        if r.arch_key == "falls_township":
            a.plot([xc], [e[1]], marker="D", ms=7.0, mfc="none", mec=S.V2_BLACK, mew=S.V2_LW_PRIMARY, ls="none",
                   zorder=6)
        elif r.water_source == "model":
            a.plot([xc], [e[1]], marker="o", ms=4.0, mfc=S.V2_ACCENT, mec=S.V2_ACCENT, ls="none", zorder=5)
        else:
            a.plot([xc], [e[1]], marker="o", ms=4.0, mfc="white", mec=S.V2_ACCENT, mew=S.V2_LW_PRIMARY,
                   ls="none", zorder=5)
        if r.arch_key in ZERO_LABELS:
            txt, dx, dy, ha, va = ZERO_LABELS[r.arch_key]
            texts[r.arch_key] = a.annotate(txt, (xc, e[1]), xytext=(dx, dy), textcoords="offset points", ha=ha,
                                           va=va, fontsize=S.V2_FONT_SIZE, zorder=7, annotation_clip=False,
                                           linespacing=1.05)
        elif r.arch_key in labels:
            txt, lx, ly, ha, va = labels[r.arch_key]
            lx = xc if lx is None else lx
            # lines align on the side the leader leaves from, so an offset leader stays attached to every line
            texts[r.arch_key] = a.text(lx, ly, txt, ha=ha, va=va, fontsize=S.V2_FONT_SIZE, zorder=7,
                                       linespacing=1.05, multialignment=ha)
            leaders.append((r.arch_key, a, (xc, e[2]), (lx, ly)))
            a.annotate("", (xc, e[2]), xytext=(lx, ly), textcoords="data",
                       arrowprops=dict(arrowstyle="-", lw=S.V2_LW_TERTIARY, color=S.V2_GRAY,
                                       shrinkA=LEADER_GAP_PT, shrinkB=LEADER_GAP_PT), zorder=2)
        data_rows.append({"arch_key": r.arch_key, "label": r.label, "marker": "zero panel" if on_zero else "log panel",
                          "water_low_gal_per_mw_year": wl, "water_central_gal_per_mw_year": wc,
                          "water_high_gal_per_mw_year": wh, "energy_low_kwh_per_mw_year": r.energy_low,
                          "energy_central_kwh_per_mw_year": r.energy_central,
                          "energy_high_kwh_per_mw_year": r.energy_high, "water_source": r.water_source})
    fig._leaders = leaders
    return fig, (az, ax), texts, pd.DataFrame(data_rows)


def overlap_report(fig) -> list:
    from .plotting.figures_v2 import text_overlaps
    return text_overlaps(fig)


def symbol_label_hits(fig, axes, texts, t) -> list:
    """Label boxes that cover any plotted marker or range-bar end (display coordinates, 1 pt pad)."""
    fig.canvas.draw(); r = fig.canvas.get_renderer(); k = fig.dpi / 72
    az, ax = axes
    pts = []
    for _, row in t[t.plotted.astype(bool)].iterrows():
        a = az if row.water_central <= 0 else ax
        xc = 0.0 if row.water_central <= 0 else row.water_central
        for xx, yy in ((xc, row.energy_central), (xc, row.energy_low), (xc, row.energy_high),
                       (max(row.water_low, LOG_XLIM[0]) if row.water_central > 0 else 0, row.energy_central),
                       (row.water_high if row.water_central > 0 else 0, row.energy_central)):
            pts.append((row.arch_key, a.transData.transform((xx, yy / 1e6))))
    # leader lines, sampled every display pixel (a leader may touch only its own label)
    for lk, la, (x0, y0), (x1, y1) in getattr(fig, "_leaders", []):
        p0 = np.array(la.transData.transform((x0, y0 / 1e6 if y0 > 1e3 else y0)))
        p1 = np.array(la.transData.transform((x1, y1)))
        n = int(np.hypot(*(p1 - p0))) + 2
        for f in np.linspace(0.02, 0.98, n):
            pts.append(("leader:" + lk, p0 + f * (p1 - p0)))
    hits = []
    for key, tx in texts.items():
        bb = tx.get_window_extent(r)
        for pk, (px, py) in pts:
            if pk == "leader:" + key:
                continue
            if bb.x0 - k < px < bb.x1 + k and bb.y0 - k < py < bb.y1 + k:
                hits.append((key, pk))
    return sorted(set(hits))


def edge_margins_mm(fig) -> dict:
    """Smallest distance (mm) from any visible text box to each figure edge."""
    import matplotlib.text as mtext
    fig.canvas.draw(); r = fig.canvas.get_renderer(); fb = fig.bbox; px_mm = fig.dpi / 25.4
    bbs = [t.get_window_extent(r) for t in fig.findobj(mtext.Text) if t.get_visible() and t.get_text().strip()]
    return {"left": min(b.x0 - fb.x0 for b in bbs) / px_mm, "right": min(fb.x1 - b.x1 for b in bbs) / px_mm,
            "bottom": min(b.y0 - fb.y0 for b in bbs) / px_mm, "top": min(fb.y1 - b.y1 for b in bbs) / px_mm}


MIN_EDGE_MM = 0.8


def save_figure(fig, stem: str):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(FIGURES / f"{stem}.{ext}", dpi=300)


# ------------------------------------------------------------------------------------------------------ text
def _g(x: float) -> str:
    """Three significant figures with thousands separators."""
    if x == 0:
        return "0"
    d = int(np.floor(np.log10(abs(x))))
    v = round(x, -d + 2)
    return f"{v:,.0f}" if d >= 2 else f"{v:,.{max(0, 2 - d)}f}"


def _m(x: float) -> str:
    return f"{x / 1e6:.2f} million"


def caption(t: pd.DataFrame, model: dict) -> str:
    T = t.set_index("arch_key")
    tw, hy, ac, aw, aa, fa = (T.loc[k] for k in ("evaporative_tower", "hybrid", "air_cooled_chiller",
                                                  "airside_adiabatic_wcc", "airside_adiabatic_acc",
                                                  "falls_township"))
    cal = model["calibration"]
    W = "[water_energy_frontier.csv]"   # per-row values are tabulated in results/water_energy_frontier.csv
    return (
        "**Figure X.**\n\n"
        "The chart shows annual cooling water and non-IT energy per megawatt of IT load for five cooling "
        "architectures at Trenton, New Jersey. Points are central values, and bars span the low and high values "
        "on each axis. Filled circles are modelled on Trenton hourly wet-bulb temperature for 2005 to 2024 "
        "[noaa_isd, stull_2011, reuse_ready_model]. Open circles take water from the LBNL simulated or reported "
        "site water usage effectiveness [shehabi_2024]. The open diamond is the Falls Township (AWS Keystone) "
        f"filing of {_g(FALLS_AVG_GPD)} gallons per day [falls_levittown_2026]. That figure is multiplied by 365 and "
        f"divided by the calibrated {cal['p_it_mw']:.2f} MW of IT load, which gives {_g(fa.water_central)} gallons "
        f"per MW-year [reuse_ready_model]. The diamond is placed at the assumed power usage effectiveness (PUE) of "
        f"{cal['pue']:.1f} [reuse_ready_model]. It coincides with the hybrid central value because the hybrid is "
        "calibrated to that filing.\n\n"
        "Energy is (PUE minus 1) times 8,760,000 kWh per MW-year, with PUE read from LBNL 2024 Figure 4.4 on page "
        "46 [shehabi_2024]. The median gives the central value, and the whisker ends give the range. Because PUE "
        f"minus 1 includes all non-IT load, it bounds cooling energy from above {W}. Each PUE row below is given as "
        "its low, central and high values. The evaporative tower uses the Large-scale waterside economizer "
        f"(water-cooled chiller) row, {tw.pue_low:.3f}, {tw.pue_central:.3f} and {tw.pue_high:.3f} {W}. The hybrid "
        f"uses the Large-scale dry cooler with adiabatic assist, {hy.pue_low:.3f}, {hy.pue_central:.3f} and "
        f"{hy.pue_high:.3f} {W}. The air-cooled chiller uses the Midsize air-cooled chiller, {ac.pue_low:.3f}, "
        f"{ac.pue_central:.3f} and {ac.pue_high:.3f}, because LBNL draws no Large-scale air-cooled chiller {W}. "
        "The two airside rows use the Large-scale airside economizer and adiabatic cooling rows, "
        f"{aw.pue_low:.3f}, {aw.pue_central:.3f} and {aw.pue_high:.3f} (water-cooled chiller) and "
        f"{aa.pue_low:.3f}, {aa.pue_central:.3f} and {aa.pue_high:.3f} (air-cooled chiller) [shehabi_2024]. "
        "Values were digitized from the figure raster at a resolution of 0.005 in PUE and 0.014 L/kWh "
        "[reuse_ready_model].\n\n"
        "Modelled water scales with PUE. Its range combines the lowest calendar-year total at the low PUE with the "
        "highest at the high PUE [reuse_ready_model]. Water for the water-cooled airside row is the Figure 4.4 site "
        f"WUE, {aw.lbnl_wue_low:.2f}, {aw.lbnl_wue_central:.2f} and {aw.lbnl_wue_high:.2f} L/kWh [shehabi_2024]. "
        "It is converted at 8,760,000 kWh per MW-year and 3.785411784 L per gallon [reuse_ready_model]. LBNL "
        "describes the simulated WUE of the air-cooled airside row as likely low. Water for that row is therefore "
        f"the {LBNL_P47_REPORTED_WUE['low']:.1f} to {LBNL_P47_REPORTED_WUE['high']:.1f} L/kWh that hyperscale "
        f"operators report for similar systems, centred on {LBNL_P47_REPORTED_WUE['central']:.1f} L/kWh (page 47) "
        "[shehabi_2024]. The air-cooled chiller uses no evaporative makeup and is plotted in the separate zero "
        "panel [reuse_ready_model]. The lower end of the water-cooled airside range is also zero and continues into "
        "that panel [shehabi_2024]. Plotted values are in figures/water_energy_frontier_data.csv and "
        "results/water_energy_frontier.csv."
    )


def results_fragment(t: pd.DataFrame, model: dict) -> str:
    T = t.set_index("arch_key")
    tw, hy, ac, aw, aa, tm = (T.loc[k] for k in ("evaporative_tower", "hybrid", "air_cooled_chiller",
                                                  "airside_adiabatic_wcc", "airside_adiabatic_acc",
                                                  "evaporative_tower_midsize"))
    ss = json.loads((RESULTS / "supply_summary.json").read_text())
    peak_per_mw = ss["demand_rates"]["peak_day_gpd_per_mw"]
    n_match, n_sites = ss["class_counts"]["matchable"], ss["n_sites"]
    pen_hyb = ac.energy_central - hy.energy_central
    pen_like = ac.energy_central - tm.energy_central
    return (
        "The cooling-system choice trades water against electricity, which is the first reason developers resist "
        "reuse-first terms. At Trenton an evaporative tower uses about "
        f"{_g(tw.water_central)} gallons per MW-year of IT load and the calibrated hybrid about "
        f"{_g(hy.water_central)} gallons [reuse_ready_model; water_energy_frontier.csv], while an air-cooled "
        "chiller uses no evaporative makeup [reuse_ready_model]. The air-cooled chiller pays for that in energy: "
        f"its median non-IT load in LBNL 2024 Figure 4.4 is PUE {ac.pue_central:.2f}, or {_m(ac.energy_central)} "
        f"kWh per MW-year, against PUE {hy.pue_central:.2f} ({_m(hy.energy_central)} kWh) for a Large-scale dry "
        f"cooler with adiabatic assist and PUE {tw.pue_central:.2f} ({_m(tw.energy_central)} kWh) for a "
        "Large-scale waterside economizer with a cooling tower [shehabi_2024; water_energy_frontier.csv]. Part "
        "of that gap reflects facility size, because LBNL draws the air-cooled chiller only for Midsize "
        f"facilities; within the Midsize class the gap between air-cooled and water-cooled chillers is "
        f"{_m(pen_like)} kWh per MW-year, compared with {_m(pen_hyb)} kWh between the air-cooled chiller and the "
        "hybrid [shehabi_2024; water_energy_frontier.csv]. LBNL states the same tradeoff directly: evaporative "
        "systems are generally more energy efficient, and air-cooled chillers use no water but more energy "
        "[shehabi_2024, p. 45]. The second reason is treatment. Secondary municipal effluent carries "
        "biodegradable organic matter, ammonia, carbonate and phosphate that drive biofouling, corrosion and "
        "scaling, and a Department of Energy study of power plant cooling found tertiary treatment essential for its "
        "use in recirculating systems [dzombak_2012, PDF p. 3]; it estimated tertiary-treated makeup at $0.91 to $1.32 per thousand gallons in 2009 dollars, above the $0.74 "
        "for river withdrawal and treatment and below the $2.95 average for city water, and the DRBC raw-water "
        "rate in the same comparison was $0.08 per thousand gallons [dzombak_2012, PDF pp. 15 and 190]. Supply "
        f"reliability is a related concern: at the calibrated peak-day rate of {_g(peak_per_mw)} gallons per day per "
        f"MW of IT load [supply_summary.json], {n_match} of {n_sites} planned sites sit within 10 miles of a "
        "treatment plant whose median flow could cover their peak demand [supply_summary.json]. The third is "
        "approval: the basin's data centers buy water from public systems and none has applied to the Commission "
        "[drbc_datacenters_2026], so a reuse contract replaces a supply that needs no Commission review with a "
        "new treatment and delivery arrangement, whose state approvals were not reviewed here. Reclaimed water "
        "changes the tradeoff because it lowers the scarcity cost of the water axis rather than moving any point "
        "along it. An evaporative tower or the calibrated hybrid supplied from effluent keeps its energy "
        f"advantage of {_m(ac.energy_central - tw.energy_central)} and {_m(pen_hyb)} kWh per MW-year over the "
        "air-cooled chiller [water_energy_frontier.csv] while drawing nothing from potable or river supply, so on "
        "the two quantities a basin regulator weighs, fresh-water withdrawal and electricity, it dominates the "
        "air-cooled design, provided the energy for tertiary treatment and delivery of the effluent, which is not "
        "counted here, stays below that margin. The airside economizer with adiabatic cooling reaches a lower median PUE, "
        f"{aw.pue_central:.2f} with a water-cooled chiller and {aa.pue_central:.2f} with an air-cooled chiller "
        f"[shehabi_2024], using {_g(aw.water_central)} and {_g(aa.water_central)} gallons per MW-year "
        "[water_energy_frontier.csv]; these designs are also candidates for effluent supply, although the "
        "reported water use of the air-cooled variant, 0.1 to 0.3 L/kWh, is well above LBNL's simulated value "
        "[shehabi_2024, p. 47]."
    )


def main():
    lbnl = digitize_fig44()
    lbnl.to_csv(RESULTS / "lbnl_fig44_digitized.csv")
    model = model_annual_water_per_mw()
    t = build_table(lbnl, model)
    t.to_csv(RESULTS / "water_energy_frontier.csv", index=False, float_format="%.6g")
    fig, axes, texts, data = render_figure(t)
    ov = overlap_report(fig)
    hits = symbol_label_hits(fig, axes, texts, t)
    edges = edge_margins_mm(fig)
    save_figure(fig, "water_energy_frontier")
    data.to_csv(FIGURES / "water_energy_frontier_data.csv", index=False, float_format="%.6g")
    (FIGURES / "water_energy_frontier_caption.md").write_text(caption(t, model) + "\n")
    (RESULTS / "water_energy_frontier_check.json").write_text(json.dumps(
        {"text_overlaps": ov, "label_symbol_hits": hits, "edge_margins_mm": edges, "model": model,
         "figure_mm": [FIG_W_MM, FIG_H_MM]}, indent=2, default=str))
    frag = ROOT_FRAG / "agentD_results.md"
    frag.parent.mkdir(parents=True, exist_ok=True)
    frag.write_text(results_fragment(t, model) + "\n")
    print(json.dumps({"overlaps": ov, "label_symbol_hits": hits, "edge_margins_mm": edges}, default=str))
    return t


from .paths import ROOT  # noqa: E402

ROOT_FRAG = ROOT / "scratch" / "fragments"

if __name__ == "__main__":
    main()
