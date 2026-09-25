"""Deliverable B: supply-screen map (PNG/PDF/SVG), companion bar chart, interactive HTML, captions, data CSVs.

Static map context (no tile service; CARTO Positron tiles now require an API key): Natural Earth 1:10m shaded
relief at low opacity [natural_earth], NHDPlus HR waterbodies and bay/estuary areas [usgs_nhdplus_hr], TIGER
state and county lines and reference-city interior points [census_tiger], WBD basin boundary [usgs_wbd].
Everything outside the basin is washed toward white. The interactive HTML uses Esri World Light Gray Canvas
tiles with Esri's attribution [esri_light_gray].

Sites are coloured by covered_it_mw: the largest IT load whose calibrated peak-day makeup the nearest eligible
municipal plant's median effluent flow covers. Outline: solid = exact location AND source page confirmed;
dashed = approximate or uncertain location, or source not confirmed.
"""
from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.text as mtext
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from shapely.geometry import box

from .. import basemap, styles
from ..paths import FIGURES, PROCESSED, RAW, RESULTS, SITES
from ..supply_screen import eligible_mask

MM = 1 / 25.4
WIDTH_IN = 180 * MM
HEIGHT_IN = 9.6
BIN_ORDER = ["over 200 MW", "50 to 200 MW", "no eligible plant within 10 mi"]
BIN_FILL = {"over 200 MW": "#9A4A0B", "50 to 200 MW": "#E8A15A", "no eligible plant within 10 mi": "#FFFFFF"}
SITE_EDGE = "#4A2506"
WATER = "#C9D6E3"
DASH = (0, (2.0, 1.2))
WWTP_AREA_PER_MGD = 3.0  # marker area (pt^2) per MGD of median flow: area-proportional
MAIN_KEYS = ["trackdatacenters_2026", "epa_echo", "noaa_isd", "stull_2011", "falls_levittown_2026", "usgs_wbd",
             "usgs_nhdplus_hr", "census_tiger", "natural_earth"]
EXTRA_LABELS = {"DRB02": (8, -10), "DRB23": (9, 4)}  # others omitted where no clear placement exists
CITY_OFFSETS = {"Philadelphia": (5, -6), "Trenton": (5, 5), "Wilmington": (-5, 4), "Allentown": (-5, 6),
                "Camden": (5, -5), "Reading": (-5, -6), "Scranton": (5, 0)}
# Philadelphia sits between site 18 and the large Philadelphia plant circles; a 1-pt finer search found (-7, 0)
# clear of both (the 8-pt grid step at (-8, 0) touches site 18), so it is tried before the grid
CITY_PREFER = {"Philadelphia": [(-7.0, 0.0)]}
RIVER_LABELS = {"Delaware River": (-75.07, 40.64, -63), "Schuylkill River": (-75.87, 40.55, 57)}


def _load():
    ss = pd.read_csv(RESULTS / "supply_screen.csv")
    ps = pd.read_csv(SITES / "planned_sites.csv")[["site_id", "dist_to_divide_km"]]
    ss = ss.merge(ps, on="site_id", how="left")
    summ = json.loads((RESULTS / "supply_summary.json").read_text())
    sites = gpd.GeoDataFrame(ss, geometry=gpd.points_from_xy(ss.lon, ss.lat), crs=4326)
    plants = gpd.read_file(PROCESSED / "wwtp_majors.geojson")
    plants = plants[eligible_mask(plants)].copy()
    drb = gpd.read_file(PROCESSED / "drb_boundary.geojson")
    rivers = {n: gpd.read_file(RAW / "gis" / f"nhd_{k}_river.geojson")
              for n, k in (("Delaware River", "delaware"), ("Schuylkill River", "schuylkill"))}
    return ss, summ, sites, plants, drb, rivers


def _context():
    counties = gpd.read_file(RAW / "gis" / "counties_pa_nj_de_ny.geojson")
    counties["geometry"] = counties.geometry.make_valid()
    states = counties.dissolve("STATE")
    wb = gpd.read_file(RAW / "gis" / "nhd_waterbody_0204.geojson")
    area = gpd.read_file(RAW / "gis" / "nhd_area_0204.geojson")
    water = pd.concat([wb[["geometry"]], area[["geometry"]]], ignore_index=True)
    water = gpd.GeoDataFrame(water, crs=4326)
    cities = basemap.load_cities()
    relief, rext = basemap.load_relief()
    return {k: v.to_crs(3857) for k, v in (("counties", counties), ("states", states), ("water", water),
                                           ("cities", cities))} | {"relief": relief, "relief_ext": rext}


def _wwtp_size(mgd):
    return np.clip(np.asarray(mgd, float), 0.3, None) * WWTP_AREA_PER_MGD


