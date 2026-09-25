"""Falls Township hybrid: flow-duration style curve of daily makeup and drought coincidence (work order items 9, 10).

Series: calibrated hybrid (results/calibration.json key 'primary', P_IT = calibrated p_it_mw), KTTN hourly wet-bulb,
America/New_York local days 2005-01-01..2024-12-31 via blindspot.daily_series; days with < 20 valid hours are NaN
and are excluded from every statistic here.

figures/falls_duration_curve: daily makeup against percent of days exceeded, Weibull plotting position
p_i = 100 * i / (n + 1) with i the descending rank among the n valid days. Zero-makeup days carry plotting positions
but cannot sit on the log axis, so the curve is drawn only where makeup > 0 and the zero-day range is shaded.

figures/drought_coincidence: daily makeup (makeup > 0 only) against the same-day Trenton flow percentile. The
percentile is the day-of-year percentile rank of that day's flow among the same calendar day across 2005-2024
(Feb 29 pooled with Feb 28 and Mar 1, as in flow.doy_percentiles), mid-rank for ties
(scipy.stats.percentileofscore kind='mean'). With 20 values per calendar day, 'rank < 25' selects exactly the days
with flow below flow.py's p25_2005_2024.

Drought periods. The basinwide table (data/processed/drbc_drought_actions.csv, parsed from the DRBC page by flow.py)
has one row overlapping 2005-2024: 2016-11-23 to 2017-01-18, a drought watch with no warning stage ('--'). No
table interval of warning or emergency overlaps the window, so the table alone would highlight nothing. The same
cached page (data/raw/drbc/drbc-drought.html) describes three further actions in text, which are added as
SUPPLEMENTAL intervals and flagged as such in the data CSV:
  * Lower Basin drought warning, 2010-09-24 to 2010-10-31 (both dates stated in the page text).
  * Water supply emergency declared 2016 (Resolution 2016-07, 2016-11-23), basin placed in drought watch; the
    page gives no separate end date for the emergency, so it is closed at the table's end-of-watch date 2017-01-18.
  * Water supply emergency, December 2024 to June 2025; the page gives no day of declaration, so the interval
    opens on 2024-12-05 (the issue date of the DRBC news release listed on the page) and closes on 2025-06-11
    (approval of Resolution 2025-5 ending the emergency); it is clipped to 2024-12-31.
Table intervals: warning = enter_warning to end_watch_warning; emergency = declare_emergency to end_emergency. A
missing end date is closed at the next later action date in the row, else at the analysis end (2024-12-31); none of
the 2005-2024 rows needs this rule.
"""
from __future__ import annotations

import json
from itertools import combinations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

from . import blindspot as B  # noqa: E402
from . import styles as S  # noqa: E402
from .paths import FIGURES, PROCESSED, RESULTS  # noqa: E402

MM = 1 / 25.4
FIG_W_MM = 85.0
AVG_GPD = 135_000.0          # [falls_levittown_2026]
PEAK_GPD = 4_400_000.0       # [falls_levittown_2026; falls_herald_2026]
TRIGGER_GPD = B.TRIGGER_GPD  # [drbc_admin_manual]
TOP_SHARE = 0.05
FLOW_PCT_MARK = 25.0

SUPPLEMENTAL_INTERVALS = [
    # (start, end, kind, description, end_rule)
    ("2010-09-24", "2010-10-31", "warning", "Lower Basin drought warning (page text)", "stated"),
    ("2016-11-23", "2017-01-18", "emergency",
     "Water supply emergency declared 2016, Resolution 2016-07, basin in drought watch (page text)",
     "closed at table end_watch_warning 2017-01-18 (no emergency end date on page)"),
    ("2024-12-05", "2025-06-11", "emergency",
     "Water supply emergency December 2024 to June 2025 (page text)",
     "start = news release issue date 2024-12-05; end = Resolution 2025-5 approval 2025-06-11"),
]


# ------------------------------------------------------------------------------------------------ data
def falls_daily(name: str = "primary") -> tuple[pd.Series, dict]:
    """Daily makeup (gal/day) of the calibrated Falls hybrid at the calibrated P_IT; NaN days kept as NaN."""
    w, cal, _, _ = B.load_inputs(name)
    d = B.daily_series(w, B.config_params(cal["p_it_mw"], "hybrid", cal))
    d.name = "makeup_gpd"
    return d, cal


