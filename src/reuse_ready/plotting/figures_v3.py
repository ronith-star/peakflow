"""V3 supply-screen map (figures/supply_screen_map_v3.*); v2 is kept unchanged alongside it.

Relative to v2, only these change: the font (Helvetica, then Arial, then Liberation Sans; Arial Narrow or
Liberation Sans Narrow for site numbers and city labels), the legend wording and layout, a tighter crop, plants
outside the basin at 40 percent opacity, scale-bar unit labels moved below the bars, and a label placer that
treats label padding, site squares, plant circles, the basin boundary and state lines as obstacles. Colours,
fills, relief, line weights and symbol styles are taken unchanged from styles.V2_* and figures_v2.

Outputs: figures/supply_screen_map_v3.{png,pdf,svg}, _caption.md, _data.csv; results/figures_v3_check.json; the
same for supply_screen_map_v3_brief (120 mm); results/supply_screen_map_v3{,_brief}_check.json (STANDARDS H1 gate:
text pairs, figure edge, label against symbol and line, site-number ambiguity, leader crossings, minimum font).
"""
from __future__ import annotations

import json
import tempfile
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.text as mtext
import numpy as np
import pandas as pd
from matplotlib.patches import Circle, Rectangle
from shapely.geometry import MultiLineString

from .. import styles as S
from ..paths import FIGURES, RESULTS
from . import figures_v2 as V2

MM = V2.MM
PT_PER_MM = V2.PT_PER_MM
MAP_W_MM = 180.0
OUTSIDE_ALPHA = 0.40
LABEL_PAD_PT = 1.0            # clearance around every label box
NUM_SIZE = S.V2_FONT_SIZE     # site numbers, narrow face
CITY_SIZE = S.V2_FONT_SIZE    # city labels, narrow face, gray
CITY_HALO = False             # brief map only: haloed city labels may cross thin plant outlines
CITY_RADII = [2.2, 3.2, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 14.0]
CITY_LEADER_FROM = 99.0       # city labels never get leaders on the full-size map
TXT_K = 1.0                   # multiplier on text-bound layout spacing (key rows, scale-bar rows); 1 at 180 mm
SCALE_ROWS = ((50, 10, "KILOMETERS", 1000.0), (30, 10, "MILES", 1609.344))
LEADER_LW = None              # None: styles.V2_LW_TERTIARY; the brief map uses V2_LW_SECONDARY x 120/180 so
                              # leaders stay visible at 120 mm (scaled tertiary, 0.17 pt, vanishes at 1:1)


# ------------------------------------------------------------------------------------------------ drawing
def draw_features_v3(ax, D):
    s, p = D["sites"], D["plants"]
    for g in s.geometry:
        ax.add_patch(Circle((g.x, g.y), 16093.44, fill=False, ec=S.V2_GRAY, lw=S.V2_LW_TERTIARY,
                            linestyle=S.V2_DASH, zorder=8))
    basin = D["drb"].geometry.union_all()
    inside = p.geometry.within(basin).to_numpy()
    for msk, alpha in ((~inside, OUTSIDE_ALPHA), (inside, 1.0)):
        q = p[msk]
        ax.scatter(q.geometry.x, q.geometry.y, s=V2.plant_area(q.median_flow_mgd), facecolors="none",
                   edgecolors=S.V2_BLACK, linewidths=S.V2_LW_TERTIARY * 2, alpha=alpha, zorder=9)
    for unv, ls in ((False, "solid"), (True, S.V2_DASH)):
        q = s[s.unverified.astype(bool) == unv]
        if len(q):
            ax.scatter(q.geometry.x, q.geometry.y, s=V2.SITE_S, marker="s",
                       c=[S.V2_FILL[b] for b in q.covered_it_bin], edgecolors=S.V2_BLACK,
                       linewidths=S.V2_LW_PRIMARY, linestyles=[ls], zorder=10)
    return inside


def scale_bar_v3(fig, rect_fig, m_per_mm, rows=None, bar_mm=None, north=True):
    """Two stacked scale bars; numbers above each bar, the unit label centred below it; north arrow at left."""
    rows = SCALE_ROWS if rows is None else rows
    k = TXT_K
    bar_mm = 1.0 * k if bar_mm is None else bar_mm
    sa = fig.add_axes(rect_fig)
    W = rect_fig[2] * fig.get_size_inches()[0] * 25.4
    H = rect_fig[3] * fig.get_size_inches()[1] * 25.4
    sa.set_xlim(0, W); sa.set_ylim(0, H); sa.set_axis_off(); sa.patch.set_alpha(0)
    x0 = (8.0 if north else 1.5) * k
    arts = []
    row_h = 7.4 * k
    for j, (tot, step, unit, conv) in enumerate(rows):
        yb = H - 3.6 * k - j * row_h - bar_mm          # bar bottom
        n = int(round(tot / step)); seg = step * conv / m_per_mm
        for i in range(n):
            sa.add_patch(Rectangle((x0 + i * seg, yb), seg, bar_mm, fc=S.V2_BLACK if i % 2 == 0 else "white",
                                   ec=S.V2_BLACK, lw=S.V2_LW_TERTIARY * 2, clip_on=False))
        for i in range(n + 1):
            arts.append(sa.text(x0 + i * seg, yb + bar_mm + 0.5 * k, f"{i * step:g}", ha="center", va="bottom",
                                fontsize=S.V2_FONT_SIZE))
        arts.append(sa.text(x0 + n * seg / 2, yb - 0.6 * k, unit, ha="center", va="top", fontsize=S.V2_FONT_SIZE))
    if north:
        sa.annotate("", xy=(3.0 * k, H - 4.2 * k), xytext=(3.0 * k, H - 13.2 * k),
                    arrowprops=dict(arrowstyle="-|>,head_width=0.22,head_length=0.5", lw=S.V2_LW_SECONDARY,
                                    color=S.V2_BLACK, shrinkA=0, shrinkB=0))
        arts.append(sa.text(3.0 * k, H - 3.8 * k, "N", ha="center", va="bottom", fontsize=S.V2_FONT_SIZE))
    return sa, arts