def _to3857(lon, lat):
    return gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs=4326).to_crs(3857).iloc[0].coords[0]


def _scale_bar(ax, km, lat, loc=(0.06, 0.05)):
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    L = km * 1000 / np.cos(np.radians(lat))
    xs = x0 + loc[0] * (x1 - x0); ys = y0 + loc[1] * (y1 - y0)
    ax.plot([xs, xs + L], [ys, ys], color=styles.INK, lw=0.8, solid_capstyle="butt", zorder=20)
    for xx in (xs, xs + L):
        ax.plot([xx, xx], [ys, ys + 0.008 * (y1 - y0)], color=styles.INK, lw=0.6, zorder=20)
    ax.text(xs + L / 2, ys + 0.014 * (y1 - y0), f"{km:g} km", ha="center", va="bottom", fontsize=styles.SMALL_SIZE,
            color=styles.INK, zorder=20)


def _north_arrow(ax, loc=(0.93, 0.90)):
    ax.annotate("N", xy=(loc[0], loc[1] + 0.05), xytext=(loc[0], loc[1]), xycoords="axes fraction",
                ha="center", va="top", fontsize=styles.SMALL_SIZE, color=styles.INK,
                arrowprops=dict(arrowstyle="-|>,head_width=0.18,head_length=0.35", lw=0.6, color=styles.INK))


def _draw_layers(ax, ctx, sites, plants, drb, rivers, buffers, extent, relief_alpha=0.30, river_lw=0.7):
    ax.set_xlim(extent[0], extent[2]); ax.set_ylim(extent[1], extent[3])
    ax.set_facecolor("white")
    ax.imshow(ctx["relief"], cmap="gray", vmin=0, vmax=255, alpha=relief_alpha, extent=ctx["relief_ext"],
              interpolation="bilinear", zorder=0)
    ctx["water"].plot(ax=ax, color=WATER, lw=0, zorder=1)
    ctx["counties"].boundary.plot(ax=ax, color="#DADDE1", lw=0.3, zorder=1.5)
    ctx["states"].boundary.plot(ax=ax, color="#A9AFB6", lw=0.6, zorder=1.6)
    outside = box(*extent).difference(drb.union_all())
    if not outside.is_empty:
        gpd.GeoSeries([outside], crs=3857).plot(ax=ax, color="white", alpha=0.62, lw=0, zorder=2)
    drb.boundary.plot(ax=ax, color="#7C8794", lw=0.6, zorder=3)
    buffers.plot(ax=ax, color=styles.SITE, alpha=0.06, lw=0, zorder=4)
    for g in rivers.values():
        g.plot(ax=ax, color=styles.RIVER, lw=river_lw, zorder=5)
    ax.scatter(plants.geometry.x, plants.geometry.y, s=_wwtp_size(plants.median_flow_mgd), c=styles.WWTP,
               edgecolors="white", linewidths=0.4, alpha=0.9, zorder=6)
    for unv, ls in ((False, "solid"), (True, DASH)):
        s = sites[sites.unverified.astype(bool) == unv]
        if len(s):
            ax.scatter(s.geometry.x, s.geometry.y, s=30, marker="D", c=[BIN_FILL[b] for b in s.covered_it_bin],
                       edgecolors=SITE_EDGE, linewidths=0.8, linestyles=[ls], zorder=8)
    ax.set_axis_off()


def _label(ax, x, y, text, dx, dy, weight="normal", size=None, color=None, arrow=True):
    return ax.annotate(text, xy=(x, y), xytext=(dx, dy), textcoords="offset points",
                       fontsize=size or styles.SMALL_SIZE, color=color or styles.INK, weight=weight,
                       ha="left" if dx >= 0 else "right", va="center",
                       arrowprops=(dict(arrowstyle="-", lw=0.4, color=styles.MUTED, shrinkA=1, shrinkB=2.5) if arrow
                                   else None), zorder=30,
                       path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])



def _tbb(t, rend):
    """Window extent of an annotation's text only (not its leader line)."""
    if isinstance(t, mtext.Annotation):
        t.update_positions(rend)
    return mtext.Text.get_window_extent(t, rend)

CANDIDATES = [(dx, dy) for r in (8, 12, 16, 22, 30, 40, 52) for (dx, dy) in
              ((1, 0.6), (1, -0.6), (-1, 0.6), (-1, -0.6), (1, 0), (-1, 0), (1, 1.4), (-1, 1.4), (1, -1.4), (-1, -1.4),
               (0.3, 2.0), (-0.3, -2.0), (0.3, -2.0), (-0.3, 2.0))
              for dx, dy in [(dx * r, dy * r)]]