def weibull_exceedance(values: pd.Series) -> pd.DataFrame:
    """Valid values sorted descending with Weibull percent-exceeded 100 * i / (n + 1)."""
    v = values.dropna().sort_values(ascending=False, kind="mergesort")
    n = len(v)
    return pd.DataFrame({"date": v.index, "makeup_gpd": v.to_numpy(),
                         "rank_desc": np.arange(1, n + 1),
                         "pct_exceeded": 100.0 * np.arange(1, n + 1) / (n + 1)})


def doy_percentile_rank(flow: pd.DataFrame, start=B.START, end=B.END) -> pd.Series:
    """Percentile rank (0-100, mid-rank for ties) of each day's flow within the same calendar day, start..end."""
    f = flow[(flow.date >= start) & (flow.date <= end) & flow.flow_cfs.notna()].copy()
    md = f.date.dt.strftime("%m-%d")
    out = pd.Series(np.nan, index=pd.DatetimeIndex(f.date))
    for k in md.unique():
        pool = ["02-28", "02-29", "03-01"] if k == "02-29" else [k]
        ref = np.sort(f.loc[md.isin(pool), "flow_cfs"].to_numpy(dtype=float))
        sel = (md == k).to_numpy()
        x = f.loc[sel, "flow_cfs"].to_numpy(dtype=float)
        lo = np.searchsorted(ref, x, side="left")
        hi = np.searchsorted(ref, x, side="right")
        out.iloc[np.flatnonzero(sel)] = 100.0 * (lo + hi) / 2.0 / len(ref)
    return out.sort_index()


def doy_percentile_of_value(flow: pd.DataFrame, value: float, start=B.START, end=B.END) -> pd.Series:
    """Percentile equivalent of a fixed flow on each calendar day (same pooling and tie rule)."""
    f = flow[(flow.date >= start) & (flow.date <= end) & flow.flow_cfs.notna()]
    md = f.date.dt.strftime("%m-%d")
    res = {}
    for k in sorted(md.unique()):
        pool = ["02-28", "02-29", "03-01"] if k == "02-29" else [k]
        ref = np.sort(f.loc[md.isin(pool), "flow_cfs"].to_numpy(dtype=float))
        lo, hi = np.searchsorted(ref, value, "left"), np.searchsorted(ref, value, "right")
        res[k] = 100.0 * (lo + hi) / 2.0 / len(ref)
    return pd.Series(res, name="pct_equiv")


def _date(s):
    s = "" if pd.isna(s) else str(s).strip()
    try:
        return pd.Timestamp(s) if s and s != "--" else None
    except ValueError:
        return None


def table_intervals(dr: pd.DataFrame, end_close=B.END) -> pd.DataFrame:
    """Warning and emergency intervals from the DRBC basinwide table (see module docstring for the rules)."""
    order = ["enter_watch", "enter_warning", "end_watch_warning", "enter_drought", "declare_emergency", "end_emergency"]
    rows = []
    for i, r in dr.iterrows():
        dates = {c: _date(r.get(c)) for c in order}
        for kind, a, b in (("warning", "enter_warning", "end_watch_warning"),
                           ("emergency", "declare_emergency", "end_emergency")):
            st = dates[a]
            if st is None:
                continue
            en, rule = dates[b], "stated"
            if en is None or en < st:
                later = sorted(v for c, v in dates.items() if v is not None and v > st)
                en, rule = (later[0], "closed at next later action in row") if later else (
                    pd.Timestamp(end_close), "open; closed at analysis end")
            rows.append({"source": "table", "table_row": int(i), "kind": kind, "start": st, "end": en,
                         "description": f"{r['period']} table row {i}: {kind}", "end_rule": rule})
    return pd.DataFrame(rows, columns=["source", "table_row", "kind", "start", "end", "description", "end_rule"])


