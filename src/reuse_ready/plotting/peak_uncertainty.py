"""Monte Carlo uncertainty figures, v3 house style (styles.v2_rc, Helvetica, V2 palette, no titles, no sentences).

  figures/peak_uncertainty.*     range bars per site, sorted by P50: P50 dot, P50 to P90 bar, P90 tick, open
                                 square at the nearest eligible plant's median flow; 180 mm wide
  figures/sites_mc_ridgeline.*   per-site kernel density of log10 peak-day makeup, sorted by median; 180 mm wide
  figures/falls_mc_fan.*         Falls Township daily makeup, 300 Monte Carlo traces (parameter draw x weather year)
                                 with the P10 to P90 band and P50 by day of year; 180 x 80 mm
Each writes <stem>.{png,pdf,svg}, <stem>_caption.md and <stem>_data.csv; checks go to
results/peak_uncertainty_figure_check.json. Inputs come from reuse_ready.uncertainty (results/peak_uncertainty.*,
results/falls_mc_fan.json).
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import matplotlib.text as mtext
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, NullFormatter
from scipy.stats import gaussian_kde

from .. import styles as S
from .. import uncertainty as UNC
from ..paths import FIGURES, RESULTS
from . import figures_v2 as V2

W_MM = 180.0
NO_PLANT = "no eligible plant within 10 mi"
GRAY_ROW = "#EDEDED"
SRC_SITES = "Sources: LBNL 2024; U.S. EPA ECHO; NOAA ISD; trackdatacenters.com."
SRC_FALLS = "Sources: LBNL 2024; NOAA ISD; Falls Township filings."


def short_name(name: str, max_len: int = 42) -> str:
    s = name.split(" / ")[0].strip()
    for a, b in (("Data Center", "DC"), ("Data Centers", "DCs"), ("Infrastructure", "Infra."), ("Township", "Twp")):
        s = s.replace(a, b)
    return s if len(s) <= max_len else s[: max_len - 1].rstrip() + "."


def _row_label(num, name):
    return f"{int(num)}  {short_name(name)}"


def _fmt(v: float) -> str:
    return f"{v:,.0f}"


def _minfont(fig):
    return float(min(t.get_fontsize() for t in fig.findobj(mtext.Text) if t.get_text().strip()))


def _save(fig, stem):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(f"{FIGURES / stem}.{ext}", dpi=S.V2_DPI)


def _log_axis(ax, lim, ticks, axis="x"):
    getattr(ax, f"set_{axis}scale")("log")
    getattr(ax, f"set_{axis}lim")(*lim)
    a = getattr(ax, f"{axis}axis")
    a.set_major_locator(FixedLocator(ticks))
    a.set_minor_formatter(NullFormatter())
    getattr(ax, f"set_{axis}ticklabels")([_fmt(t) for t in ticks])
    ax.tick_params(axis=axis, which="minor", length=1.5, width=S.V2_LW_TERTIARY)


def _site_table():
    d = pd.read_csv(RESULTS / "peak_uncertainty.csv")
    d["has_plant"] = np.isfinite(d.plant_median_gpd)
    d["label"] = [_row_label(n, nm) for n, nm in zip(d.map_number, d.name)]
    return d


# ------------------------------------------------------------------------------------------------ range bars
RB_ROW_MM, RB_TOP_MM, RB_BOT_MM, RB_LEFT_MM, RB_RIGHT_MM = 4.2, 8.0, 11.5, 50.0, 30.0
RB_XLIM = (3e5, 4e7)
RB_TICKS = [5e5, 1e6, 2e6, 5e6, 1e7, 2e7]


def render_range_bars() -> dict:
    S.v2_rc()
    narrow = S.narrow_family()
    d = _site_table().sort_values(["p50_peak_day_gpd", "map_number"]).reset_index(drop=True)
    n = len(d)
    h_mm = RB_TOP_MM + RB_BOT_MM + RB_ROW_MM * n
    fig = plt.figure(figsize=(W_MM * V2.MM, h_mm * V2.MM), dpi=S.V2_DPI)
    aw = W_MM - RB_LEFT_MM - RB_RIGHT_MM
    ax = fig.add_axes([RB_LEFT_MM / W_MM, RB_BOT_MM / h_mm, aw / W_MM, RB_ROW_MM * n / h_mm])
    _log_axis(ax, RB_XLIM, RB_TICKS)
    ax.set_ylim(n - 0.5, -0.5)
    for t in RB_TICKS:
        ax.axvline(t, color=S.V2_GRAY_LIGHT, lw=S.V2_LW_TERTIARY, zorder=0)
    notes = []
    for i, r in d.iterrows():
        if not r.has_plant:
            ax.axhspan(i - 0.5, i + 0.5, color=GRAY_ROW, lw=0, zorder=0.5)
        c_bar = S.V2_ACCENT_HALF if r.has_plant else S.V2_GRAY_LIGHT
        c_pt = S.V2_ACCENT if r.has_plant else S.V2_GRAY
        ax.plot([r.p50_peak_day_gpd, r.p90_peak_day_gpd], [i, i], color=c_bar, lw=3.0, solid_capstyle="butt",
                zorder=2)
        ax.plot([r.p90_peak_day_gpd] * 2, [i - 0.3, i + 0.3], color=c_pt, lw=S.V2_LW_PRIMARY, zorder=3)
        ax.scatter([r.p50_peak_day_gpd], [i], s=9, color=c_pt, lw=0, zorder=4)
        if r.has_plant:
            ax.scatter([r.plant_median_gpd], [i], s=14, marker="s", facecolor="none", edgecolor=S.V2_BLACK,
                       linewidths=S.V2_LW_SECONDARY, zorder=5)
        note = ("No plant within 10 mi" if not r.has_plant else
                "P90 exceeds plant" if r.p90_peak_day_gpd > r.plant_median_gpd else "Plant covers P90")
        notes.append(note)
        if note:
            ax.text(1.0 + 2.0 / aw, i, note, transform=ax.get_yaxis_transform(), ha="left", va="center",
                    fontsize=S.V2_FONT_SIZE, color=S.V2_GRAY_DARK if not r.has_plant else S.V2_BLACK)
    ax.set_yticks(np.arange(n))
    ax.set_yticklabels(d.label, family=narrow)
    for lab, hp in zip(ax.get_yticklabels(), d.has_plant):
        if not hp:
            lab.set_color(S.V2_GRAY_DARK)
    ax.tick_params(axis="y", length=0, pad=2.0)
    ax.set_xlabel("Peak-day cooling makeup or plant median flow (gallons per day)", labelpad=2.0)
    for s_ in ("top", "right", "left"):
        ax.spines[s_].set_visible(False)
    handles = [Line2D([], [], marker="o", markersize=3.4, color=S.V2_ACCENT, lw=0, label="P50"),
               Line2D([], [], color=S.V2_ACCENT_HALF, lw=3.0, solid_capstyle="butt", label="P50 to P90"),
               Line2D([], [], marker="|", markersize=6, markeredgewidth=S.V2_LW_PRIMARY, color=S.V2_ACCENT, lw=0,
                      label="P90"),
               Line2D([], [], marker="s", markersize=3.8, markerfacecolor="none", markeredgecolor=S.V2_BLACK,
                      markeredgewidth=S.V2_LW_SECONDARY, lw=0, label="Nearest plant median flow"),
               Patch(facecolor=GRAY_ROW, edgecolor="none", label="No plant within 10 mi")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(RB_LEFT_MM / W_MM, 1 - 1.2 / h_mm), ncol=5,
               frameon=False, fontsize=S.V2_FONT_SIZE, handlelength=2.0, columnspacing=1.8, borderaxespad=0,
               handletextpad=0.5)
    S.v2_source_line(fig, SRC_SITES, y_mm=1.2, x_mm=2.0)
    overlaps = V2.text_overlaps(fig)
    _save(fig, "peak_uncertainty")
    mf = _minfont(fig)
    plt.close(fig)
    d["row_top_to_bottom"] = np.arange(1, n + 1)
    d["right_margin_note"] = notes
    cols = ["row_top_to_bottom", "map_number", "site_id", "name", "label", "it_mw_basis", "it_mw_stated",
            "p10_peak_day_gpd", "p50_peak_day_gpd", "p90_peak_day_gpd", "plant_median_gpd", "has_plant",
            "right_margin_note", "prob_covered", "covers_p50", "covers_p90", "deterministic_class", "class_p90_cap"]
    d[cols].to_csv(FIGURES / "peak_uncertainty_data.csv", index=False)
    return {"text_overlaps": overlaps, "min_font_pt": mf, "size_mm": [W_MM, h_mm],
            "n_notes_p90_exceeds": int(sum(x == "P90 exceeds plant" for x in notes)),
            "n_notes_no_plant": int(sum(x == "No plant within 10 mi" for x in notes)),
            "n_notes_plant_covers_p90": int(sum(x == "Plant covers P90" for x in notes))}


# ------------------------------------------------------------------------------------------------ ridgeline
RL_ROW_MM, RL_TOP_MM, RL_BOT_MM, RL_LEFT_MM, RL_RIGHT_MM = 5.2, 9.0, 11.5, 50.0, 6.0
RL_LOG = (5.0, 7.7)
RL_TICKS = [1e5, 3e5, 1e6, 3e6, 1e7, 3e7]
RL_HEIGHT = 1.45      # peak height of each density in row units (1 = row spacing), gives slight overlap
RL_GRID = 400


def ridgeline_data():
    ss, dem = UNC.primary_site_draws()
    d = _site_table().set_index("site_id")
    grid = np.linspace(*RL_LOG, RL_GRID)
    rows, curves = [], {}
    for i, sid in enumerate(ss.site_id):
        v = dem[i]
        pos = v[v > 0]
        lv = np.log10(pos)
        k = gaussian_kde(lv)
        dens = k(grid)
        curves[sid] = dens
        rows.append({"site_id": sid, "median_gpd": float(np.median(v)), "p90_gpd": float(np.quantile(v, 0.9)),
                     "share_zero_draws": float((v == 0).mean()),
                     "share_below_axis": float((v < 10 ** RL_LOG[0]).mean()),
                     "share_above_axis": float((v > 10 ** RL_LOG[1]).mean()),
                     "kde_bandwidth_log10": float(k.factor * lv.std(ddof=1)), "n_positive": int(len(pos))})
    r = pd.DataFrame(rows).set_index("site_id").join(d[["map_number", "name", "label", "plant_median_gpd",
                                                        "has_plant"]])
    return r, grid, curves


def render_ridgeline() -> dict:
    S.v2_rc()
    narrow = S.narrow_family()
    r, grid, curves = ridgeline_data()
    r = r.sort_values(["median_gpd", "map_number"]).reset_index()
    n = len(r)
    h_mm = RL_TOP_MM + RL_BOT_MM + RL_ROW_MM * n
    fig = plt.figure(figsize=(W_MM * V2.MM, h_mm * V2.MM), dpi=S.V2_DPI)
    aw = W_MM - RL_LEFT_MM - RL_RIGHT_MM
    ax = fig.add_axes([RL_LEFT_MM / W_MM, RL_BOT_MM / h_mm, aw / W_MM, RL_ROW_MM * n / h_mm])
    x = 10 ** grid
    _log_axis(ax, (x[0], x[-1]), RL_TICKS)
    # row i baseline at y = n - 1 - i (first row at the top); densities rise upward and overlap the row above
    ax.set_ylim(-0.25, n - 1 + RL_HEIGHT + 0.08)
    for t in RL_TICKS:
        ax.axvline(t, color=S.V2_GRAY_LIGHT, lw=S.V2_LW_TERTIARY, zorder=0)
    out_rows = []
    for i, rr in r.iterrows():
        base = n - 1 - i
        dens = curves[rr.site_id]
        y = base + RL_HEIGHT * dens / dens.max()
        fc = S.V2_ACCENT if rr.has_plant else S.V2_GRAY
        z = 10 + i * 3        # lower rows drawn in front of upper rows
        ax.fill_between(x, base, y, facecolor=fc, alpha=0.30, lw=0, zorder=z)
        ax.plot(x, y, color=fc, lw=S.V2_LW_SECONDARY, zorder=z + 1)
        ax.plot([x[0], x[-1]], [base, base], color=fc, lw=S.V2_LW_TERTIARY, zorder=z + 1)
        yp = base + RL_HEIGHT * np.interp(np.log10(rr.p90_gpd), grid, dens) / dens.max()
        # markers sit above every ridge (zorder 200+), so a lower row's ridge rising into this row cannot hide them
        ax.plot([rr.p90_gpd] * 2, [base, base + 0.32], color=S.V2_ACCENT if rr.has_plant else S.V2_GRAY_DARK,
                lw=S.V2_LW_PRIMARY, zorder=200 + i)
        if rr.has_plant:
            ax.plot([rr.plant_median_gpd] * 2, [base - 0.18, base + 0.55], color=S.V2_BLACK, lw=1.1, zorder=250 + i)
        for xv, yv in zip(x, y):
            out_rows.append({"site_id": rr.site_id, "map_number": int(rr.map_number), "row_top_to_bottom": i + 1,
                             "baseline_y": base, "x_gpd": xv, "y_plotted": yv, "density_log10": None})
        out_rows[-len(x):] = [{**o, "density_log10": dv} for o, dv in zip(out_rows[-len(x):], dens)]
    ax.set_yticks([n - 1 - i for i in range(n)])
    ax.set_yticklabels(r.label, family=narrow, va="bottom")
    for lab, hp in zip(ax.get_yticklabels(), r.has_plant):
        if not hp:
            lab.set_color(S.V2_GRAY_DARK)
    ax.tick_params(axis="y", length=0, pad=2.0)
    for s_ in ("top", "right", "left"):
        ax.spines[s_].set_visible(False)
    ax.set_xlabel("Simulated peak-day cooling makeup (gallons per day)", labelpad=2.0)
    handles = [Patch(facecolor=S.V2_ACCENT, alpha=0.30, edgecolor=S.V2_ACCENT, lw=S.V2_LW_SECONDARY,
                     label="Density of draws"),
               Line2D([], [], marker="|", markersize=5, markeredgewidth=S.V2_LW_PRIMARY, color=S.V2_ACCENT, lw=0,
                      label="P90"),
               Line2D([], [], marker="|", markersize=8, markeredgewidth=1.1, color=S.V2_BLACK, lw=0,
                      label="Nearest plant median flow"),
               Patch(facecolor=S.V2_GRAY, alpha=0.30, edgecolor=S.V2_GRAY, lw=S.V2_LW_SECONDARY,
                     label="No plant within 10 mi")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(RL_LEFT_MM / W_MM, 1 - 1.2 / h_mm), ncol=4,
               frameon=False, fontsize=S.V2_FONT_SIZE, handlelength=2.0, columnspacing=2.0, borderaxespad=0,
               handletextpad=0.5)
    S.v2_source_line(fig, SRC_SITES, y_mm=1.2, x_mm=2.0)
    overlaps = V2.text_overlaps(fig)
    _save(fig, "sites_mc_ridgeline")
    mf = _minfont(fig)
    plt.close(fig)
    curves_df = pd.DataFrame(out_rows)
    curves_df["element"] = "density_curve"
    summ = r.assign(row_top_to_bottom=np.arange(1, n + 1), element="site_summary",
                    p90_above_plant=r.has_plant & (r.p90_gpd > r.plant_median_gpd))
    data = pd.concat([summ, curves_df], ignore_index=True)
    first = ["element", "row_top_to_bottom", "map_number", "site_id", "name", "label", "median_gpd", "p90_gpd",
             "plant_median_gpd", "has_plant", "p90_above_plant", "share_zero_draws", "share_below_axis",
             "share_above_axis", "kde_bandwidth_log10", "n_positive", "baseline_y", "x_gpd", "density_log10",
             "y_plotted"]
    data[first].to_csv(FIGURES / "sites_mc_ridgeline_data.csv", index=False)
    return {"text_overlaps": overlaps, "min_font_pt": mf, "size_mm": [W_MM, h_mm],
            "n_p90_above_plant": int(summ.p90_above_plant.sum()),
            "sites_p90_above_plant": summ.loc[summ.p90_above_plant, "site_id"].tolist(),
            "zero_share_range": [float(r.share_zero_draws.min()), float(r.share_zero_draws.max())],
            "below_axis_share_range": [float(r.share_below_axis.min()), float(r.share_below_axis.max())]}


# ------------------------------------------------------------------------------------------------ Falls fan
FAN_H_MM = 80.0
FAN_LEFT_MM, FAN_RIGHT_MM, FAN_BOT_MM, FAN_TOP_MM = 20.0, 27.0, 13.0, 3.0
FAN_YLIM = (UNC.FAN_FLOOR_GPD * 0.8, 1.2e7)
FAN_YTICKS = [1e3, 1e4, 1e5, 1e6, 1e7]
FAN_DOY_TICKS = [1, 60, 121, 182, 244, 305, 366]
JJA = (152, 243)   # 1 June to 31 August, non-leap day-of-year numbering


def render_fan() -> dict:
    S.v2_rc()
    F = UNC.falls_fan()
    info, D, idx, q = F["info"], F["daily"], F["plot_idx"], F["q"]
    floor = UNC.FAN_FLOOR_GPD
    doy = np.arange(1, 367)
    fig = plt.figure(figsize=(W_MM * V2.MM, FAN_H_MM * V2.MM), dpi=S.V2_DPI)
    aw = W_MM - FAN_LEFT_MM - FAN_RIGHT_MM
    ah = FAN_H_MM - FAN_BOT_MM - FAN_TOP_MM
    ax = fig.add_axes([FAN_LEFT_MM / W_MM, FAN_BOT_MM / FAN_H_MM, aw / W_MM, ah / FAN_H_MM])
    _log_axis(ax, FAN_YLIM, FAN_YTICKS, axis="y")
    ax.set_xlim(1, 366)
    ax.axvspan(*JJA, color=S.V2_OUTSIDE, lw=0, zorder=0)
    for i in idx:
        ax.plot(doy, np.maximum(D[i], floor), color=S.V2_ACCENT, lw=0.25, alpha=0.04, zorder=2)
    lo, med, hi = (np.maximum(v, floor) for v in q)
    ax.fill_between(doy, lo, hi, where=np.isfinite(hi), facecolor=S.V2_ACCENT, alpha=0.20, lw=0, zorder=3)
    ax.plot(doy, med, color=S.V2_ACCENT, lw=1.0, zorder=4)
    refs = [(1e5, "100,000 gal/day\n(DRBC trigger)"), (4.4e6, "4.4 MGD\n(reported peak)")]
    for yv, lab in refs:
        ax.axhline(yv, color=S.V2_GRAY, lw=S.V2_LW_SECONDARY, linestyle=S.V2_DASH, zorder=5)
        ax.text(1.0 + 1.5 / aw, yv, lab, transform=ax.get_yaxis_transform(), ha="left", va="center",
                fontsize=S.V2_FONT_SIZE, color=S.V2_GRAY_DARK, linespacing=1.1)
    jja_lab = ax.text((JJA[0] + JJA[1]) / 2, FAN_YLIM[1] / 1.25, "June to August", ha="center", va="top",
                      fontsize=S.V2_FONT_SIZE, color=S.V2_GRAY_DARK, zorder=6)
    ax.set_xticks(FAN_DOY_TICKS)
    ax.set_xlabel("Day of year", labelpad=2.0)
    ax.set_ylabel("Modeled daily makeup (gallons per day)", labelpad=2.0)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    handles = [Line2D([], [], color=S.V2_ACCENT, lw=0.6, alpha=0.35, label="Single trace"),
               Patch(facecolor=S.V2_ACCENT, alpha=0.20, lw=0, label="P10 to P90"),
               Line2D([], [], color=S.V2_ACCENT, lw=1.0, label="P50")]
    leg = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.01, 0.99), ncol=3, frameon=False,
                    fontsize=S.V2_FONT_SIZE, handlelength=1.6, columnspacing=1.0, borderaxespad=0.2,
                    handletextpad=0.4)
    S.v2_source_line(fig, SRC_FALLS, y_mm=1.2, x_mm=2.0)
    overlaps = V2.text_overlaps(fig)
    # the legend row must end at least 1 mm left of the June to August panel
    fig.canvas.draw()
    leg_x1 = leg.get_window_extent(fig.canvas.get_renderer()).x1
    jja_x0 = ax.transData.transform((JJA[0], 1.0))[0]
    legend_gap_mm = float((jja_x0 - leg_x1) / fig.dpi * 25.4)
    if legend_gap_mm < 1.0:
        overlaps.append(("legend", "June to August panel"))
    # the panel label must clear the dashed reference lines and every plotted trace, band and P50 value
    bb = jja_lab.get_window_extent(fig.canvas.get_renderer())
    inv = ax.transData.inverted()
    (dx0, dy0), (dx1, dy1) = inv.transform((bb.x0, bb.y0)), inv.transform((bb.x1, bb.y1))
    cols = (doy >= dx0) & (doy <= dx1)
    plotted_max = np.nanmax(np.r_[np.maximum(D[idx][:, cols], floor).ravel(), hi[cols], med[cols]])
    if plotted_max >= dy0:
        overlaps.append(("June to August", "traces"))
    if any(dy0 <= yv <= dy1 for yv, _ in refs):
        overlaps.append(("June to August", "reference line"))
    jja_clear_mm = float((ax.transData.transform((1, dy0))[1] - ax.transData.transform((1, max(
        plotted_max, max(yv for yv, _ in refs))))[1]) / fig.dpi * 25.4)
    _save(fig, "falls_mc_fan")
    mf = _minfont(fig)
    plt.close(fig)
    P = F["params"]
    rows = []
    for k, i in enumerate(idx):
        p = P.iloc[i]
        for j in range(366):
            v = D[i, j]
            rows.append(("trace", k, int(i), j + 1, int(p.weather_year), p.p_it_mw, p.pue, p.gamma, v,
                         np.nan if np.isnan(v) else max(v, floor)))
    for name, arr in (("p10_all_draws", q[0]), ("p50_all_draws", q[1]), ("p90_all_draws", q[2])):
        for j in range(366):
            v = arr[j]
            rows.append((name, np.nan, np.nan, j + 1, np.nan, np.nan, np.nan, np.nan, v,
                         np.nan if np.isnan(v) else max(v, floor)))
    for yv, lab in refs:
        rows.append(("reference_line", np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, yv, yv))
    rows.append(("jja_shading_start_doy", np.nan, np.nan, JJA[0], np.nan, np.nan, np.nan, np.nan, np.nan, np.nan))
    rows.append(("jja_shading_end_doy", np.nan, np.nan, JJA[1], np.nan, np.nan, np.nan, np.nan, np.nan, np.nan))
    df = pd.DataFrame(rows, columns=["element", "trace", "draw", "doy", "weather_year", "p_it_mw", "pue", "gamma",
                                     "makeup_gpd", "plotted_gpd"])
    df.to_csv(FIGURES / "falls_mc_fan_data.csv", index=False, float_format="%.6g")
    return {"text_overlaps": overlaps, "min_font_pt": mf, "size_mm": [W_MM, FAN_H_MM],
            "legend_to_jja_panel_mm": legend_gap_mm, "jja_label_clearance_mm": jja_clear_mm, "n_traces": int(len(idx)), "info": {k: v for k, v in info.items() if k != "distributions"}}


# ------------------------------------------------------------------------------------------------ captions
def _n(v, nd=0):
    return f"{v:,.{nd}f}"


def _mc_common(m) -> str:
    p = m["scenarios"]["primary"]
    w = m["distributions"]["architecture_weights_primary"]
    wue = m["distributions"]["wue_l_per_kwh_five_number"]
    ev, hy = wue["large_waterside_econ_wcc"], wue["large_airside_econ_adiabatic_wcc"]
    pool = m["distributions"]["it_load"]["pool_mw"]
    conv = m["conversion"]["model"]
    return (f"Each of the {m['n_draws']:,} draws (random seed {m['seed']}) samples its inputs as follows "
            f"[peak_uncertainty.json]. The cooling architecture is drawn with LBNL's 2023 hyperscale cooling-system "
            f"shares, grouped into evaporative tower ({w['evaporative_tower']:.3f}), hybrid ({w['hybrid']:.3f}) and "
            f"air-cooled chiller ({w['air_cooled_chiller']:.3f}) [shehabi_2024, p. 39]. The annual site water usage "
            f"effectiveness (WUE) is drawn from LBNL's large-scale simulation ranges. These are "
            f"{_n(ev['lower_whisker'], 2)} to {_n(ev['upper_whisker'], 2)} liters per kilowatt-hour (median "
            f"{_n(ev['median'], 2)}) for the evaporative tower and {_n(max(hy['lower_whisker'], 0), 2)} to "
            f"{_n(hy['upper_whisker'], 2)} liters per kilowatt-hour (median {_n(hy['median'], 2)}) for the hybrid "
            f"[shehabi_2024, p. 46]. The air-cooled chiller has zero makeup [reuse_ready_model]. Power usage "
            f"effectiveness is uniform on 1.15 to 1.35 [shehabi_2024, p. 48]. Annual WUE is converted to peak-day "
            f"makeup with the calibrated cooling model's ratio of maximum day to mean day on Trenton weather for 2005 "
            f"to 2024 [reuse_ready_model, noaa_isd]. The ratio is "
            f"{_n(conv['evaporative_tower']['peak_to_average'], 1)} for the evaporative tower and "
            f"{_n(conv['hybrid']['peak_to_average'], 1)} for the calibrated hybrid [peak_uncertainty.json]. Hybrid "
            f"draws are capped at full evaporation of the day's heat, and the cap binds in "
            f"{100 * p['hybrid_draws_capped_share']:.0f} percent of hybrid draws [reuse_ready_model]. Sites that "
            f"state a capacity use it. The 16 sites that do not state one draw their IT load with equal probability "
            f"from the {len(pool)} stated values, {_n(min(pool))} to {_n(max(pool))} MW [peak_uncertainty.json, "
            f"trackdatacenters_2026]. Plant flows are median monthly discharge reported from July 2023 to June 2026 "
            f"[epa_echo].")


def write_captions(rb: dict, rl: dict, fan: dict) -> None:
    m = json.loads((RESULTS / "peak_uncertainty.json").read_text())
    p = m["scenarios"]["primary"]
    common = _mc_common(m)
    assert (rb["n_notes_p90_exceeds"], rb["n_notes_plant_covers_p90"], rb["n_notes_no_plant"]) == \
        (p["n_p90_above_plant"], p["n_covers_p90"], p["n_no_eligible_plant"])
    ch_list = [f"{r['name']} ({r['site_id']})" for r in p["class_changes_at_p90"]]
    ch = ch_list[0] if len(ch_list) == 1 else ", ".join(ch_list[:-1]) + " and " + ch_list[-1]
    (FIGURES / "peak_uncertainty_caption.md").write_text(f"""# Figure X (peak_uncertainty)