def place_labels(fig, specs, symbols, fixed=()):
    """Greedy placement. specs: (ax, x, y, text, kw); symbols: (ax, xs, ys, radius_pt).
    For each label, the candidate offsets are scored by (inside axes, label overlaps, symbol overlaps, distance);
    a label never overlaps another label if any candidate avoids it. Returns (annotations, residual report)."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    k = fig.dpi / 72
    sym = []
    for ax, xs, ys, rad in symbols:
        for x, y in ax.transData.transform(np.column_stack([xs, ys])):
            sym.append((ax, x, y, rad * k))
    placed = [_tbb(t, rend) for t in fixed]
    out, residual = [], []
    for ax, x, y, text, kw in specs:
        kw = dict(kw)
        max_r = kw.pop("max_r", 1e9)
        prefer = list(kw.pop("prefer", []))
        axbb = ax.get_window_extent(rend)
        ax_xy = ax.transData.transform((x, y))
        own = [(sx, sy, r) for (sax, sx, sy, r) in sym if sax is ax and axbb.contains(sx, sy)
               and not (abs(sx - ax_xy[0]) < 1 and abs(sy - ax_xy[1]) < 1)]
        best, best_score = None, None
        for i, (dx, dy) in enumerate(prefer + CANDIDATES):
            if max(abs(dx), abs(dy)) > max_r * 2.0:
                continue
            t = _label(ax, x, y, text, dx, dy, **kw)
            bb = _tbb(t, rend).expanded(1.03, 1.08)
            inside = axbb.contains(bb.x0, bb.y0) and axbb.contains(bb.x1, bb.y1)
            n_lab = sum(bb.overlaps(pb) for pb in placed)
            n_sym = sum(bb.x0 - r < sx < bb.x1 + r and bb.y0 - r < sy < bb.y1 + r for sx, sy, r in own)
            score = (not inside, n_lab, n_sym, i)
            if best_score is None or score < best_score:
                if best is not None:
                    best.remove()
                best, best_score = t, score
            else:
                t.remove()
            if score[:3] == (False, 0, 0):
                break
        if best_score[:3] != (False, 0, 0):
            residual.append({"label": text.split("\n")[0], "outside_axes": best_score[0],
                             "label_overlaps": best_score[1], "symbol_overlaps": best_score[2]})
        placed.append(_tbb(best, rend))
        out.append(best)
    return out, residual


def _collisions(fig, labels, marker_pts):
    """Overlapping label pairs, and labels whose TEXT box covers a symbol other than the label's own anchor."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = []
    for t in labels:
        anchor = t.axes.transData.transform(t.xy) if hasattr(t, "xy") else None
        boxes.append((t.get_text().split("\n")[0], _tbb(t, r), anchor, t.axes))
    pairs = [(a, b) for i, (a, ba, _, _) in enumerate(boxes) for (b, bb, _, _) in boxes[i + 1:] if ba.overlaps(bb)]
    hits = []
    for name, bb, anc, ax in boxes:
        axbb = ax.get_window_extent(r)
        for (px, py, rad, what, sax) in marker_pts:
            if sax is not ax:   # symbols of another axes (the insets) are projected off that axes; ignore them
                continue
            if anc is not None and abs(px - anc[0]) < 1 and abs(py - anc[1]) < 1:
                continue
            if not (axbb.x0 <= px <= axbb.x1 and axbb.y0 <= py <= axbb.y1):
                continue
            if bb.x0 - rad < px < bb.x1 + rad and bb.y0 - rad < py < bb.y1 + rad:
                hits.append((name, what, round(px), round(py)))
    return pairs, hits