def drought_intervals(start=B.START, end=B.END) -> pd.DataFrame:
    dr = pd.read_csv(PROCESSED / "drbc_drought_actions.csv", dtype=str)
    t = table_intervals(dr)
    sup = pd.DataFrame([{"source": "supplemental_page_text", "table_row": np.nan, "kind": k,
                         "start": pd.Timestamp(a), "end": pd.Timestamp(b), "description": dsc, "end_rule": rule}
                        for a, b, k, dsc, rule in SUPPLEMENTAL_INTERVALS])
    iv = pd.concat([t, sup], ignore_index=True)
    iv = iv[(iv.end >= start) & (iv.start <= end)].copy()
    iv["start_clipped"] = iv.start.clip(lower=start)
    iv["end_clipped"] = iv.end.clip(upper=end)
    return iv.reset_index(drop=True)


def in_intervals(idx: pd.DatetimeIndex, iv: pd.DataFrame) -> np.ndarray:
    m = np.zeros(len(idx), dtype=bool)
    for r in iv.itertuples():
        m |= (idx >= r.start_clipped) & (idx <= r.end_clipped)
    return m


def duration_stats(d: pd.Series) -> dict:
    v = d.dropna()
    n = len(v)
    return {"n_days_total": int(len(d)), "n_nan_days": int(d.isna().sum()), "n_valid_days": n,
            "n_zero_days": int((v == 0).sum()), "share_zero_days": float((v == 0).mean()),
            "n_positive_days": int((v > 0).sum()),
            "max_pct_exceeded_positive": 100.0 * int((v > 0).sum()) / (n + 1),
            "mean_gpd": float(v.mean()), "max_gpd": float(v.max()), "max_date": v.idxmax().date().isoformat(),
            "peak_to_average_ratio": float(v.max() / v.mean()),
            "pct_days_above_trigger_100000": 100.0 * float((v > TRIGGER_GPD).mean()),
            "pct_days_above_avg_135000": 100.0 * float((v > AVG_GPD).mean()),
            "pct_days_above_peak_4400000": 100.0 * float((v > PEAK_GPD).mean()),
            "n_days_at_or_above_peak_4400000": int((v >= PEAK_GPD - 1e-6).sum()),
            "n_days_above_trigger_100000": int((v > TRIGGER_GPD).sum()),
            "n_days_above_avg_135000": int((v > AVG_GPD).sum())}


def coincidence_frame(d: pd.Series, flow: pd.DataFrame, iv: pd.DataFrame, q7q10: float) -> pd.DataFrame:
    rank = doy_percentile_rank(flow)
    fl = flow.set_index("date")
    v = d.dropna()
    df = pd.DataFrame({"date": v.index, "makeup_gpd": v.to_numpy()})
    df["flow_cfs"] = fl.flow_cfs.reindex(v.index).to_numpy(dtype=float)
    df["flow_doy_pct"] = rank.reindex(v.index).to_numpy()
    df["p25_2005_2024_cfs"] = fl.p25_2005_2024.reindex(v.index).to_numpy(dtype=float)
    df["below_q7q10"] = df.flow_cfs < q7q10
    df["in_drought_period"] = in_intervals(pd.DatetimeIndex(df.date), iv)
    thr = float(v.quantile(1 - TOP_SHARE))
    df["top5pct_demand"] = df.makeup_gpd >= thr
    df.attrs["top5_threshold_gpd"] = thr
    return df


def coincidence_stats(df: pd.DataFrame, q7q10: float, iv: pd.DataFrame, pct_equiv: pd.Series) -> dict:
    top = df[df.top5pct_demand & df.flow_doy_pct.notna()]
    pos = df[df.makeup_gpd > 0]
    return {"n_valid_days": int(len(df)), "top5_threshold_gpd": df.attrs["top5_threshold_gpd"],
            "n_top5_days": int(df.top5pct_demand.sum()), "n_top5_days_with_flow": int(len(top)),
            "share_top5_below_flow_p25": float((top.flow_doy_pct < FLOW_PCT_MARK).mean()),
            "n_top5_below_flow_p25": int((top.flow_doy_pct < FLOW_PCT_MARK).sum()),
            "share_top5_below_flow_p25_check_vs_p25_cfs": float((top.flow_cfs < top.p25_2005_2024_cfs).mean()),
            "share_top5_below_q7q10": float((top.flow_cfs < q7q10).mean()),
            "n_top5_in_drought_period": int(top.in_drought_period.sum()),
            "n_top5_in_table_warning_or_emergency": int(in_intervals(
                pd.DatetimeIndex(top.date), iv[iv.source == "table"]).sum()),
            "n_positive_days_plotted": int(len(pos)), "n_positive_days_in_drought": int(pos.in_drought_period.sum()),
            "n_valid_days_in_drought": int(df.in_drought_period.sum()),
            "share_positive_days_below_flow_p25": float((pos.flow_doy_pct < FLOW_PCT_MARK).mean()),
            "q7q10_cfs": q7q10, "min_flow_2005_2024_cfs": float(df.flow_cfs.min()),
            "n_days_below_q7q10_2005_2024": int((df.flow_cfs < q7q10).sum()),
            "q7q10_pct_equiv_min": float(pct_equiv.min()), "q7q10_pct_equiv_max": float(pct_equiv.max()),
            "n_intervals_table": int((iv.source == "table").sum()),
            "n_intervals_supplemental": int((iv.source != "table").sum())}