**Figure X.**

The range chart compares the simulated peak-day cooling makeup of each of the 24 active planned data center sites in the Delaware River Basin [trackdatacenters_2026] with the median effluent flow of the nearest eligible municipal plant within 10 miles [epa_echo]. For each site, the dot marks the 50th percentile (P50) of {m['n_draws']:,} Monte Carlo draws [peak_uncertainty.json]. The light bar spans P50 to the 90th percentile (P90), and the tick marks P90 [reuse_ready_model]. The open square marks the plant's median monthly flow converted to gallons per day [epa_echo]. Rows are sorted by P50 and labeled with the site number of the map key [site_key.csv]. Gray rows are the {p['n_no_eligible_plant']} sites with no eligible plant within 10 miles [supply_screen.csv]. The right-hand notes give each site's status. P90 exceeds the plant's median flow at {rb['n_notes_p90_exceeds']} sites, and the plant's median flow covers P90 at {rb['n_notes_plant_covers_p90']} site [peak_uncertainty.csv]. The other {rb['n_notes_no_plant']} sites have no plant within 10 miles [peak_uncertainty.csv]. The horizontal axis is logarithmic.

{common} The median flow covers P90 at {p['n_covers_p90']} of 24 sites, against {p['n_deterministic_matchable']} of 24 matchable sites in the deterministic screen [peak_uncertainty.csv, supply_screen.csv]. The sites that change are {ch} [peak_uncertainty.csv]. These values are model-derived.