def render_map(out_stem=FIGURES / "supply_screen_map", check=True):
    family = styles.register_fonts()
    ss, summ, sites, plants, drb, rivers = _load()
    ctx = _context()
    s3 = sites.to_crs(3857); p3 = plants.to_crs(3857); d3 = drb.to_crs(3857)
    r3 = {k: v.to_crs(3857) for k, v in rivers.items()}
    buf = gpd.GeoDataFrame(geometry=sites.to_crs(5070).buffer(16093.44), crs=5070).to_crs(3857)
    pid = p3.set_index("npdes_id"); s3i = s3.set_index("site_id"); ssi = ss.set_index("site_id")

    hi = summ["headline_capacity_independent"]
    bins = summ["covered_it_bins"]
    n_ge50 = bins["50 to 200 MW"] + bins["over 200 MW"]
    assert n_ge50 == hi["n_within_10mi_of_eligible_potw"], "title claim must hold for every counted site"
    n_unv = int(ss.unverified.astype(bool).sum())
    n_unv_ge50 = int((ss.unverified.astype(bool) & (ss.covered_it_mw >= 50)).sum())
    per_mw = float(ss.peak_day_gpd.iloc[0] / ss.it_mw.iloc[0])
    title = (f"{n_ge50} of {hi['of']} planned data center sites sit within 10 miles of a municipal treatment plant "
             f"whose effluent could cover the peak-day cooling demand of at least 50 MW of IT load")
    subtitle = (f"{n_unv_ge50} of those {n_ge50} sites have an unverified location or source (dashed outline). "
                f"Effluent is the median monthly DMR flow from July 2023 to June 2026 at the nearest eligible plant "
                f"within 10 miles. Demand is the calibrated hybrid cooling model at {per_mw:,.0f} gal/day per MW of IT "
                f"load on the peak day (Trenton weather, 2005 to 2024). {hi['n_no_published_capacity']} of "
                f"{hi['of']} sites publish no capacity.")

    fig = plt.figure(figsize=(WIDTH_IN, HEIGHT_IN))
    top, bottom = 0.845, 0.075
    main = fig.add_axes([0.0, bottom, 0.60, top - bottom])
    ih = (top - bottom - 0.20 - 0.02) / 2
    insA = fig.add_axes([0.615, top - ih, 0.375, ih])
    insB = fig.add_axes([0.615, top - 2 * ih - 0.02, 0.375, ih])
    leg = fig.add_axes([0.615, bottom, 0.375, 0.19]); leg.set_axis_off()

    xmin, ymin, xmax, ymax = d3.total_bounds
    pad = 0.04 * (xmax - xmin)
    ax_w, ax_h = 0.60 * WIDTH_IN, (top - bottom) * HEIGHT_IN
    h = (ymax - ymin) + 2 * pad; w = h * ax_w / ax_h; cxm = (xmin + xmax) / 2
    ext = (cxm - w / 2, ymin - pad, cxm + w / 2, ymax + pad)
    _draw_layers(main, ctx, s3, p3, d3, r3, buf, ext)

    river_txt = []
    for name, (lon, lat, rot) in RIVER_LABELS.items():
        x, y = _to3857(lon, lat)
        river_txt.append(main.text(x, y, name, fontsize=styles.SMALL_SIZE, color="#55677A", style="italic", rotation=rot,
                  ha="center", va="center", zorder=9))
    for c in ctx["cities"].itertuples():
        x, y = c.geometry.coords[0]
        main.scatter([x], [y], s=6, c=styles.INK, marker="o", lw=0, zorder=9)
    inset_hw = (ih * HEIGHT_IN) / (0.375 * WIDTH_IN)
    def ext_around(lon, lat, half_km):
        x, y = _to3857(lon, lat); k = 1 / np.cos(np.radians(lat))
        return (x - half_km * 1e3 * k, y - half_km * inset_hw * 1e3 * k, x + half_km * 1e3 * k, y + half_km * inset_hw * 1e3 * k)
    eA = ext_around(-74.755, 40.175, 13); eB = ext_around(-75.32, 40.092, 9)
    for ax, e, tag, lat in ((insA, eA, "A  Lower Bucks County", 40.18), (insB, eB, "B  Conshohocken, Schuylkill River", 40.09)):
        _draw_layers(ax, ctx, s3, p3, d3, r3, buf, e, relief_alpha=0.18, river_lw=1.0)
        ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, lw=0.5, ec="#9AA3AD", zorder=40))
        ax.text(0.03, 0.96, tag, transform=ax.transAxes, fontsize=styles.SMALL_SIZE, weight="normal", va="top",
                color=styles.INK, bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.2), zorder=41)
        _scale_bar(ax, 5 if tag.startswith("A") else 2, lat, loc=(0.06, 0.06))
        main.add_patch(Rectangle((e[0], e[1]), e[2] - e[0], e[3] - e[1], fill=False, lw=0.6, ec=styles.INK, zorder=25))
        main.text(e[2], e[3], " " + tag[0], fontsize=styles.SMALL_SIZE, weight="normal", va="bottom", ha="left", zorder=25)

    fal = ssi.loc["DRB12"]; ply = ssi.loc["DRB31"]
    xy = lambda sid: s3i.loc[sid].geometry.coords[0]
    pxy = lambda npdes: pid.loc[npdes].geometry.coords[0]
    bold = {"weight": "bold"}
    specs = [
        (insA, *xy("DRB12"), f"Falls Twp, AWS Keystone\ncovers {fal.covered_it_mw:,.0f} MW IT", bold),
        (insA, *pxy(fal.plant_npdes_id), f"Trenton Sewer Utility (NJ)\n{fal.plant_median_flow_mgd:.3g} MGD, "
                                         f"{fal.distance_mi:.3g} mi", {}),
        (insA, *pxy(fal.same_state_npdes_id), f"Morrisville Borough STP (PA)\n{fal.same_state_median_flow_mgd:.3g} MGD, "
                                              f"{fal.same_state_distance_mi:.3g} mi", {}),
        (insB, *xy("DRB31"), f"Plymouth Twp site\ncovers {ply.covered_it_mw:,.0f} MW IT", bold),
        (insB, *pxy(ply.plant_npdes_id), f"Matsunk STP\n{ply.plant_median_flow_mgd:.3g} MGD, {ply.distance_mi:.3g} mi", {}),
    ]
    for sid in EXTRA_LABELS:
        r = ssi.loc[sid]
        cap = f"{r.stated_mw:,.0f} MW stated" if pd.notna(r.stated_mw) else "capacity not published"
        cov = "no plant within 10 mi" if r.covered_it_mw == 0 else f"covers {r.covered_it_mw:,.0f} MW"
        import textwrap
        body = "\n".join(textwrap.wrap(r["name"], 30)) + f"\n{cap}; {cov}"
        if bool(r.near_divide):
            body += f"\n{r.dist_to_divide_km:.2f} km inside the basin divide"
        specs.append((main, *xy(sid), body, {"max_r": 30}))
    for c in ctx["cities"].itertuples():
        specs.append((main, *c.geometry.coords[0], c.name, {"color": styles.MUTED, "arrow": False, "max_r": 12,
                                                             "prefer": CITY_PREFER.get(c.name, [])}))
    symbols = []
    for ax in (main, insA, insB):
        symbols.append((ax, s3.geometry.x.values, s3.geometry.y.values, np.sqrt(30) / 2 + 1))
        big = p3.median_flow_mgd.values >= 2.0  # smaller plants are dots a haloed label may cross
        for (x, y), a in zip(zip(p3.geometry.x.values[big], p3.geometry.y.values[big]),
                             _wwtp_size(p3.median_flow_mgd.values[big])):
            symbols.append((ax, [x], [y], np.sqrt(a) / 2 + 0.5))
    all_labels, unresolved = place_labels(fig, specs, symbols, fixed=river_txt)
    _scale_bar(main, 25, 40.5, loc=(0.05, 0.03)); _north_arrow(main, loc=(0.93, 0.97))

    # legend
    y = 0.98
    leg.text(0, y, "Planned site: IT load the nearest plant's effluent covers", fontsize=styles.SMALL_SIZE,
             weight="normal", va="top")
    for i, b in enumerate(BIN_ORDER):
        yy = y - 0.15 - i * 0.11
        leg.scatter([0.03], [yy], s=30, marker="D", c=BIN_FILL[b], edgecolors=SITE_EDGE, linewidths=0.8)
        lab = b
        leg.text(0.08, yy, f"{lab}, n = {bins[b]}", fontsize=styles.SMALL_SIZE, va="center")
    yy = y - 0.50
    leg.scatter([0.03], [yy], s=30, marker="D", c="white", edgecolors=SITE_EDGE, linewidths=0.8)
    leg.text(0.08, yy, f"verified, n = {len(ss) - n_unv}", fontsize=styles.SMALL_SIZE, va="center")
    leg.scatter([0.45], [yy], s=30, marker="D", c="white", edgecolors=SITE_EDGE, linewidths=0.8, linestyles=[DASH])
    leg.text(0.50, yy, f"unverified, n = {n_unv}", fontsize=styles.SMALL_SIZE, va="center")
    yy = y - 0.63
    leg.add_patch(Rectangle((0.005, yy - 0.04), 0.05, 0.08, color=styles.SITE, alpha=0.12, lw=0))
    leg.text(0.08, yy, "10-mile radius", fontsize=styles.SMALL_SIZE, va="center")
    leg.plot([0.36, 0.41], [yy, yy], color=styles.RIVER, lw=1.0)
    leg.text(0.43, yy, "river", fontsize=styles.SMALL_SIZE, va="center")
    leg.add_patch(Rectangle((0.58, yy - 0.04), 0.05, 0.08, color=WATER, lw=0))
    leg.text(0.65, yy, "reservoir, bay", fontsize=styles.SMALL_SIZE, va="center")
    yy = y - 0.80
    leg.text(0, yy + 0.02, "Municipal plant,\nmedian flow", fontsize=styles.SMALL_SIZE, va="center")
    for j, q in enumerate((5, 25, 100)):
        xx = 0.45 + j * 0.18
        leg.scatter([xx], [yy - 0.01], s=_wwtp_size(q), c=styles.WWTP, edgecolors="white", linewidths=0.4)
        leg.text(xx, yy - 0.17, f"{q} MGD", fontsize=styles.SMALL_SIZE, ha="center", va="center")
    leg.set_xlim(0, 1); leg.set_ylim(0, 1)

    m_in = styles.FIG_MARGIN_IN if hasattr(styles, "FIG_MARGIN_IN") else 0.1
    fig.text(m_in / WIDTH_IN, 0.992, title, fontsize=styles.TITLE_SIZE, weight="normal", va="top", ha="left",
             wrap=True, color=styles.INK)
    fig.text(m_in / WIDTH_IN, 0.925, subtitle, fontsize=styles.SUBTITLE_SIZE, va="top", ha="left", wrap=True,
             color=styles.MUTED)
    src = styles.source_line(fig, MAIN_KEYS, extra="Plotted values are in figures/supply_screen_map_data.csv.")
    src.set_wrap(True)

    report = {"unresolved_labels": unresolved}
    if check:
        mk = []
        for ax, xs, ys, rad in symbols:
            for x, y in ax.transData.transform(np.column_stack([xs, ys])):
                mk.append((x, y, rad * fig.dpi / 72, "symbol", ax))
        pairs, hits = _collisions(fig, all_labels, mk)
        report.update({"label_pairs_overlapping": pairs, "labels_over_symbols": hits})
    for ext_ in ("png", "pdf", "svg"):
        fig.savefig(f"{out_stem}.{ext_}", dpi=300)
    _write_map_data(ss, plants, ctx["cities"], out_stem)
    return fig, family, report