def legend_v3(fig, ax, anchor_mm, aw, ah, l_mm, b_mm, m_per_mm):
    """Key in the lower-right corner. Swatches in one column, all text left-aligned, uniform row spacing."""
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    px_mm = fig.dpi / 25.4
    def tw(s, **kw):
        t = fig.text(0, 0, s, fontsize=S.V2_FONT_SIZE, **kw); w = t.get_window_extent(r).width / px_mm; t.remove()
        return w
    k = TXT_K
    PAD, SW_X, TX, ROW, GAP = 2.4 * k, 5.0 * k, 9.6 * k, 3.9 * k, 1.6 * k
    items = [("head", "Key"), ("group", "Planned site, IT load coverable at peak (MW)")]
    items += [("site", "> 200", S.V2_FILL["over 200 MW"], "solid"), ("site", "50 to 200", S.V2_FILL["50 to 200 MW"], "solid"),
              ("site", "No eligible plant within 10 mi", S.V2_FILL["no eligible plant within 10 mi"], "solid"), ("site", "Unverified", "#FFFFFF", "dashed")]
    items += [("gap",), ("group", "Treatment plant, median flow (MGD)")]
    items += [("plant", "5", 5), ("plant", "25", 25), ("plant", "100", 100)]
    items += [("gap",), ("radius", "10-mile radius"), ("line", "Basin boundary", S.V2_BLACK, S.V2_LW_PRIMARY, "solid"),
              ("line", "State boundary", S.V2_GRAY_DARK, S.V2_LW_SECONDARY, "dashed")]
    widths = [tw(it[1], weight="bold" if it[0] == "head" else "normal") + (PAD if it[0] in ("head", "group") else TX)
              for it in items if len(it) > 1]
    SB_H = 17.0 * k
    w_mm = max(max(widths) + PAD, 44.0 * k)
    # vertical layout (y downward from the top of the box)
    ys, y = [], PAD + 1.4 * k
    for it in items:
        kind = it[0]
        if kind == "gap":
            y += GAP; ys.append(None); continue
        if kind == "plant":
            d = np.sqrt(V2.plant_area(it[2])) / PT_PER_MM
            h = max(ROW, d + 1.1 * k)
            ys.append(y + h / 2 - ROW / 2 + (0 if ys and items[len(ys) - 1][0] == "plant" else 0)); y += h
            continue
        ys.append(y); y += ROW if kind != "group" else ROW
    h_mm = y + 1.0 * k + SB_H + PAD
    x_mm = aw - w_mm - anchor_mm; y_top = ah - h_mm - anchor_mm
    lg = ax.inset_axes([x_mm / aw, 1 - (y_top + h_mm) / ah, w_mm / aw, h_mm / ah])
    lg.set_xlim(0, w_mm); lg.set_ylim(h_mm, 0); lg.set_xticks([]); lg.set_yticks([])
    lg.set_facecolor("white"); lg.set_zorder(40)
    for sp in lg.spines.values():
        sp.set_linewidth(S.V2_LW_SECONDARY)
    rows_out = []
    for it, yy in zip(items, ys):
        if yy is None:
            continue
        kind = it[0]
        if kind in ("head", "group"):
            lg.text(PAD, yy, it[1], fontsize=S.V2_FONT_SIZE, va="center", ha="left",
                    weight="bold" if kind == "head" else "normal")
        elif kind == "site":
            lg.scatter([SW_X], [yy], s=V2.SITE_S, marker="s", c=it[2], edgecolors=S.V2_BLACK,
                       linewidths=S.V2_LW_PRIMARY, linestyles=[S.V2_DASH if it[3] == "dashed" else "solid"],
                       clip_on=False)
            lg.text(TX, yy, it[1], fontsize=S.V2_FONT_SIZE, va="center", ha="left")
        elif kind == "plant":
            lg.scatter([SW_X], [yy], s=V2.plant_area(it[2]), facecolors="none", edgecolors=S.V2_BLACK,
                       linewidths=S.V2_LW_TERTIARY * 2, clip_on=False)
            lg.text(TX, yy, it[1], fontsize=S.V2_FONT_SIZE, va="center", ha="left")
        elif kind == "radius":
            lg.add_patch(Circle((SW_X, yy), 1.55 * k, fill=False, ec=S.V2_GRAY, lw=S.V2_LW_SECONDARY, linestyle=S.V2_DASH))
            lg.text(TX, yy, it[1], fontsize=S.V2_FONT_SIZE, va="center", ha="left")
        elif kind == "line":
            lg.plot([SW_X - 2.6 * k, SW_X + 2.6 * k], [yy, yy], color=it[2], lw=it[3],
                    linestyle=S.V2_DASH if it[4] == "dashed" else "solid")
            lg.text(TX, yy, it[1], fontsize=S.V2_FONT_SIZE, va="center", ha="left")
        rows_out.append({"kind": kind, "text": it[1], "y_mm": yy})
    fx = lambda xm: (l_mm + xm) / MAP_W_MM
    fig_h = fig.get_size_inches()[1] * 25.4
    sb_top_from_axes_top = y_top + h_mm - PAD - SB_H
    rect = [fx(x_mm + PAD - 1.0 * k), (b_mm + ah - sb_top_from_axes_top - SB_H) / fig_h, (w_mm - 2 * PAD) / MAP_W_MM,
            SB_H / fig_h]
    sa, sb = scale_bar_v3(fig, rect, m_per_mm)
    sa.set_zorder(41)
    return lg, sa, sb, {"w_mm": w_mm, "h_mm": h_mm, "rows": rows_out}


# ------------------------------------------------------------------------------------------------ labels
def _line_pts(ax, geoms, step_m=150.0):
    pts = []
    for g in geoms:
        if g is None or g.is_empty:
            continue
        lines = [g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))
        for ln in lines:
            if ln.geom_type != "LineString":
                continue
            ln = ln.segmentize(step_m)
            pts.append(np.asarray(ln.coords)[:, :2])
    if not pts:
        return np.zeros((0, 2))
    return ax.transData.transform(np.vstack(pts))