The citation keys are trackdatacenters_2026, epa_echo, reuse_ready_model, shehabi_2024 and noaa_isd. Plotted values are in figures/peak_uncertainty_data.csv.
""")
    zr, br = rl["zero_share_range"], rl["below_axis_share_range"]
    rng_txt = lambda a: f"{100 * a[0]:.1f} percent" if round(100 * a[0], 1) == round(100 * a[1], 1) else \
        f"{100 * a[0]:.1f} to {100 * a[1]:.1f} percent"
    covered = ", ".join(pd.read_csv(RESULTS / "peak_uncertainty.csv").query("covers_p90").name)
    (FIGURES / "sites_mc_ridgeline_caption.md").write_text(f"""# Figure X (sites_mc_ridgeline)

**Figure X.**

The ridgeline chart shows one density curve for each of the 24 active planned data center sites in the Delaware River Basin [trackdatacenters_2026]. Each curve is a Gaussian kernel density (Scott's bandwidth) of the base-10 logarithm of simulated peak-day cooling makeup from {m['n_draws']:,} Monte Carlo draws [reuse_ready_model]. Each density is scaled to a common peak height, so the curves compare shape and position, not probability mass. The short colored tick marks each site's 90th percentile (P90) [sites_mc_ridgeline_data.csv]. The black bar marks the median monthly effluent flow of the nearest eligible municipal plant within 10 miles [epa_echo]. Rows are sorted by the median of the draws and labeled with the site number of the map key [site_key.csv]. The {p['n_no_eligible_plant']} gray rows have no eligible plant within 10 miles [supply_screen.csv]. Draws with zero makeup (the air-cooled architecture) make up {rng_txt(zr)} of each site's draws and are excluded from the densities [sites_mc_ridgeline_data.csv]. Of each site's draws, {rng_txt(br)} fall below the 100,000 gallon per day left edge of the axis [sites_mc_ridgeline_data.csv]. P90 exceeds the plant's median flow at {rl['n_p90_above_plant']} of the {24 - p['n_no_eligible_plant']} sites with a plant [peak_uncertainty.json]. Only {covered} is covered at P90 [peak_uncertainty.csv]. The horizontal axis is logarithmic.

{common} These values are model-derived.

The citation keys are trackdatacenters_2026, reuse_ready_model, epa_echo, shehabi_2024 and noaa_isd. Plotted values, including each density curve, are in figures/sites_mc_ridgeline_data.csv.
""")
    f = json.loads((RESULTS / "falls_mc_fan.json").read_text())
    dd = f["distributions"]
    am = f["annual_max_day_gpd"]
    (FIGURES / "falls_mc_fan_caption.md").write_text(f"""# Figure X (falls_mc_fan)

**Figure X.**

The line chart shows modeled daily cooling makeup at the Falls Township (AWS Keystone) campus by day of year for the calibrated hybrid cooling architecture [reuse_ready_model, falls_levittown_2026]. Each thin trace is one parameter draw run over one weather year chosen at random from 2005 to 2024 [falls_mc_fan.json]. Each run uses hourly Trenton (KTTN) wet-bulb temperature on local calendar days [noaa_isd, stull_2011]. The chart draws {f['n_plotted_traces']} of {f['n_draws']:,} draws (seed {f['seed']}), and the drawn traces were selected with seed {f['plot_selection_seed']} [falls_mc_fan.json]. The shaded band spans the 10th to the 90th percentile, and the solid line is the 50th percentile across all {f['n_draws']:,} draws for each day of year [reuse_ready_model].

Parameters are drawn independently. IT load is uniform on {_n(dd['p_it_mw']['low'])} to {_n(dd['p_it_mw']['high'], 1)} megawatts, from the unverified 253 megawatt figure [cleanview_keystone_2026] to the peak-day calibration's fitted load [reuse_ready_model]. Power usage effectiveness is uniform on 1.15 to 1.35 [shehabi_2024, p. 48]. The part-load exponent is uniform on {_n(dd['gamma']['low'], 3)} to {_n(dd['gamma']['high'], 3)}, the design-rate and peak-day calibration readings [reuse_ready_model]. The switchover wet-bulb temperature is fixed at {_n(dd['t_sw_c']['value'], 2)} degrees Celsius, the value shared by both readings [reuse_ready_model]. Cycles of concentration are fixed at 4 [falls_mc_fan.json].

Days with zero makeup cannot be shown on the logarithmic axis and are plotted at a floor of {_n(f['plot_floor_gpd'])} gallons per day [falls_mc_fan.json]. They are {100 * f['share_zero_makeup_trace_days_all_draws']:.1f} percent of all trace-days, so the 50th percentile sits at the floor on all but {f['n_doy_p50_positive']} days of the year [falls_mc_fan.json]. Dashed reference lines mark the DRBC review trigger of 100,000 gallons per day [drbc_admin_manual] and the reported peak of 4.4 million gallons per day [falls_levittown_2026, falls_herald_2026]. The gray panel marks June to August. Across draws, the largest day of the drawn year has a median of {_n(am['p50'])} gallons per day (10th to 90th percentile {_n(am['p10'])} to {_n(am['p90'])}) [falls_mc_fan.json]. The largest day exceeds the trigger in {100 * f['share_draws_max_day_over_trigger']:.0f} percent of draws [falls_mc_fan.json]. Day 366 exists only in leap years [noaa_isd]. These values are model-derived.

The citation keys are reuse_ready_model, falls_levittown_2026, falls_herald_2026, noaa_isd, stull_2011, cleanview_keystone_2026, shehabi_2024 and drbc_admin_manual. Plotted values are in figures/falls_mc_fan_data.csv.
""")


def run() -> dict:
    rb = render_range_bars()
    rl = render_ridgeline()
    fan = render_fan()
    write_captions(rb, rl, fan)
    # count also recorded in results/peak_uncertainty.json
    m = json.loads((RESULTS / "peak_uncertainty.json").read_text())
    m["ridgeline_p90_above_plant"] = {"n": rl["n_p90_above_plant"], "site_ids": rl["sites_p90_above_plant"]}
    (RESULTS / "peak_uncertainty.json").write_text(json.dumps(m, indent=2, default=float))
    chk = {"peak_uncertainty": rb, "sites_mc_ridgeline": rl, "falls_mc_fan": fan}
    (RESULTS / "peak_uncertainty_figure_check.json").write_text(json.dumps(chk, indent=1, default=str))
    for stem, v in chk.items():   # one check file per figure stem (QA gate H1)
        (RESULTS / f"{stem}_check.json").write_text(json.dumps(v, indent=1, default=str))
    return chk


if __name__ == "__main__":
    c = run()
    print(json.dumps({k: {kk: v[kk] for kk in ("text_overlaps", "min_font_pt", "size_mm")} for k, v in c.items()},
                     default=str))