def _write_map_data(ss, plants, cities, out_stem):
    a = ss.assign(element="planned_site", marker_fill=ss.covered_it_bin.map(BIN_FILL),
                  outline=np.where(ss.unverified.astype(bool), "dashed", "solid"), buffer_radius_mi=10.0)
    a = a[["element", "site_id", "name", "lon", "lat", "status", "stated_mw", "it_mw", "capacity_basis", "covered_it_mw",
           "covered_it_bin", "marker_fill", "outline", "unverified", "plant_npdes_id", "plant_name", "distance_mi",
           "plant_median_flow_mgd", "peak_day_gpd", "buffer_radius_mi", "source_url"]]
    b = pd.DataFrame({"element": "municipal_plant", "site_id": plants.npdes_id, "name": plants["name"],
                      "lon": plants.lat * 0 + plants.geometry.x, "lat": plants.geometry.y,
                      "plant_median_flow_mgd": plants.median_flow_mgd,
                      "marker_area_pt2": _wwtp_size(plants.median_flow_mgd)})
    c = pd.DataFrame({"element": "reference_city", "name": cities.to_crs(4326)["name"],
                      "lon": cities.to_crs(4326).geometry.x, "lat": cities.to_crs(4326).geometry.y})
    pd.concat([a, b, c], ignore_index=True).to_csv(f"{out_stem}_data.csv", index=False)