def obstacles(ax, D, inside_mask):
    T = ax.transData
    k = ax.figure.dpi / 72
    sq = np.array([T.transform((g.x, g.y)) for g in D["sites"].geometry])
    sq_half = (V2.SITE_MS_PT / 2 + S.V2_LW_PRIMARY / 2) * k
    pl = np.array([T.transform((g.x, g.y)) for g in D["plants"].geometry])
    pl_rad = np.sqrt(V2.plant_area(D["plants"].median_flow_mgd.to_numpy())) / 2 * k
    boundary = [g.boundary for g in D["drb"].geometry]
    borders = list(V2.shared_state_borders(D["states"]).geometry)
    lines = _line_pts(ax, boundary + borders)
    rivers = _line_pts(ax, list(D["rivers"].geometry), step_m=300.0)
    return {"sq": sq, "sq_half": sq_half, "pl": pl, "pl_rad": pl_rad, "pl_inside": inside_mask,
            "lines": lines, "rivers": rivers}


def _hits(bb, O, own=None):
    """Counts of obstacles intersecting display bbox `bb`; `own` is the anchor point to exclude."""
    x0, y0, x1, y1 = bb.x0, bb.y0, bb.x1, bb.y1
    sq = O["sq"]; h = O["sq_half"]
    m = (sq[:, 0] + h > x0) & (sq[:, 0] - h < x1) & (sq[:, 1] + h > y0) & (sq[:, 1] - h < y1)
    n_sq = int(m.sum())
    pl, rad = O["pl"], O["pl_rad"]
    cx = np.clip(pl[:, 0], x0, x1); cy = np.clip(pl[:, 1], y0, y1)
    mp = np.hypot(pl[:, 0] - cx, pl[:, 1] - cy) < rad
    if own is not None:
        mp &= np.hypot(pl[:, 0] - own[0], pl[:, 1] - own[1]) > 0.5
    n_pl_in = int((mp & O["pl_inside"]).sum()); n_pl_out = int((mp & ~O["pl_inside"]).sum())
    L = O["lines"]
    n_ln = int(((L[:, 0] > x0) & (L[:, 0] < x1) & (L[:, 1] > y0) & (L[:, 1] < y1)).sum()) if len(L) else 0
    R = O["rivers"]
    n_rv = int(((R[:, 0] > x0) & (R[:, 0] < x1) & (R[:, 1] > y0) & (R[:, 1] < y1)).sum()) if len(R) else 0
    return n_sq, n_pl_in, n_pl_out, n_ln, n_rv


AMBIG_RATIO = 1.2   # a site number without a leader must sit >= 1.2 x nearer its own square than any other symbol


def _ambiguous(bb, own, O):
    """Label-to-symbol association check for a site number. `bb` is the text box (display px), `own` the anchor.
    Distances run from the text centre to the centre of every site square (and city dot, when O includes them).
    Returns (flag, ratio): flag is True when the nearest other symbol is closer than AMBIG_RATIO times the
    distance to the label's own square, so a reader could attach the number to the wrong site."""
    sq = O["sq"]
    if len(sq) < 2:
        return False, float("inf")
    c = np.array([(bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2])
    d = np.hypot(*(sq - c).T)
    mine = np.hypot(*(sq - own).T) < 0.5
    if not mine.any() or mine.all():
        return False, float("inf")
    ratio = float(d[~mine].min() / max(d[mine].min(), 1e-9))
    return ratio < AMBIG_RATIO, ratio


def _seg_dist(P, p, q):
    d = q - p; n2 = float(d @ d)
    if n2 < 1e-9 or not len(P):
        return np.full(len(P), np.inf)
    t = np.clip(((P - p) @ d) / n2, 0, 1)
    return np.hypot(*(P - (p + t[:, None] * d)).T)


def _leader_seg(bb, own):
    p = np.asarray(own, float)
    return p, np.array([np.clip(p[0], bb.x0, bb.x1), np.clip(p[1], bb.y0, bb.y1)])


def _segs_cross(a, b, c, d):
    o = lambda p, q, r: np.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]))
    return o(a, b, c) != o(a, b, d) and o(c, d, a) != o(c, d, b)


def _seg_box(p, q, bb):
    """True when segment p-q enters box bb (sampled; boxes here are a few points across)."""
    S_ = p + np.linspace(0, 1, 40)[:, None] * (q - p)
    return bool(((S_[:, 0] > bb.x0) & (S_[:, 0] < bb.x1) & (S_[:, 1] > bb.y0) & (S_[:, 1] < bb.y1)).any())


def _leader_conflicts(bb_pad, seg, placed_boxes, placed_segs):
    """Crossings between this candidate and already placed leaders: its own leader `seg` (or None) against
    placed leaders and placed label boxes, and its padded text box against placed leaders."""
    n = 0
    for (a, b) in placed_segs:
        if seg is not None and _segs_cross(seg[0], seg[1], a, b):
            n += 1
        if _seg_box(a, b, bb_pad):
            n += 1
    if seg is not None:
        n += sum(_seg_box(seg[0], seg[1], pb) for pb in placed_boxes)
    return n


LEADER_ALONG_MAX_PT = 4.0   # a leader may cross a boundary, but not run within tol of it for longer than this


def _leader_line_hits(bb, own, O, k, tol_pt=1.2):
    """Obstacles touched by a leader drawn from anchor `own` to the nearest point of text box `bb` (display px):
    1 if more than LEADER_ALONG_MAX_PT of the leader lies within tol_pt of a basin/state line (it would read as
    part of that line; a clean crossing is about 2 x tol_pt long and is allowed), plus every other site square
    (or city dot) the leader passes through, which would misattribute the number."""
    p = np.asarray(own, float)
    q = np.array([np.clip(p[0], bb.x0, bb.x1), np.clip(p[1], bb.y0, bb.y1)])
    n = 0
    L = O["lines"]; tol = tol_pt * k
    if len(L):
        lo, hi = np.minimum(p, q) - tol, np.maximum(p, q) + tol
        L = L[(L[:, 0] > lo[0]) & (L[:, 0] < hi[0]) & (L[:, 1] > lo[1]) & (L[:, 1] < hi[1])]
        if len(L):
            step = 0.25 * k
            m = max(int(np.hypot(*(q - p)) / step), 1)
            S_ = p + np.linspace(0, 1, m + 1)[:, None] * (q - p)
            near = (np.hypot(S_[:, None, 0] - L[None, :, 0], S_[:, None, 1] - L[None, :, 1]) < tol).any(1)
            n += int(near.sum() * np.hypot(*(q - p)) / m > LEADER_ALONG_MAX_PT * k)
    sq = O["sq"]
    if len(sq):
        other = np.hypot(*(sq - p).T) > 0.5
        n += int((_seg_dist(sq[other], p, q) < O["sq_half"] + tol_pt * k).sum())
    return n


DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.75, 0.75), (-0.75, 0.75), (0.75, -0.75), (-0.75, -0.75),
        (1, 0.45), (-1, 0.45), (1, -0.45), (-1, -0.45), (0.45, 1), (-0.45, 1), (0.45, -1), (-0.45, -1)]


def place(ax, anchors, texts, hard, O, family, color, size, radii, leader_from, own_is_site, dot_r_pt=0.0,
          plants_soft=False):
    fig = ax.figure; r = fig.canvas.get_renderer(); k = fig.dpi / 72
    axbb = ax.get_window_extent(r)
    placed = [b for b in hard]
    placed_segs = []   # leaders already drawn, in display px
    out, rep = [], []
    for (x, y), txt in zip(anchors, texts):
        pxy = ax.transData.transform((x, y))
        best, bscore = None, None
        for ri, rr in enumerate(radii):
            for di, (ux, uy) in enumerate(DIRS):
                ha = "left" if ux > 0.3 else ("right" if ux < -0.3 else "center")
                va = "bottom" if uy > 0.3 else ("top" if uy < -0.3 else "center")
                lead = rr >= leader_from
                t = ax.annotate(txt, (x, y), xytext=(ux * rr, uy * rr), textcoords="offset points", ha=ha, va=va,
                                fontsize=size, color=color, family=family, zorder=26,
                                arrowprops=(dict(arrowstyle="-", lw=S.V2_LW_TERTIARY if LEADER_LW is None else LEADER_LW,
                                                 color=S.V2_BLACK, shrinkA=0.6,
                                                 shrinkB=V2.SITE_MS_PT / 2 + 0.8) if lead else None))
                t.update_positions(r)
                bb = mtext.Text.get_window_extent(t, r).expanded(1, 1)
                bb = bb.from_extents(bb.x0 - LABEL_PAD_PT * k, bb.y0 - LABEL_PAD_PT * k,
                                     bb.x1 + LABEL_PAD_PT * k, bb.y1 + LABEL_PAD_PT * k)
                inside = axbb.x0 <= bb.x0 and bb.x1 <= axbb.x1 and axbb.y0 <= bb.y0 and bb.y1 <= axbb.y1
                n_lab = sum(bb.overlaps(pb) for pb in placed)
                n_sq, n_pli, n_plo, n_ln, n_rv = _hits(bb, O, own=pxy)
                tb = mtext.Text.get_window_extent(t, r)
                seg = _leader_seg(tb, pxy) if lead else None
                if lead:
                    n_ln += _leader_line_hits(tb, pxy, O, k)
                n_ln += _leader_conflicts(bb, seg, placed, placed_segs)
                if own_is_site:
                    n_sq -= 1 if (bb.x0 - O["sq_half"] < pxy[0] < bb.x1 + O["sq_half"] and
                                  bb.y0 - O["sq_half"] < pxy[1] < bb.y1 + O["sq_half"]) else 0
                    n_sq = max(n_sq, 0)
                own_hit = dot_r_pt > 0 and (bb.x0 - dot_r_pt * k < pxy[0] < bb.x1 + dot_r_pt * k and
                                            bb.y0 - dot_r_pt * k < pxy[1] < bb.y1 + dot_r_pt * k)
                # site numbers without a leader must read as belonging to their own square (see _ambiguous)
                # (leader labels are exempt, but among leader candidates the unambiguous ones rank first)
                amb_raw = bool(own_is_site and _ambiguous(mtext.Text.get_window_extent(t, r), pxy, O)[0])
                amb, amb_lead = int(amb_raw and not lead), int(amb_raw and lead)
                if plants_soft:   # plant outlines rank after leader and radius; the label carries a white halo
                    score = (not inside, n_lab, n_sq + int(own_hit), n_ln, 0, 0, amb, lead, amb_lead, ri,
                             n_pli + n_plo, n_rv, di)
                else:
                    score = (not inside, n_lab, n_sq + int(own_hit), n_ln, n_pli, n_plo, amb, lead, amb_lead, n_rv,
                             ri, di)
                if bscore is None or score < bscore:
                    if best is not None:
                        best.remove()
                    best, bscore, bbox, bseg = t, score, bb, seg
                else:
                    t.remove()
                if score[:8] == (False, 0, 0, 0, 0, 0, 0, False):
                    break
            if bscore[:8] == (False, 0, 0, 0, 0, 0, 0, False):
                break
        placed.append(bbox); out.append(best)
        if bseg is not None:
            placed_segs.append(bseg)
        if plants_soft:
            import matplotlib.patheffects as pe
            best.set_path_effects([pe.withStroke(linewidth=1.6, foreground="white")])
            best._reuse_ready_plants_soft = True
        rep.append({"label": txt, "outside_axes": bool(bscore[0]), "label_overlaps": int(bscore[1]),
                    "square_overlaps": int(bscore[2]), "boundary_line_hits": int(bscore[3]),
                    "plant_overlaps_inside": int(bscore[4]), "plant_overlaps_outside": int(bscore[5]),
                    "ambiguous": bool(bscore[6]), "leader": bool(bscore[7]),
                    "river_hits": int(bscore[9 if not plants_soft else 11]),
                    "plant_outlines_under_halo": int(bscore[10]) if plants_soft else 0,
                    "offset_pt": [round(v, 1) for v in best.xyann]})
    return out, rep