# ------------------------------------------------------------------------------------------------ plotting
def _mgd_fmt(y, _pos=None):
    """Tick label in million gal/d for a value in gal/d (0.01, 0.1, 1, 10)."""
    return f"{y / 1e6:g}"


def text_boxes_check(fig) -> dict:
    """QA gate H1 in display coordinates: every pair of visible text boxes that overlap, any text outside the
    figure, text boxes crossed by a plotted line (Line2D in any axes, sampled densely along the path) and text
    boxes that touch a scatter symbol (disc of the marker radius). Tick marks and spines are not data lines."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    ts = [t for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text().strip()]
    boxes = [(t.get_text(), t.get_window_extent(r)) for t in ts]
    fb = fig.bbox
    pairs = [(a, b) for (a, ba), (b, bb) in combinations(boxes, 2) if ba.overlaps(bb)]
    edge = [a for a, ba in boxes if ba.x0 < fb.x0 or ba.x1 > fb.x1 or ba.y0 < fb.y0 or ba.y1 > fb.y1]
    text_line, text_symbol = [], []
    for ax in fig.axes:
        axb = ax.get_window_extent(r)
        for ln in ax.lines:
            xy = ln.get_transform().transform(ln.get_xydata())
            xy = xy[np.isfinite(xy).all(axis=1)]
            if len(xy) < 2:
                continue
            seg = np.diff(xy, axis=0)
            n = np.maximum(2, np.ceil(np.hypot(seg[:, 0], seg[:, 1]) / 0.5).astype(int))
            pts = np.vstack([xy[i] + np.linspace(0, 1, k)[:, None] * seg[i] for i, k in enumerate(n)])
            if ln.get_clip_on():
                pts = pts[(pts[:, 0] >= axb.x0) & (pts[:, 0] <= axb.x1) & (pts[:, 1] >= axb.y0) & (pts[:, 1] <= axb.y1)]
            for a, ba in boxes:
                if ((pts[:, 0] > ba.x0) & (pts[:, 0] < ba.x1) & (pts[:, 1] > ba.y0) & (pts[:, 1] < ba.y1)).any():
                    text_line.append((a, ln.get_label()))
        for pc in ax.collections:
            off = pc.get_offset_transform().transform(pc.get_offsets())
            if not len(off):
                continue
            rad = np.sqrt(np.broadcast_to(pc.get_sizes(), (len(off),))) / 2 * fig.dpi / 72.0
            for a, ba in boxes:
                dx = np.maximum(np.maximum(ba.x0 - off[:, 0], 0), off[:, 0] - ba.x1)
                dy = np.maximum(np.maximum(ba.y0 - off[:, 1], 0), off[:, 1] - ba.y1)
                hit = np.hypot(dx, dy) < rad
                if hit.any():
                    text_symbol.append((a, int(hit.sum())))
    return {"text_text": pairs, "text_outside_figure": edge, "text_line": text_line, "text_symbol": text_symbol,
            "n_text": len(boxes)}


def _write_check(stem: str, chk: dict):
    ok = not any(chk[k] for k in ("text_text", "text_outside_figure", "text_line", "text_symbol"))
    (RESULTS / f"{stem}_check.json").write_text(json.dumps({"figure": f"figures/{stem}", "pass": ok, **chk},
                                                           indent=1, default=str))


def _save(fig, stem: str):
    for e in ("png", "pdf", "svg"):
        fig.savefig(FIGURES / f"{stem}.{e}", dpi=S.V2_DPI)


def _style_axes(ax):
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(which="both", direction="out", pad=1.5)


def render_duration_curve(d: pd.Series, st: dict) -> dict:
    S.v2_rc()
    ex = weibull_exceedance(d)
    pos = ex[ex.makeup_gpd > 0]
    h_mm = 62.0
    l_mm, r_mm, b_mm, t_mm = 11.0, 3.2, 10.0, 3.0
    fig = plt.figure(figsize=(FIG_W_MM * MM, h_mm * MM), dpi=S.V2_DPI)
    ax = fig.add_axes([l_mm / FIG_W_MM, b_mm / h_mm, (FIG_W_MM - l_mm - r_mm) / FIG_W_MM, (h_mm - b_mm - t_mm) / h_mm])
    ax.set_yscale("log")
    ymin, ymax = 1e4, 1e7
    ax.set_xlim(0, 100)
    ax.set_ylim(ymin, ymax)
    x_zero = st["max_pct_exceeded_positive"]
    ax.axvspan(x_zero, 100, color=S.V2_OUTSIDE, lw=0, zorder=0)
    ax.text((x_zero + 100) / 2, 1.9e4, "Makeup zero", ha="center", va="center", fontsize=S.V2_FONT_SIZE,
            color=S.V2_GRAY_DARK)
    ax.plot(pos.pct_exceeded, pos.makeup_gpd, color=S.V2_ACCENT, lw=S.V2_LW_PRIMARY, zorder=5,
            solid_joinstyle="round")
    refs = [(PEAK_GPD, "Reported peak day, 4.4 million gal/d", "bottom", S.V2_GRAY_DARK, S.V2_DASH),
            (AVG_GPD, "Reported average, 135,000 gal/d", "bottom", S.V2_GRAY_DARK, S.V2_DASH),
            (TRIGGER_GPD, "DRBC threshold, 100,000 gal/d", "top", S.V2_BLACK, "solid")]
    for y, lab, va, col, ls in refs:
        ax.axhline(y, color=col, lw=S.V2_LW_SECONDARY, linestyle=ls, zorder=3)
        yy = y * (1.06 if va == "bottom" else 1 / 1.06)
        ax.text(99.3, yy, lab, ha="right", va=va, fontsize=S.V2_FONT_SIZE, color=S.V2_BLACK, zorder=6)
    ax.yaxis.set_major_locator(FixedLocator([1e4, 1e5, 1e6, 1e7]))
    ax.yaxis.set_major_formatter(FuncFormatter(_mgd_fmt))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("Percent of days exceeded", labelpad=2)
    ax.set_ylabel("Modeled makeup (million gal/d)", labelpad=2)
    _style_axes(ax)
    chk = text_boxes_check(fig)
    stem = "falls_duration_curve"
    _write_check(stem, chk)
    _save(fig, stem)
    plt.close(fig)
    out = ex.copy()
    out["date"] = pd.to_datetime(out.date).dt.date
    out["plotted"] = out.makeup_gpd > 0
    out["share_zero_days_all_valid"] = st["share_zero_days"]
    ref = pd.DataFrame([{"date": "", "makeup_gpd": y, "rank_desc": np.nan, "pct_exceeded": np.nan,
                         "plotted": True, "share_zero_days_all_valid": st["share_zero_days"],
                         "element": "reference_line", "label": lab} for y, lab, *_ in refs])
    out["element"] = "daily_makeup"
    out["label"] = ""
    pd.concat([out, ref], ignore_index=True).to_csv(FIGURES / f"{stem}_data.csv", index=False)
    return {"check": chk, "h_mm": h_mm, "zero_band_from_pct": x_zero}


def render_drought_coincidence(df: pd.DataFrame, cs: dict, pct_equiv: pd.Series) -> dict:
    S.v2_rc()
    pos = df[(df.makeup_gpd > 0) & df.flow_doy_pct.notna()]
    h_mm = 71.0
    l_mm, r_mm, b_mm, t_mm = 11.0, 3.2, 10.0, 11.5
    fig = plt.figure(figsize=(FIG_W_MM * MM, h_mm * MM), dpi=S.V2_DPI)
    ax = fig.add_axes([l_mm / FIG_W_MM, b_mm / h_mm, (FIG_W_MM - l_mm - r_mm) / FIG_W_MM, (h_mm - b_mm - t_mm) / h_mm])
    ax.set_yscale("log")
    ax.set_xlim(0, 100)
    ax.set_ylim(1e4, 1e7)
    oth, dro = pos[~pos.in_drought_period], pos[pos.in_drought_period]
    ax.scatter(oth.flow_doy_pct, oth.makeup_gpd, s=3.0, c=S.V2_GRAY, lw=0, zorder=3, alpha=0.8)
    ax.scatter(dro.flow_doy_pct, dro.makeup_gpd, s=7.0, c=S.V2_ACCENT, lw=0, zorder=4)
    ax.axvline(FLOW_PCT_MARK, color=S.V2_BLACK, lw=S.V2_LW_SECONDARY, linestyle=S.V2_DASH, zorder=2)
    ax.text(FLOW_PCT_MARK + 1.0, 8.0e6, "25th percentile", ha="left", va="center", fontsize=S.V2_FONT_SIZE)
    thr = cs["top5_threshold_gpd"]
    ax.axhline(thr, color=S.V2_GRAY_DARK, lw=S.V2_LW_SECONDARY, linestyle=S.V2_DASH, zorder=2)
    ax.axhline(TRIGGER_GPD, color=S.V2_BLACK, lw=S.V2_LW_SECONDARY, zorder=2)
    # 7Q10: its percentile equivalent is 0 on every calendar day (every 2005-2024 daily flow exceeds it)
    x7 = float(pct_equiv.max())
    ax.annotate("7Q10", xy=(x7, 1.25e4), xytext=(x7 + 4.0, 1.25e4), textcoords="data", ha="left", va="center",
                fontsize=S.V2_FONT_SIZE,
                arrowprops=dict(arrowstyle="-|>,head_width=0.15,head_length=0.3", lw=S.V2_LW_SECONDARY,
                                color=S.V2_BLACK, shrinkA=1, shrinkB=0))
    ax.yaxis.set_major_locator(FixedLocator([1e4, 1e5, 1e6, 1e7]))
    ax.yaxis.set_major_formatter(FuncFormatter(_mgd_fmt))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Same-day Trenton flow, day-of-year percentile", labelpad=2)
    ax.set_ylabel("Modeled makeup (million gal/d)", labelpad=2)
    _style_axes(ax)
    # key in the top margin (two right-aligned rows) so that no line label covers a data point
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    px_mm = fig.dpi / 25.4
    rows = [[("pt", "DRBC drought warning or emergency", S.V2_ACCENT, 7.0), ("pt", "Other days", S.V2_GRAY, 3.0)],
            [("ln", "Top 5 percent of days", S.V2_GRAY_DARK, S.V2_DASH),
             ("ln", "DRBC threshold, 100,000 gal/d", S.V2_BLACK, "solid")]]
    kx = fig.add_axes([0, 0, 1, 1], zorder=-1)
    kx.set_axis_off()
    kx.set_xlim(0, FIG_W_MM)
    kx.set_ylim(0, h_mm)
    SW = {"pt": 3.5, "ln": 5.5}
    for k, row in enumerate(rows):
        y_mm = h_mm - 2.4 - k * 3.6
        xs = FIG_W_MM - r_mm
        for kind, lab, col, sty in reversed(row):
            t = fig.text(0, 0, lab, fontsize=S.V2_FONT_SIZE)
            w = t.get_window_extent(rend).width / px_mm
            t.remove()
            xt = xs - w
            fig.text(xt / FIG_W_MM, y_mm / h_mm, lab, fontsize=S.V2_FONT_SIZE, va="center", ha="left")
            if kind == "pt":
                kx.scatter([xt - 2.0], [y_mm], s=sty * 1.6, c=col, lw=0)
            else:
                kx.plot([xt - 1.2 - SW["ln"], xt - 1.2], [y_mm, y_mm], color=col, lw=S.V2_LW_SECONDARY, linestyle=sty)
            xs = xt - SW[kind] - 1.2 - 3.0
    chk = text_boxes_check(fig)
    stem = "drought_coincidence"
    _write_check(stem, chk)
    _save(fig, stem)
    plt.close(fig)
    out = df.copy()
    out["date"] = pd.to_datetime(out.date).dt.date
    out["plotted"] = (out.makeup_gpd > 0) & out.flow_doy_pct.notna()
    out.to_csv(FIGURES / f"{stem}_data.csv", index=False)
    return {"check": chk, "h_mm": h_mm, "x_7q10_pct_equiv": x7}


# ------------------------------------------------------------------------------------------------ captions
def _p(x, nd=1):
    return f"{100 * x:.{nd}f}"


def caption_duration(st: dict, cal: dict) -> str:
    return (
        "# Figure 3 (falls_duration_curve)\n\n"
        "**Figure 3.**\n\n"
        "The duration curve shows modeled daily cooling makeup for the calibrated hybrid system at the Falls "
        "Township (AWS Keystone) campus under KTTN weather for 2005 to 2024 [reuse_ready_model, noaa_isd, "
        f"stull_2011]. The model uses the primary peak-day calibration (switchover wet-bulb {cal['t_sw_c']:.2f} °C, "
        f"part-load exponent {cal['gamma']:.3f}, {cal['p_it_mw']:.1f} MW of IT load, PUE {cal['pue']:.1f}, "
        f"{cal['cycles']:.0f} cycles of concentration) [reuse_ready_model]. Each local calendar day is plotted at "
        f"its Weibull plotting position, 100 i / (n + 1), among the {st['n_valid_days']:,} valid days, and the "
        f"{st['n_nan_days']} days with fewer than 20 valid weather hours are excluded [reuse_ready_model]. On some "
        "days the hybrid cools without water, and these zero-makeup days cannot be drawn on the logarithmic axis. "
        f"Makeup is zero on {st['n_zero_days']:,} days ({_p(st['share_zero_days'])} percent of valid days), so the "
        f"curve stops at {st['max_pct_exceeded_positive']:.1f} percent of days exceeded and the zero-makeup range "
        "is shaded [reuse_ready_model]. Reference lines mark the reported average of 135,000 gal/d "
        "[falls_levittown_2026], the reported peak of 4.4 million gal/d [falls_levittown_2026, falls_herald_2026] "
        "and the 100,000 gal/d DRBC review threshold, which applies to the daily average over any 30 consecutive "
        f"days [drbc_admin_manual]. The modeled maximum day ({st['max_gpd']:,.0f} gal/d on {st['max_date']}) is "
        f"{st['peak_to_average_ratio']:.1f} times the modeled mean ({st['mean_gpd']:,.0f} gal/d) "
        f"[reuse_ready_model]. Modeled makeup exceeds 100,000 gal on {st['pct_days_above_trigger_100000']:.1f} "
        f"percent of valid days ({st['n_days_above_trigger_100000']} days) and 135,000 gal on "
        f"{st['pct_days_above_avg_135000']:.1f} percent ({st['n_days_above_avg_135000']} days) "
        "[reuse_ready_model]. No day exceeds 4.4 million gal, which the calibration reproduces on "
        f"{st['n_days_at_or_above_peak_4400000']} day [falls_figures_summary.json].\n\n"
        "The citation keys are reuse_ready_model, noaa_isd, stull_2011, falls_levittown_2026, falls_herald_2026 "
        "and drbc_admin_manual.\n")


def caption_coincidence(cs: dict, iv: pd.DataFrame) -> str:
    n_dr = cs['n_top5_in_drought_period']
    return (
        "# Figure 4 (drought_coincidence)\n\n"
        "**Figure 4.**\n\n"
        "The scatter plot compares modeled daily cooling makeup for the calibrated Falls Township hybrid with the "
        "same-day flow of the Delaware River at Trenton. Flow is expressed as the day-of-year percentile of that "
        "day's flow among the same calendar day in 2005 to 2024 [reuse_ready_model, usgs_nwis_01463500]. Only the "
        f"{cs['n_positive_days_plotted']:,} days with makeup above zero are drawn on the logarithmic axis "
        "[reuse_ready_model]. Percentile ranks use the mid-rank for ties, and February 29 is pooled with February 28 "
        "and March 1 [usgs_nwis_01463500]. Accent points fall inside DRBC drought warning or emergency periods "
        "[drbc_drought_page]. The basinwide table lists no warning or emergency stage between 2005 and 2024, and its "
        "only row in that window is the drought watch of 23 November 2016 to 18 January 2017 [drbc_drought_page]. "
        "The highlighted periods are therefore taken from the text of the same page. The first is the Lower Basin "
        "drought warning of 24 September to 31 October 2010 [drbc_drought_page]. The second is the water supply "
        "emergency of 2016, dated from Resolution 2016-07 of 23 November 2016 [drought_intervals_2005_2024.csv]. "
        "The page gives no separate end date for it, so it is closed at the end of the drought watch on 18 January "
        "2017 [drought_intervals_2005_2024.csv]. The third is the water supply emergency of December 2024 to June "
        "2025 [drought_intervals_2005_2024.csv]. It is opened on 5 December 2024, the date of the DRBC news "
        "release, and clipped at 31 December 2024 [drought_intervals_2005_2024.csv]. Only the 2010 period falls in the season with makeup "
        f"above zero, and it contains {cs['n_positive_days_in_drought']} such days [reuse_ready_model]. With 20 "
        "years in the window, each calendar day has 20 flows, so percentile ranks fall on 20 discrete values "
        "[usgs_nwis_01463500]. The points therefore form columns. The dashed vertical line marks the 25th flow "
        "percentile, and the dashed horizontal line marks the top 5 percent of valid days by makeup "
        f"({cs['top5_threshold_gpd']:,.0f} gal/d or more, {cs['n_top5_days']} days) [reuse_ready_model]. The "
        "solid horizontal line marks the 100,000 gal/d DRBC review threshold, which applies to the daily average "
        f"over any 30 consecutive days [drbc_admin_manual]. The full-record 7Q10 of {cs['q7q10_cfs']:,.0f} cfs lies "
        f"below every daily flow from 2005 to 2024 (minimum {cs['min_flow_2005_2024_cfs']:,.0f} cfs) "
        "[usgs_nwis_01463500]. Its percentile equivalent is therefore 0 on every calendar day, and an arrow marks it "
        "at the left axis [usgs_nwis_01463500]. Of the top 5 percent demand days, "
        f"{_p(cs['share_top5_below_flow_p25'])} percent ({cs['n_top5_below_flow_p25']} days) fall below the 25th "
        f"flow percentile and {_p(cs['share_top5_below_q7q10'], 0)} percent fall below the 7Q10 "
        f"[reuse_ready_model, usgs_nwis_01463500]. Of the same days, {n_dr} "
        f"{'day falls' if n_dr == 1 else 'days fall'} inside a drought warning or emergency period "
        "[drbc_drought_page] [falls_figures_summary.json].\n\n"
        "The citation keys are reuse_ready_model, usgs_nwis_01463500, drbc_drought_page and drbc_admin_manual.\n")


# ------------------------------------------------------------------------------------------------ driver
def run() -> dict:
    d, cal = falls_daily("primary")
    st = duration_stats(d)
    _, _, q7q10, _ = B.load_inputs("primary")
    flow = pd.read_parquet(PROCESSED / "flow_daily.parquet")[["date", "flow_cfs", "p25_2005_2024"]]
    iv = drought_intervals()
    df = coincidence_frame(d, flow, iv, q7q10)
    pct_equiv = doy_percentile_of_value(flow, q7q10)
    cs = coincidence_stats(df, q7q10, iv, pct_equiv)
    i1 = render_duration_curve(d, st)
    i2 = render_drought_coincidence(df, cs, pct_equiv)
    (FIGURES / "falls_duration_curve_caption.md").write_text(caption_duration(st, cal))
    (FIGURES / "drought_coincidence_caption.md").write_text(caption_coincidence(cs, iv))
    ivo = iv.copy()
    for c in ("start", "end", "start_clipped", "end_clipped"):
        ivo[c] = ivo[c].dt.date.astype(str)
    ivo.to_csv(RESULTS / "drought_intervals_2005_2024.csv", index=False)
    summary = {"calibration": "primary", "p_it_mw": cal["p_it_mw"], "duration": st, "coincidence": cs,
               "figure_checks": {"falls_duration_curve": i1["check"], "drought_coincidence": i2["check"]},
               "drought_intervals_file": "results/drought_intervals_2005_2024.csv"}
    (RESULTS / "falls_figures_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    s = run()
    print(json.dumps({k: s[k] for k in ("duration", "coincidence", "figure_checks")}, indent=1, default=str))