def render_bar(out=FIGURES / "supply_screen_bar.png"):
    styles.register_fonts()
    ss = pd.read_csv(RESULTS / "supply_screen.csv")
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.6))
    fig.subplots_adjust(left=0.03, right=0.97, top=0.56, bottom=0.34)
    left, rows = 0, []
    plt.rcParams["hatch.color"] = SITE_EDGE
    plt.rcParams["hatch.linewidth"] = 0.5
    for b in BIN_ORDER:
        sub = ss[ss.covered_it_bin == b]
        for unv in (False, True):
            n = int((sub.unverified.astype(bool) == unv).sum())
            rows.append({"covered_it_bin": b, "verification": "unverified" if unv else "verified", "n_sites": n,
                         "left": left})
            if n:
                ax.barh([0], [n], left=left, height=0.6, color=BIN_FILL[b], edgecolor=SITE_EDGE, lw=0.7,
                        hatch="////" if unv else None)
                left += n
        ha = "right" if b == BIN_ORDER[-1] else ("left" if b == BIN_ORDER[0] else "center")
        xt = left if ha == "right" else (left - len(sub) if ha == "left" else left - len(sub) / 2)
        ax.text(xt, 0.42, f"{b}: {len(sub)} sites", ha=ha, va="bottom", fontsize=styles.SMALL_SIZE)
    ax.set_xlim(0, len(ss)); ax.set_ylim(-0.4, 0.9)
    ax.set_yticks([]); ax.set_xticks([0, 6, 12, 18, 24]); ax.tick_params(axis="x", labelsize=styles.SMALL_SIZE, length=2)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.5)
    ax.set_xlabel("Active planned data center sites (count); hatched segments have an unverified location or source",
                  fontsize=styles.SMALL_SIZE)
    n_ge50 = int((ss.covered_it_mw >= 50).sum())
    fig.text(0.03, 0.97, f"{n_ge50} of {len(ss)} planned sites have a municipal plant within 10 miles whose\neffluent "
             f"covers the peak-day cooling demand of at least 50 MW of IT load", fontsize=styles.TITLE_SIZE,
             weight="normal", va="top")
    fig.text(0.03, 0.74, "IT load covered at peak day by the nearest eligible plant's median flow, "
             "calibrated hybrid cooling model.", fontsize=styles.SUBTITLE_SIZE, va="top", color=styles.MUTED)
    styles.source_line(fig, ["trackdatacenters_2026", "epa_echo", "noaa_isd", "falls_levittown_2026"],
                       extra="Plotted values are in figures/supply_screen_bar_data.csv.").set_wrap(True)
    fig.savefig(out, dpi=300)
    fig.savefig(out.with_suffix(".pdf"))
    pd.DataFrame(rows).to_csv(FIGURES / "supply_screen_bar_data.csv", index=False)
    return fig


ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Tiles &copy; Esri: Esri, DeLorme, NAVTEQ"