RIVER_LABELS = [("delaware", "Delaware River", (40.30, 41.40)), ("schuylkill", "Schuylkill River", (40.15, 40.60))]
RIVER_FALLBACK = {"delaware": (39.95, 41.95), "schuylkill": (40.05, 40.95)}  # searched only if the window fails
RIVER_OFFSETS_PT = (4.5, 6.0, 7.5, 9.0, 10.5, 12.0)


def _rot_rect(t, r):
    """Oriented rectangle of a rotated, center-anchored annotation in display pixels: (center, u, v, hw, hh)."""
    k = t.figure.dpi / 72
    rot = t.get_rotation()
    t.set_rotation(0); w0 = mtext.Text.get_window_extent(t, r); t.set_rotation(rot)
    c = np.asarray(t.axes.transData.transform(t.xy)) + np.asarray(t.xyann) * k
    a = np.radians(rot)
    u, v = np.array([np.cos(a), np.sin(a)]), np.array([-np.sin(a), np.cos(a)])
    return c, u, v, w0.width / 2 + LABEL_PAD_PT * k, w0.height / 2 + LABEL_PAD_PT * k


def _rot_hits(rect, O, placed):
    c, u, v, hw, hh = rect
    def inside(P, pad=0.0):
        if not len(P):
            return np.zeros(0, bool)
        d = np.asarray(P) - c
        return (np.abs(d @ u) < hw + pad) & (np.abs(d @ v) < hh + pad)
    n_sq = int(inside(O["sq"], O["sq_half"]).sum())
    pl = O["pl"]; n_pl = 0
    if len(pl):
        d = pl - c; du, dv = np.abs(d @ u) - hw, np.abs(d @ v) - hh
        n_pl = int((np.hypot(np.clip(du, 0, None), np.clip(dv, 0, None)) < O["pl_rad"]).sum())
    n_ln = int(inside(O["lines"]).sum())
    corners = np.array([c + su * hw * u + sv * hh * v for su in (-1, 1) for sv in (-1, 1)])
    x0, y0 = corners.min(0); x1, y1 = corners.max(0)
    n_lab = 0
    for b in placed:  # separating-axis test between the oriented rectangle and each axis-aligned box
        bc = np.array([(b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2]); bh = np.array([(b.x1 - b.x0) / 2, (b.y1 - b.y0) / 2])
        axes = [np.array([1.0, 0.0]), np.array([0.0, 1.0]), u, v]
        sep = False
        for ax_ in axes:
            ra = hw * abs(u @ ax_) + hh * abs(v @ ax_)
            rb = bh[0] * abs(ax_[0]) + bh[1] * abs(ax_[1])
            if abs((c - bc) @ ax_) > ra + rb:
                sep = True; break
        n_lab += not sep
    return n_sq, n_pl, n_ln, n_lab, (x0, y0, x1, y1)


def _river_candidates(ax, key, lat0, lat1):
    import geopandas as gpd
    g = gpd.read_file(V2.RAW / "gis" / f"nhd_{key}_river.geojson").to_crs(V2.AEA)
    pts = []
    for geom in g.geometry:
        for ln in ([geom] if geom.geom_type == "LineString" else list(getattr(geom, "geoms", []))):
            c = np.asarray(ln.segmentize(500.0).coords)[:, :2]
            if len(c) < 3:
                continue
            lat = np.array([V2.TO_LL.transform(*q)[1] for q in c])
            h = min(6, (len(c) - 1) // 2)       # tangent from points about 3 km either side
            for i in range(h, len(c) - h):
                if lat0 <= lat[i] <= lat1:
                    pts.append((c[i], c[i - h], c[i + h], lat[i]))
    mid = (lat0 + lat1) / 2
    pts.sort(key=lambda t_: abs(t_[3] - mid))
    return pts


def _try_river(ax, r, axbb, txt, pts, O, placed, family, size):
    for (pxy, a, b, _) in pts:
        da, db = ax.transData.transform(a), ax.transData.transform(b)
        ang = float(np.degrees(np.arctan2(db[1] - da[1], db[0] - da[0])))
        ang = ang - 180 if ang > 90 else (ang + 180 if ang < -90 else ang)
        nx, ny = -np.sin(np.radians(ang)), np.cos(np.radians(ang))
        for off in [o * TXT_K for o in RIVER_OFFSETS_PT]:
            for side in (1, -1):
                t = ax.annotate(txt, tuple(pxy), xytext=(side * nx * off, side * ny * off), textcoords="offset points",
                                ha="center", va="center", rotation=ang, rotation_mode="anchor", fontsize=size,
                                color=S.V2_GRAY_DARK, family=family, zorder=26)
                rect = _rot_rect(t, r)
                n_sq, n_pl, n_ln, n_lab, (x0, y0, x1, y1) = _rot_hits(rect, O, placed)
                inside = axbb.x0 <= x0 and x1 <= axbb.x1 and axbb.y0 <= y0 and y1 <= axbb.y1
                if inside and not (n_lab or n_sq or n_pl or n_ln):
                    return t, rect, ang
                t.remove()
    return None


def label_rivers(ax, D, hard, O, family, size):
    """One label per river, set parallel to the channel and offset to one side. Candidate anchors are sampled
    along the named NHD flowlines inside a latitude window (a wider fallback window is searched only if the
    first fails); the first candidate whose oriented text rectangle clears every placed label, site square,
    plant circle and basin/state line is used. (The Delaware main stem is itself the state line, so an
    axis-aligned box test would always fail.)"""
    from matplotlib.transforms import Bbox
    fig = ax.figure; r = fig.canvas.get_renderer()
    axbb = ax.get_window_extent(r)
    placed = list(hard); out, rep = [], []
    for key, txt, window in RIVER_LABELS:
        best = None
        for (lat0, lat1) in (window, RIVER_FALLBACK[key]):
            best = _try_river(ax, r, axbb, txt, _river_candidates(ax, key, lat0, lat1), O, placed, family, size)
            if best is not None:
                break
        if best is None:
            raise RuntimeError(f"no clean position for the {txt} label")
        t, rect, ang = best
        c, u, v, hw, hh = rect
        corners = np.array([c + su * hw * u + sv * hh * v for su in (-1, 1) for sv in (-1, 1)])
        placed.append(Bbox.from_extents(*corners.min(0), *corners.max(0)))
        t._reuse_ready_rect = rect
        out.append(t)
        rep.append({"label": txt, "rotation_deg": round(ang, 1),
                    "anchor_lonlat": [round(v_, 4) for v_ in V2.TO_LL.transform(*t.xy)],
                    "offset_pt": [round(v_, 1) for v_ in t.xyann]})
    return out, rep


def final_check(fig, ax, O, map_labels):
    """At export resolution: every pair of visible text boxes, plus each map label against site squares, plant
    circles and the basin/state lines. Returns lists of conflicts (empty lists mean clean)."""
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    ts = [t for t in fig.findobj(mtext.Text) if t.get_visible() and t.get_text().strip()]
    boxes = [(t, V2._tbb(t, r)) for t in ts]
    def _pair_overlap(a, ba, b, bb):
        ra, rb = getattr(a, "_reuse_ready_rect", None), getattr(b, "_reuse_ready_rect", None)
        if ra is None and rb is None:
            return ba.overlaps(bb)
        if ra is not None and rb is not None:
            return ba.overlaps(bb)
        rect, box_ = (ra, bb) if ra is not None else (rb, ba)
        return _rot_hits(_rot_rect(a if ra is not None else b, r), {"sq": np.zeros((0, 2)), "sq_half": 0,
                         "pl": np.zeros((0, 2)), "pl_rad": np.zeros(0), "lines": np.zeros((0, 2))}, [box_])[3] > 0
    tt = [(a.get_text(), b.get_text()) for (a, ba), (b, bb) in combinations(boxes, 2) if _pair_overlap(a, ba, b, bb)]
    fb = fig.bbox
    edge = [t.get_text() for t, b in boxes if b.x0 < fb.x0 or b.x1 > fb.x1 or b.y0 < fb.y0 or b.y1 > fb.y1]
    sym, halo = [], []
    for t in map_labels:
        if getattr(t, "_reuse_ready_rect", None) is not None:
            n_sq, n_pl, n_ln, _, _ = _rot_hits(_rot_rect(t, r), O, [])
            if n_sq or n_pl or n_ln:
                sym.append({"label": t.get_text(), "squares": n_sq, "plants": n_pl, "boundary_or_state_line": n_ln})
            continue
        bb = V2._tbb(t, r)
        own = ax.transData.transform(t.xy)
        n_sq, n_pli, n_plo, n_ln, _ = _hits(bb, O, own=own)
        if getattr(t, "arrow_patch", None) is not None:
            n_ln += _leader_line_hits(bb, own, O, ax.figure.dpi / 72)
        sqs = O["sq"]; h = O["sq_half"]
        own_sq = any(np.hypot(*(sqs - own).T) < 0.5)
        if own_sq and (bb.x0 - h < own[0] < bb.x1 + h and bb.y0 - h < own[1] < bb.y1 + h):
            n_sq -= 1
        if getattr(t, "_reuse_ready_plants_soft", False):
            halo.append({"label": t.get_text(), "plant_outlines": int(n_pli + n_plo)}) if (n_pli or n_plo) else None
            n_pli = n_plo = 0
        if n_sq > 0 or n_pli or n_plo or n_ln:
            sym.append({"label": t.get_text(), "squares": n_sq, "plants_inside": n_pli, "plants_outside": n_plo,
                        "boundary_or_state_line": n_ln})
    amb = []
    for t in map_labels:
        if t.get_text().isdigit() and t.arrow_patch is None:
            f, ratio = _ambiguous(V2._tbb(t, r), ax.transData.transform(t.xy), O)
            if f:
                amb.append({"label": t.get_text(), "other_to_own_distance_ratio": round(ratio, 2)})
    segs = [(t, _leader_seg(V2._tbb(t, r), ax.transData.transform(t.xy))) for t in map_labels
            if getattr(t, "arrow_patch", None) is not None]
    lx = []
    for (ta, sa_), (tb_, sb_) in combinations(segs, 2):
        if _segs_cross(*sa_, *sb_):
            lx.append([ta.get_text(), tb_.get_text()])
    for ta, (p, q) in segs:
        for t in map_labels:
            if t is not ta and _seg_box(p, q, V2._tbb(t, r)):
                lx.append([ta.get_text() + " leader", t.get_text()])
    out = {"text_text": tt, "text_outside_figure": edge, "label_symbol_or_line": sym, "site_number_ambiguous": amb,
           "leader_crossings": lx}
    if halo:
        out["haloed_city_label_over_plant_outline"] = halo   # permitted on the brief map; reported, not hidden
    return out


# ------------------------------------------------------------------------------------------------ map
def render_map_v3(D, stem_name="supply_screen_map_v3", map_h_mm=222.0, margins_mm=(8.0, 2.0, 11.0, 2.0),
                  sources=None, source_y_mm=1.8, rivers_lw=None):
    S.v2_rc()
    fam = S.register_fonts(); narrow = S.narrow_family()
    fig = plt.figure(figsize=(MAP_W_MM * MM, map_h_mm * MM), dpi=S.V2_DPI)
    l_mm, r_mm, b_mm, t_mm = margins_mm
    aw, ah = MAP_W_MM - l_mm - r_mm, map_h_mm - b_mm - t_mm
    ax = fig.add_axes([l_mm / MAP_W_MM, b_mm / map_h_mm, aw / MAP_W_MM, ah / map_h_mm])
    x0, y0, x1, y1 = D["drb"].total_bounds
    pad = 3500.0
    hgt = (y1 - y0) + 2 * pad
    wid = hgt * aw / ah
    xl = x0 - pad - 8000.0
    ext = (xl, y0 - pad, xl + wid, y1 + pad)
    relief, rext = V2.build_relief_aea(ext, D["drb"])
    V2.draw_base(ax, D, ext, relief, rext, rivers_lw=S.V2_LW_SECONDARY if rivers_lw is None else rivers_lw)
    inside = draw_features_v3(ax, D)
    tick_txt = V2.edge_ticks(ax, ext, 0.5)
    m_per_mm = wid / aw
    lg, sa, sb, lg_info = legend_v3(fig, ax, 2.5 * TXT_K, aw, ah, l_mm, b_mm, m_per_mm)
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    O = obstacles(ax, D, inside)
    hard = [V2._tbb(t, r) for t in tick_txt] + [lg.get_window_extent(r)]
    c = D["cities"]
    ax.scatter(c.geometry.x, c.geometry.y, s=4, c=S.V2_GRAY_DARK, lw=0, zorder=11)
    city_labels, city_rep = place(ax, [(g.x, g.y) for g in c.geometry], list(c["name"]), hard, O, narrow,
                                  S.V2_GRAY_DARK, CITY_SIZE, radii=CITY_RADII, leader_from=CITY_LEADER_FROM,
                                  own_is_site=False, dot_r_pt=1.3, plants_soft=CITY_HALO)
    hard2 = hard + [V2._tbb(t, r) for t in city_labels]
    # city dots are obstacles for site numbers
    O2 = dict(O); O2["sq"] = np.vstack([O["sq"], np.array([ax.transData.transform((g.x, g.y)) for g in c.geometry])])
    s = D["sites"]
    order = np.argsort([-len(str(n)) for n in s.number])  # no effect on result order, kept stable below
    num_labels, num_rep = place(ax, [(g.x, g.y) for g in s.geometry], [str(n) for n in s.number], hard2, O2, narrow,
                                S.V2_BLACK, NUM_SIZE, radii=[4.4, 5.6, 7.0, 8.6, 10.5, 13.0, 16.0, 20.0],
                                leader_from=8.6, own_is_site=True)
    hard3 = hard2 + [V2._tbb(t, r) for t in num_labels]
    river_labels, river_rep = label_rivers(ax, D, hard3, O2, narrow, CITY_SIZE)
    S.v2_source_line(fig, V2.MAP_SOURCES if sources is None else sources, y_mm=source_y_mm, x_mm=l_mm)
    chk = final_check(fig, ax, O2, num_labels + city_labels + river_labels)
    stem = FIGURES / stem_name
    for e in ("png", "pdf", "svg"):
        fig.savefig(f"{stem}.{e}", dpi=S.V2_DPI)
    rows = []
    for g, rr, t in zip(s.geometry, s.itertuples(), num_labels):
        rows.append({"element": "planned_site", "number": rr.number, "site_id": rr.site_id, "name": rr.name,
                     "lon": rr.lon, "lat": rr.lat, "x_aea_m": g.x, "y_aea_m": g.y, "covered_it_mw": rr.covered_it_mw,
                     "covered_it_class": rr.covered_it_bin, "fill": S.V2_FILL[rr.covered_it_bin],
                     "outline": "dashed" if rr.unverified else "solid", "radius_mi": 10.0,
                     "label_dx_pt": t.xyann[0], "label_dy_pt": t.xyann[1], "leader": t.arrow_patch is not None})
    p = D["plants"]
    for g, rr, ins in zip(p.geometry, p.itertuples(), inside):
        rows.append({"element": "municipal_plant", "site_id": rr.npdes_id, "name": rr.name, "lon": rr.lon,
                     "lat": rr.lat, "x_aea_m": g.x, "y_aea_m": g.y, "median_flow_mgd": rr.median_flow_mgd,
                     "marker_area_pt2": float(V2.plant_area(rr.median_flow_mgd)), "inside_basin": bool(ins),
                     "opacity": 1.0 if ins else OUTSIDE_ALPHA})
    for g, nm, t in zip(c.geometry, c["name"], city_labels):
        lon, lat = V2.TO_LL.transform(g.x, g.y)
        rows.append({"element": "reference_city", "name": nm, "lon": lon, "lat": lat, "x_aea_m": g.x, "y_aea_m": g.y,
                     "label_dx_pt": t.xyann[0], "label_dy_pt": t.xyann[1]})
    pd.DataFrame(rows).to_csv(f"{stem}_data.csv", index=False)
    plt.close(fig)
    fonts = {"primary": fam, "narrow": narrow}
    return {"fonts": fonts, "check": chk, "site_labels": num_rep, "city_labels": city_rep, "river_labels": river_rep,
            "legend": lg_info,
            "n_plants_inside": int(inside.sum()), "n_plants_outside": int((~inside).sum()),
            "n_leaders": int(sum(x["leader"] for x in num_rep)), "map_h_mm": map_h_mm, "map_w_mm": MAP_W_MM,
            "min_font_pt": float(min(t.get_fontsize() for t in fig.findobj(mtext.Text) if t.get_text().strip()))}


BRIEF_W_MM = 120.0
BRIEF_MIN_FONT_PT = 6.5


def render_brief(D):
    """Brief-size copy of the v3 map: same design and crop at 120 mm wide. Geometry (symbols, line weights,
    margins) scales by 120/180; text is set at max(7 x 120/180, 6.5) = 6.5 pt, and text-bound spacing (key rows,
    scale-bar rows) scales with the font. Module constants are patched for the duration of the call only."""
    global MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, SCALE_ROWS, CITY_LEADER_FROM, CITY_RADII, CITY_HALO, LEADER_LW
    k = BRIEF_W_MM / MAP_W_MM
    saved_leader = LEADER_LW
    LEADER_LW = S.V2_LW_SECONDARY * k    # 0.33 pt, as the plant outlines; scaled tertiary (0.17 pt) is invisible
    font = max(S.V2_FONT_SIZE * k, BRIEF_MIN_FONT_PT)
    fk = font / S.V2_FONT_SIZE
    saved_S = {n: getattr(S, n) for n in ("V2_FONT_SIZE", "V2_LW_PRIMARY", "V2_LW_SECONDARY", "V2_LW_TERTIARY")}
    saved_V2 = {n: getattr(V2, n) for n in ("SITE_MS_PT", "SITE_S", "PLANT_AREA_PER_MGD")}
    saved_me = (MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, SCALE_ROWS, CITY_LEADER_FROM, CITY_RADII, CITY_HALO)
    try:
        S.V2_FONT_SIZE = font
        for n in ("V2_LW_PRIMARY", "V2_LW_SECONDARY", "V2_LW_TERTIARY"):
            setattr(S, n, saved_S[n] * k)
        V2.SITE_MS_PT = saved_V2["SITE_MS_PT"] * k
        V2.SITE_S = V2.SITE_MS_PT ** 2
        V2.PLANT_AREA_PER_MGD = saved_V2["PLANT_AREA_PER_MGD"] * k * k
        MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, CITY_LEADER_FROM = BRIEF_W_MM, font, font, fk, 7.5
        CITY_RADII = CITY_RADII + [16.0, 18.0]
        CITY_HALO = True
        SCALE_ROWS = ((50, 25, "KILOMETERS", 1000.0), (30, 10, "MILES", 1609.344))
        src = V2.MAP_SOURCES.replace("NOAA ISD; ", "NOAA ISD;\n")
        info = render_map_v3(D, stem_name="supply_screen_map_v3_brief", map_h_mm=222.0 * k,
                             margins_mm=(8.0 * fk, 2.0 * k, 11.0 * fk + 2.6, 2.0 * k), sources=src,
                             source_y_mm=1.2, rivers_lw=saved_S["V2_LW_SECONDARY"] * k)
    finally:
        for n, v in saved_S.items():
            setattr(S, n, v)
        for n, v in saved_V2.items():
            setattr(V2, n, v)
        MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, SCALE_ROWS, CITY_LEADER_FROM, CITY_RADII, CITY_HALO = saved_me
        LEADER_LW = saved_leader
    info.update({"scale": k, "font_pt": font})
    return info


def write_caption_v3(D, key, info):
    with tempfile.TemporaryDirectory() as td:
        V2.write_captions(D, key, out_dir=Path(td))
        txt = (Path(td) / "supply_screen_map_v2_caption.md").read_text()
    txt = txt.replace("# Figure 1 (supply_screen_map_v2)", "# Figure 1 (supply_screen_map_v3)")
    txt = txt.replace("Circle area is proportional to the median monthly effluent flow reported from July 2023 to "
                      "June 2026 [epa_echo].",
                      "Circle area is proportional to the median monthly effluent flow reported from July 2023 to "
                      "June 2026 [epa_echo]; plants outside the basin are drawn at 40 percent opacity so that plants "
                      "inside the basin read first. In the key, IT load coverable at peak is the largest IT load, in "
                      "megawatts, whose peak-day makeup the nearest eligible plant's median flow covers.")
    (FIGURES / "supply_screen_map_v3_caption.md").write_text(txt)


def run():
    D = V2.load()
    key = V2.site_key(D["ss"])
    info = render_map_v3(D)
    write_caption_v3(D, key, info)
    # consistency with the v2 bar: same fills and counts per class
    m = pd.read_csv(FIGURES / "supply_screen_map_v3_data.csv")
    ms = m[m.element == "planned_site"].groupby(["covered_it_class", "fill"]).size().to_dict()
    bc = V2.bar_counts(D["ss"])
    bs = {(r.covered_it_class, r.fill): int(r.n_sites) for r in bc.itertuples()}
    info["map_bar_identical"] = all(ms.get(k) == v for k, v in bs.items()) and sum(bs.values()) == len(D["ss"])
    (RESULTS / "figures_v3_check.json").write_text(json.dumps(info, indent=1, default=str))
    brief = render_brief(D)
    cap = (FIGURES / "supply_screen_map_v3_caption.md").read_text()
    cap = cap.replace("# Figure 1 (supply_screen_map_v3)", "# Figure 1, brief size (supply_screen_map_v3_brief)")
    cap += (f"\n\nBrief-size version: the same design and extent at {BRIEF_W_MM:.0f} mm wide, with symbols and line "
            f"weights scaled by {brief['scale']:.3f} and all text at {brief['font_pt']:.1f} pt or larger. The kilometre "
            "scale bar is divided at 25 km, and city labels displaced from their point carry a short leader line; city labels carry a white halo and may cross the outline of a plant circle. Plotted values are in figures/supply_screen_map_v3_brief_data.csv.\n")
    (FIGURES / "supply_screen_map_v3_brief_caption.md").write_text(cap)
    (RESULTS / "figures_v3_brief_check.json").write_text(json.dumps(brief, indent=1, default=str))
    info["brief"] = {"check": brief["check"], "min_font_pt": brief["min_font_pt"], "leaders": brief["n_leaders"]}
    # STANDARDS H1: results/<stem>_check.json per figure. The haloed-city-over-plant-outline list on the brief map
    # is reported but permitted (see the brief caption), so it does not fail the check.
    for stem, d, min_pt in (("supply_screen_map_v3", info, S.V2_FONT_SIZE), ("supply_screen_map_v3_brief", brief,
                                                                            BRIEF_MIN_FONT_PT)):
        gate = {k: v for k, v in d["check"].items() if k != "haloed_city_label_over_plant_outline"}
        ok = not any(gate.values()) and d["min_font_pt"] >= min_pt - 1e-9
        (RESULTS / f"{stem}_check.json").write_text(json.dumps(
            {"figure": f"figures/{stem}", "pass": ok, "min_font_pt": d["min_font_pt"], "required_min_font_pt": min_pt,
             **d["check"]}, indent=1, default=str))
    return info


if __name__ == "__main__":
    i = run()
    print(json.dumps({"fonts": i["fonts"], "check": i["check"], "identical": i["map_bar_identical"],
                      "leaders": i["n_leaders"], "plants_in_out": [i["n_plants_inside"], i["n_plants_outside"]],
                      "legend_mm": [round(i["legend"]["w_mm"], 1), round(i["legend"]["h_mm"], 1)],
                      "city": [(x["label"], x["offset_pt"]) for x in i["city_labels"]],
                      "site_14_15": [x for x in i["site_labels"] if x["label"] in ("14", "15")]}, indent=1, default=str))