def render_html(out=FIGURES / "supply_screen_map.html"):
    import folium
    ss, summ, sites, plants, drb, rivers = _load()
    m = folium.Map(location=[40.4, -75.3], zoom_start=8, tiles=None, control_scale=True)
    folium.TileLayer(tiles=ESRI_URL, attr=ESRI_ATTR, name="Esri World Light Gray Canvas", max_zoom=16).add_to(m)
    folium.GeoJson(drb.__geo_interface__, name="Delaware River Basin",
                   style_function=lambda f: {"color": "#7C8794", "weight": 1, "fillOpacity": 0}).add_to(m)
    for k, g in rivers.items():
        folium.GeoJson(g.__geo_interface__, name=k,
                       style_function=lambda f: {"color": styles.RIVER, "weight": 1.5}).add_to(m)
    fg = folium.FeatureGroup(name="Municipal plants (eligible)").add_to(m)
    for r in plants.itertuples():
        folium.CircleMarker([r.lat, r.lon], radius=float(np.sqrt(max(r.median_flow_mgd, 0.3)) * 1.6), color="white",
                            weight=0.6, fill=True, fill_color=styles.WWTP, fill_opacity=0.9,
                            tooltip=f"<b>{r.name}</b> ({r.state}), municipal plant<br>NPDES {r.npdes_id}<br>median flow "
                                    f"{r.median_flow_mgd:.3g} MGD ({int(r.dmr_flow_months)} months)<br>design "
                                    f"{r.design_flow_mgd:.3g} MGD").add_to(fg)
    fs = folium.FeatureGroup(name="Planned sites").add_to(m)
    for r in ss.itertuples():
        stated = (f"{r.stated_mw:,.0f} MW stated (campus power)" if pd.notna(r.stated_mw)
                  else "no capacity published (100 MW IT assumed)")
        plant = (f"{r.plant_name} ({r.plant_state}), {r.distance_mi:.3g} mi, median {r.plant_median_flow_mgd:.3g} MGD"
                 if pd.notna(r.plant_name) else "no eligible municipal plant within 10 mi")
        verified = "verified location and source" if not r.unverified else "unverified location or source"
        html = (f"<b>{r.name}</b><br>{r.municipality}, {r.county}<br>status: {r.status}<br>"
                f"<b>covered IT load: {r.covered_it_mw:,.0f} MW (class: {r.covered_it_bin})</b><br>{stated}<br>nearest plant: {plant}<br>"
                f"modelled peak-day makeup at {r.it_mw:,.0f} MW IT: {r.peak_day_gpd:,.0f} gal/day<br>{verified}<br>"
                f"<a href='{r.source_url}' target='_blank'>source</a>")
        folium.RegularPolygonMarker([r.lat, r.lon], number_of_sides=4, rotation=45, radius=7, color=SITE_EDGE,
                                    weight=1.2, dash_array="3,2" if r.unverified else None, fill=True,
                                    fill_color=BIN_FILL[r.covered_it_bin], fill_opacity=1,
                                    tooltip=folium.Tooltip(html), popup=folium.Popup(html, max_width=320)).add_to(fs)
    folium.LayerControl(collapsed=True).add_to(m)
    m.save(str(out))
    return out


def write_captions():
    ss = pd.read_csv(RESULTS / "supply_screen.csv")
    summ = json.loads((RESULTS / "supply_summary.json").read_text())
    cal = json.loads((RESULTS / "calibration.json").read_text())["primary"]
    hi, bins = summ["headline_capacity_independent"], summ["covered_it_bins"]
    n_unv = int(ss.unverified.astype(bool).sum())
    n_ge50 = bins["50 to 200 MW"] + bins["over 200 MW"]
    n_unv_ge50 = int((ss.unverified.astype(bool) & (ss.covered_it_mw >= 50)).sum())
    per_mw = float(ss.peak_day_gpd.iloc[0] / ss.it_mw.iloc[0])
    fal = ss.set_index("site_id").loc["DRB12"]; ply = ss.set_index("site_id").loc["DRB31"]
    keys = ", ".join(MAIN_KEYS + ["esri_light_gray"])
    m = f"""# Figure B. Supply screen: planned data centers and municipal effluent within 10 miles

**Caption.** The map shows the {hi['of']} active planned data center sites in the Delaware River Basin listed by the Data Center Proposal Tracker [trackdatacenters_2026], each coloured by the largest IT load whose modelled peak-day cooling makeup could be met by the median effluent flow of the nearest eligible municipal treatment plant within 10 miles. {n_ge50} of {hi['of']} sites have such a plant able to cover at least 50 MW of IT load ({bins['over 200 MW']} over 200 MW and {bins['50 to 200 MW']} between 50 and 200 MW), and {bins['no eligible plant within 10 mi']} have no eligible plant within 10 miles. Of the {n_ge50}, {n_unv_ge50} have an unverified location or source and are drawn with a dashed outline; across all {hi['of']} sites, {n_unv} are unverified. Plant circles are scaled by area to median monthly flow reported in discharge monitoring reports from July 2023 to June 2026 [epa_echo]. Shaded disks are 10-mile radii computed in an equal-area projection (EPSG:5070). Inset A shows Lower Bucks County, where the Falls Township (AWS Keystone Trade Center) site is matched to the Trenton Sewer Utility in New Jersey ({fal.plant_median_flow_mgd:.3g} MGD at {fal.distance_mi:.3g} mi, covering {fal.covered_it_mw:,.0f} MW of IT load); the nearest eligible Pennsylvania plant is the Morrisville Borough STP ({fal.same_state_median_flow_mgd:.3g} MGD at {fal.same_state_distance_mi:.3g} mi, covering {fal.same_state_covered_it_mw:,.0f} MW). Inset B shows the Plymouth Township (Conshohocken) site, matched to the Matsunk STP ({ply.plant_median_flow_mgd:.3g} MGD at {ply.distance_mi:.3g} mi, covering {ply.covered_it_mw:,.0f} MW).

**Assumptions.** Demand is the calibrated hybrid cooling model of results/calibration.json at {per_mw:,.0f} gal/day of peak-day makeup per MW of IT load (model-derived; Trenton hourly weather 2005 to 2024 [noaa_isd], wet-bulb temperature from Stull (2011) [stull_2011]), calibrated to the reported Falls average of 135,000 gal/day and peak of 4.4 million gal/day [falls_levittown_2026]. Eligible plants are municipal (POTW) majors with at least 12 months of flow reports; industrial dischargers are excluded from the headline. Covered IT load equals median plant flow divided by peak-day makeup per MW, so it does not depend on each site's capacity, which {hi['n_no_published_capacity']} of {hi['of']} sites do not publish. A site is verified when its location is exact and its cited source page was opened and names the site. The basin boundary is the dissolve of WBD HUC6 020401 and 020402 [usgs_wbd]; rivers, reservoirs and the bay are from NHDPlus HR [usgs_nhdplus_hr]; state and county lines and city points are from TIGERweb [census_tiger]; relief is Natural Earth [natural_earth]. The interactive version (figures/supply_screen_map.html) uses Esri World Light Gray Canvas tiles [esri_light_gray]. Plotted values are in figures/supply_screen_map_data.csv.

**Citation keys.** {keys}.
"""
    (FIGURES / "supply_screen_map_caption.md").write_text(m)
    b = f"""# Figure B2. Planned sites by IT load covered by the nearest municipal plant

**Caption.** The bar divides the {hi['of']} active planned data center sites [trackdatacenters_2026] by the largest IT load whose modelled peak-day cooling makeup the median effluent flow of the nearest eligible municipal plant within 10 miles could cover [epa_echo]: {bins['over 200 MW']} sites over 200 MW, {bins['50 to 200 MW']} between 50 and 200 MW, and {bins['no eligible plant within 10 mi']} with no eligible plant within 10 miles. Hatched segments are sites with an unverified location or source ({n_unv} of {hi['of']}).

**Assumptions.** The same demand rate ({per_mw:,.0f} gal/day per MW of IT load on the peak day, model-derived from results/calibration.json [noaa_isd; falls_levittown_2026]) and plant eligibility rules as Figure B apply. Plotted values are in figures/supply_screen_bar_data.csv.

**Citation keys.** trackdatacenters_2026, epa_echo, noaa_isd, falls_levittown_2026.
"""
    (FIGURES / "supply_screen_bar_caption.md").write_text(b)


def run():
    """Write the interactive HTML map (figures/supply_screen_map.html). The first static map and bar
    (render_map, render_bar, write_captions) were superseded by figures_v3 and figures_v2 and are no longer
    written; the functions are kept for reference and are not called by the build."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    html = render_html()
    return {"html": str(html)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
