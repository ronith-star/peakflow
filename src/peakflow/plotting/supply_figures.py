"""Supply-screen figures in the style of a USGS Scientific Investigations Report.

Builds, from results/supply_screen.csv, results/supply_summary.json and results/calibration.json:
  figures/supply_screen_map.{png,pdf,svg}, _caption.md, _data.csv        single-panel map, 180 mm wide
  figures/supply_screen_map_brief.{png,pdf,svg}, _caption.md, _data.csv  the same map, 120 mm wide
  figures/supply_screen_bar.{png,pdf,svg}, _caption.md, _data.csv        one-bar summary, 85 mm wide
  figures/falls_plymouth_detail.{png,pdf,svg}, _caption.md, _data.csv    two-panel appendix detail
  figures/site_key.csv                                                   number -> site key for the map
  results/supply_figures_report.json                                     bar and detail label reports, palette check
  results/supply_screen_map_report.json, results/supply_screen_map_brief_report.json   map layout reports
  results/<stem>_check.json   pass/fail layout gate per figure (text pairs, figure edge, label against symbol and
                              line, site-number ambiguity, leader crossings, minimum font)
No titles, sentences, citation keys or file paths inside images; explanation lives in the caption files.
Projection: Albers equal-area conic, NAD83, standard parallels 39 and 42 N, central meridian 75.3 W, so that
north is up at the basin and the scale bar is valid across the map.
Map typography: Helvetica, then Arial, then Liberation Sans; Arial Narrow or Liberation Sans Narrow for site
numbers and city labels. The key, in the lower-right corner, holds the scale bars, with unit labels below each
bar. Plants outside the basin are drawn at 40 percent opacity. The map label placer treats label padding, site
squares, plant circles, the basin boundary and state lines as obstacles.
"""
from __future__ import annotations

import json
import zipfile
from itertools import combinations

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.text as mtext
import numpy as np
import pandas as pd
from matplotlib.patches import Circle, Rectangle
from pyproj import Transformer
from scipy.optimize import brentq
from shapely.geometry import box

from .. import styles as S
from ..paths import FIGURES, PROCESSED, RAW, RESULTS
from ..supply_screen import eligible_mask

AEA = "+proj=aea +lat_0=40 +lon_0=-75.3 +lat_1=39 +lat_2=42 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs"
TO_AEA = Transformer.from_crs(4326, AEA, always_xy=True)
TO_LL = Transformer.from_crs(AEA, 4326, always_xy=True)
MM = 1 / 25.4
PT_PER_MM = 72 / 25.4
BAR_W_MM, BAR_H_MM = 85.0, 30.0
DET_W_MM, DET_H_MM = 180.0, 96.0
SITE_MS_PT = 5.2                    # square side in points
SITE_S = SITE_MS_PT ** 2            # scatter area (pt^2) for marker "s"
PLANT_AREA_PER_MGD = 3.0            # pt^2 per MGD of median flow, area-proportional
MAP_CITIES = ["Philadelphia", "Trenton", "Wilmington", "Allentown", "Scranton"]
STATES_FP = {"42": "PA", "34": "NJ", "10": "DE", "36": "NY", "24": "MD", "09": "CT"}
MAP_SOURCES = ("Sources: DRBC; U.S. EPA ECHO; USGS WBD and NHD; NOAA ISD; U.S. Census Bureau; Natural Earth; "
               "trackdatacenters.com.")
BAR_SOURCES = "Sources: U.S. EPA ECHO; NOAA ISD; trackdatacenters.com."
DET_SOURCES = "Sources: U.S. EPA ECHO; USGS WBD and NHD; U.S. Census Bureau; trackdatacenters.com."
RELIEF_AEA = PROCESSED / "relief_drb_aea.npz"


# ------------------------------------------------------------------------------------------------ data
def load():
    ss = pd.read_csv(RESULTS / "supply_screen.csv")
    summ = json.loads((RESULTS / "supply_summary.json").read_text())
    cal = json.loads((RESULTS / "calibration.json").read_text())
    ss = ss.sort_values(["lat", "lon"], ascending=[False, True]).reset_index(drop=True)
    ss["number"] = np.arange(1, len(ss) + 1)
    sites = gpd.GeoDataFrame(ss, geometry=gpd.points_from_xy(ss.lon, ss.lat), crs=4326).to_crs(AEA)
    plants = gpd.read_file(PROCESSED / "wwtp_majors.geojson")
    plants = plants[eligible_mask(plants)].to_crs(AEA)
    drb = gpd.read_file(PROCESSED / "drb_boundary.geojson").to_crs(AEA)
    rivers = pd.concat([gpd.read_file(RAW / "gis" / f"nhd_{k}_river.geojson")[["geometry"]]
                        for k in ("delaware", "schuylkill")], ignore_index=True)
    rivers = gpd.GeoDataFrame(rivers, crs=4326).to_crs(AEA)
    water = pd.concat([gpd.read_file(RAW / "gis" / f)[["geometry"]]
                       for f in ("nhd_waterbody_0204.geojson", "nhd_area_0204.geojson")], ignore_index=True)
    water = gpd.GeoDataFrame(water, crs=4326).to_crs(AEA)
    water["geometry"] = water.geometry.make_valid()
    states = gpd.read_file(RAW / "gis" / "cb_2023_us_state_500k.zip")
    states = states[states.STATEFP.isin(STATES_FP)].to_crs(AEA)
    counties = gpd.read_file(RAW / "gis" / "cb_2023_us_county_500k.zip")
    counties = counties[counties.STATEFP.isin(STATES_FP)].to_crs(AEA)
    for g in (states, counties):
        g["geometry"] = g.geometry.make_valid()
    from ..basemap import load_cities
    cities = load_cities()
    cities = cities[cities["name"].isin(MAP_CITIES)].to_crs(AEA)
    return dict(ss=ss, summ=summ, cal=cal, sites=sites, plants=plants, drb=drb, rivers=rivers, water=water,
                states=states, counties=counties, cities=cities)


def site_key(ss) -> pd.DataFrame:
    k = pd.DataFrame({
        "number": ss.number, "site_id": ss.site_id, "name": ss["name"], "municipality": ss.municipality,
        "county": ss.county, "stated_mw": ss.stated_mw, "covered_it_mw": ss.covered_it_mw.round(0),
        "covered_it_class": ss.covered_it_bin,
        "verified": np.where(ss.unverified.astype(bool), "no", "yes")})
    k.to_csv(FIGURES / "site_key.csv", index=False)
    return k


def build_relief_aea(bounds_aea, drb, force=False):
    """Natural Earth SR_HR reprojected to the map CRS, masked to the basin interior."""
    if RELIEF_AEA.exists() and not force:
        d = np.load(RELIEF_AEA)
        return d["relief"], tuple(d["extent"])
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds as tfb
    from rasterio.warp import Resampling, reproject
    from rasterio.windows import from_bounds
    from ..basemap import MAP_BOUNDS_4326, NE_DIR
    zf = zipfile.ZipFile(NE_DIR / "SR_HR.zip")
    tif = next(n for n in zf.namelist() if n.lower().endswith(".tif"))
    x0, y0, x1, y1 = drb.total_bounds
    res = 400.0
    w, h = int((x1 - x0) / res) + 1, int((y1 - y0) / res) + 1
    dst_tr = tfb(x0, y0, x0 + w * res, y0 + h * res, w, h)
    with rasterio.MemoryFile(zf.read(tif)) as mem, mem.open() as src:
        win = from_bounds(*MAP_BOUNDS_4326, transform=src.transform)
        arr = src.read(1, window=win).astype("float32")
        out = np.full((h, w), np.nan, dtype="float32")
        reproject(arr, out, src_transform=src.window_transform(win), src_crs=src.crs, dst_transform=dst_tr,
                  dst_crs=AEA, resampling=Resampling.bilinear, dst_nodata=np.nan)
    mask = geometry_mask(list(drb.geometry), out_shape=out.shape, transform=dst_tr, invert=True)
    out[~mask] = np.nan
    ext = (x0, x0 + w * res, y0, y0 + h * res)
    np.savez_compressed(RELIEF_AEA, relief=out, extent=np.array(ext))
    return out, ext


# ------------------------------------------------------------------------------------------------ drawing
def plant_area(mgd):
    return np.clip(np.asarray(mgd, float), 0.3, None) * PLANT_AREA_PER_MGD


def shared_state_borders(states):
    segs = []
    geoms = list(states.geometry)
    for a, b in combinations(geoms, 2):
        if a.buffer(50).intersects(b):
            seg = a.boundary.intersection(b.buffer(60))
            if not seg.is_empty:
                segs.append(seg)
    return gpd.GeoSeries(segs, crs=AEA)


def draw_base(ax, D, ext, relief, rext, relief_strength=0.10, rivers_lw=S.FIG_LW_SECONDARY):
    ax.set_xlim(ext[0], ext[2]); ax.set_ylim(ext[1], ext[3]); ax.set_aspect("equal")
    ax.set_facecolor(S.FIG_WATER)                                      # ocean and bay
    frame = box(*ext)
    land = D["states"].clip(frame)
    land.plot(ax=ax, color=S.FIG_OUTSIDE, lw=0, zorder=1)
    D["drb"].plot(ax=ax, color="white", lw=0, zorder=2)
    if relief is not None:
        v = relief
        lo, hi = np.nanpercentile(v, 2), np.nanpercentile(v, 98)
        shade = np.clip((v - lo) / (hi - lo), 0, 1)
        rgba = np.zeros(v.shape + (4,), dtype="float32")
        rgba[..., 3] = np.where(np.isnan(v), 0.0, relief_strength * (1 - shade))
        ax.imshow(rgba, extent=rext, origin="upper", interpolation="bilinear", zorder=3)
    D["counties"].clip(frame).boundary.plot(ax=ax, color=S.FIG_GRAY_LIGHT, lw=S.FIG_LW_TERTIARY, zorder=4)
    borders = shared_state_borders(D["states"]).clip(frame)
    if not borders.empty:  # the Falls/Plymouth detail frame contains no state border
        borders.plot(ax=ax, color=S.FIG_GRAY_DARK, lw=S.FIG_LW_SECONDARY, linestyle=S.FIG_DASH, zorder=5)
    D["water"].clip(frame).plot(ax=ax, color=S.FIG_WATER, lw=0, zorder=6)
    D["rivers"].clip(frame).plot(ax=ax, color=S.FIG_WATER, lw=rivers_lw, zorder=6)
    D["drb"].boundary.plot(ax=ax, color=S.FIG_BLACK, lw=S.FIG_LW_PRIMARY, zorder=7)
    for sp in ax.spines.values():
        sp.set_linewidth(S.FIG_LW_SECONDARY); sp.set_color(S.FIG_BLACK); sp.set_zorder(30)
    ax.set_xticks([]); ax.set_yticks([])


def draw_features(ax, D, radii=True):
    s = D["sites"]
    if radii:
        for g in s.geometry:
            ax.add_patch(Circle((g.x, g.y), 16093.44, fill=False, ec=S.FIG_GRAY, lw=S.FIG_LW_TERTIARY,
                                linestyle=S.FIG_DASH, zorder=8))
    p = D["plants"]
    ax.scatter(p.geometry.x, p.geometry.y, s=plant_area(p.median_flow_mgd), facecolors="none",
               edgecolors=S.FIG_BLACK, linewidths=S.FIG_LW_TERTIARY * 2, zorder=9)
    for unv, ls in ((False, "solid"), (True, S.FIG_DASH)):
        q = s[s.unverified.astype(bool) == unv]
        if len(q):
            ax.scatter(q.geometry.x, q.geometry.y, s=SITE_S, marker="s", c=[S.FIG_FILL[b] for b in q.covered_it_bin],
                       edgecolors=S.FIG_BLACK, linewidths=S.FIG_LW_PRIMARY, linestyles=[ls], zorder=10)


def edge_ticks(ax, ext, step_deg, label_edges=("bottom", "left"), tick_len_pt=3.0):
    """Graticule ticks on the neat line only (no interior gridlines), at every `step_deg` degrees."""
    x0, y0, x1, y1 = ext
    lon0, lat0 = TO_LL.transform(x0, y0); lon1, lat1 = TO_LL.transform(x1, y1)
    lons = np.arange(np.floor(min(lon0, lon1) / step_deg) * step_deg - step_deg, max(lon0, lon1) + 2 * step_deg, step_deg)
    lats = np.arange(np.floor(min(lat0, lat1) / step_deg) * step_deg - step_deg, max(lat0, lat1) + 2 * step_deg, step_deg)
    fig = ax.figure
    k = tick_len_pt / 72 * fig.dpi
    def fmt(v, hemi):
        d = int(np.floor(abs(v) + 1e-9)); m = int(round((abs(v) - d) * 60))
        if m == 60:
            d, m = d + 1, 0
        return f"{d}\u00b0{m:02d}'{hemi}" if m else f"{d}\u00b0{hemi}"
    out = []
    for lon in lons:
        for edge, y in (("bottom", y0), ("top", y1)):
            try:
                la = brentq(lambda la: TO_AEA.transform(lon, la)[1] - y, 20, 60)
            except ValueError:
                continue
            x = TO_AEA.transform(lon, la)[0]
            if x0 < x < x1:
                fx = (x - x0) / (x1 - x0); sgn = 1 if edge == "bottom" else -1
                fy = 0 if edge == "bottom" else 1
                ax.plot([fx, fx], [fy, fy + sgn * k / ax.bbox.height], transform=ax.transAxes, color=S.FIG_BLACK,
                        lw=S.FIG_LW_SECONDARY, clip_on=False, zorder=31)
                if edge in label_edges and 0.04 < fx < 0.96:
                    out.append(ax.annotate(fmt(lon, "W" if lon < 0 else "E"), (fx, 0), xycoords="axes fraction",
                                           xytext=(0, -2), textcoords="offset points", ha="center", va="top",
                                           fontsize=S.FIG_FONT_SIZE))
    for lat in lats:
        for edge, x in (("left", x0), ("right", x1)):
            try:
                lo = brentq(lambda lo: TO_AEA.transform(lo, lat)[0] - x, -90, -60)
            except ValueError:
                continue
            y = TO_AEA.transform(lo, lat)[1]
            if y0 < y < y1:
                fy = (y - y0) / (y1 - y0); sgn = 1 if edge == "left" else -1
                fx = 0 if edge == "left" else 1
                ax.plot([fx, fx + sgn * k / ax.bbox.width], [fy, fy], transform=ax.transAxes, color=S.FIG_BLACK,
                        lw=S.FIG_LW_SECONDARY, clip_on=False, zorder=31)
                if edge in label_edges and 0.04 < fy < 0.96:
                    out.append(ax.annotate(fmt(lat, "N"), (0, fy), xycoords="axes fraction", xytext=(-2, 0),
                                           textcoords="offset points", ha="center", va="bottom",
                                           fontsize=S.FIG_FONT_SIZE, rotation=90, rotation_mode="anchor"))
    return out


def scale_bar_axes(fig, rect_fig, m_per_mm, km_total, km_step, mi_total, mi_step, bar_mm=1.0, with_north=False):
    """Scale bar in its own transparent axes (x and y in millimeters): kilometers with labels above, miles with
    labels below, alternating black and white segments; optional north arrow to the left."""
    sa = fig.add_axes(rect_fig)
    w_mm = rect_fig[2] * fig.get_size_inches()[0] * 25.4
    h_mm = rect_fig[3] * fig.get_size_inches()[1] * 25.4
    sa.set_xlim(0, w_mm); sa.set_ylim(0, h_mm); sa.set_axis_off(); sa.patch.set_alpha(0)
    x0 = 7.0 if with_north else 1.5
    ymid = h_mm / 2
    arts = []
    rows = ((km_total, km_step, "KILOMETERS", 1000.0, ymid + 0.35, "bottom"),
            (mi_total, mi_step, "MILES", 1609.344, ymid - 0.35 - bar_mm, "top"))
    ends = []
    for tot, step, unit, conv, yy, va in rows:
        n = int(round(tot / step)); seg = step * conv / m_per_mm
        for i in range(n):
            sa.add_patch(Rectangle((x0 + i * seg, yy), seg, bar_mm, fc=S.FIG_BLACK if i % 2 == 0 else "white",
                                   ec=S.FIG_BLACK, lw=S.FIG_LW_TERTIARY * 2, clip_on=False))
        ty = yy + bar_mm + 0.5 if va == "bottom" else yy - 0.5
        for i in range(n + 1):
            arts.append(sa.text(x0 + i * seg, ty, f"{i * step:g}", ha="center", va=va, fontsize=S.FIG_FONT_SIZE))
        ends.append((x0 + n * seg, unit, ty, va))
    xe = max(e[0] for e in ends) + 3.5
    for _, unit, ty, va in ends:
        arts.append(sa.text(xe, ty, unit, ha="left", va=va, fontsize=S.FIG_FONT_SIZE))
    if with_north:
        sa.annotate("", xy=(2.5, h_mm - 3.0), xytext=(2.5, 1.0),
                    arrowprops=dict(arrowstyle="-|>,head_width=0.22,head_length=0.5", lw=S.FIG_LW_SECONDARY,
                                    color=S.FIG_BLACK, shrinkA=0, shrinkB=0))
        arts.append(sa.text(2.5, h_mm - 2.6, "N", ha="center", va="bottom", fontsize=S.FIG_FONT_SIZE))
    return sa, arts


def _tbb(t, r):
    if isinstance(t, mtext.Annotation):
        t.update_positions(r)
    return mtext.Text.get_window_extent(t, r)


DETAIL_LABEL_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.75, 0.75), (-0.75, 0.75), (0.75, -0.75),
                     (-0.75, -0.75), (1, 0.45), (-1, 0.45), (1, -0.45), (-1, -0.45)]
RADII = [4.6, 6.0, 7.8, 10.5, 14.0, 18.0, 23.0]
LEADER_FROM = 7.8


def place_numbers(ax, pts, texts, hard_boxes, symbols, color=S.FIG_BLACK, size=S.FIG_FONT_SIZE, radii=RADII,
                  leader_from=LEADER_FROM):
    """Place short labels next to points. Hard constraints: inside axes; no overlap with other labels or hard
    boxes; no overlap with any site square. Plant circles are soft (minimized). Leader lines only when the
    label must sit beyond `leader_from` points."""
    fig = ax.figure
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    k = fig.dpi / 72
    axbb = ax.get_window_extent(r)
    placed = list(hard_boxes)
    out, report = [], []
    sq = [(x, y, rad * k, kind) for (x, y, rad, kind) in symbols]
    for (x, y), txt in zip(pts, texts):
        pxy = ax.transData.transform((x, y))
        best, best_score = None, None
        for ri, rr in enumerate(radii):
            for di, (ux, uy) in enumerate(DETAIL_LABEL_DIRS):
                dx, dy = ux * rr, uy * rr
                ha = "left" if ux > 0.3 else ("right" if ux < -0.3 else "center")
                va = "bottom" if uy > 0.3 else ("top" if uy < -0.3 else "center")
                lead = rr >= leader_from
                t = ax.annotate(txt, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                                fontsize=size, color=color, zorder=26,
                                arrowprops=(dict(arrowstyle="-", lw=S.FIG_LW_TERTIARY, color=S.FIG_BLACK, shrinkA=0.5,
                                                 shrinkB=SITE_MS_PT / 2 + 0.5) if lead else None))
                bb = _tbb(t, r)
                inside = axbb.x0 <= bb.x0 and bb.x1 <= axbb.x1 and axbb.y0 <= bb.y0 and bb.y1 <= axbb.y1
                n_lab = sum(bb.overlaps(pb) for pb in placed)
                n_sq = n_pl = 0
                for sx, sy, rad, kind in sq:
                    if abs(sx - pxy[0]) < 0.5 and abs(sy - pxy[1]) < 0.5:
                        if kind == "site":
                            rad_own = rad
                            if bb.x0 - rad_own * 0.2 < sx < bb.x1 + rad_own * 0.2 and bb.y0 - rad_own * 0.2 < sy < bb.y1 + rad_own * 0.2:
                                n_sq += 1
                        continue
                    hit = bb.x0 - rad < sx < bb.x1 + rad and bb.y0 - rad < sy < bb.y1 + rad
                    if hit:
                        if kind == "site":
                            n_sq += 1
                        else:
                            n_pl += 1
                score = (not inside, n_lab, n_sq, n_pl, lead, ri, di)
                if best_score is None or score < best_score:
                    if best is not None:
                        best.remove()
                    best, best_score = t, score
                else:
                    t.remove()
                if score[:5] == (False, 0, 0, 0, False):
                    break
            if best_score[:5] == (False, 0, 0, 0, False):
                break
        placed.append(_tbb(best, r))
        out.append(best)
        report.append({"label": txt, "outside_axes": bool(best_score[0]), "label_overlaps": int(best_score[1]),
                       "square_overlaps": int(best_score[2]), "plant_circle_overlaps": int(best_score[3]),
                       "leader": bool(best_score[4])})
    return out, report


def text_overlaps(fig):
    """All pairwise overlaps between visible, non-empty text objects in the figure (display coordinates)."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    ts = [t for t in fig.findobj(mtext.Text) if t.get_visible() and t.get_text().strip()]
    boxes = [(t.get_text(), _tbb(t, r).shrunk(0.98, 0.9)) for t in ts]
    fb = fig.bbox
    out = [(a, b) for (a, ba), (b, bb) in combinations(boxes, 2) if ba.overlaps(bb)]
    out += [(a, "FIGURE EDGE") for a, ba in boxes
            if ba.x0 < fb.x0 - 0.5 or ba.x1 > fb.x1 + 0.5 or ba.y0 < fb.y0 - 0.5 or ba.y1 > fb.y1 + 0.5]
    return out


def symbols_px(ax, D):
    T = ax.transData
    out = [(*T.transform((g.x, g.y)), SITE_MS_PT / 2 + 0.6, "site") for g in D["sites"].geometry]
    for g, a in zip(D["plants"].geometry, plant_area(D["plants"].median_flow_mgd)):
        out.append((*T.transform((g.x, g.y)), np.sqrt(a) / 2, "plant"))
    return out


# ------------------------------------------------------------------------------------------------ bar
def bar_counts(ss):
    rows = []
    for b in S.FIG_BIN_ORDER:
        sub = ss[ss.covered_it_bin == b]
        rows.append({"covered_it_class": b, "fill": S.FIG_FILL[b], "n_sites": len(sub),
                     "n_verified": int((~sub.unverified.astype(bool)).sum()),
                     "n_unverified": int(sub.unverified.astype(bool).sum())})
    return pd.DataFrame(rows)


def _hatch_rect(ax, x, w, y, h, dark):
    col = "white" if dark else S.FIG_BLACK
    ax.add_patch(Rectangle((x, y), w, h, fill=False, hatch=S.FIG_HATCH * 2, lw=0, ec=col, zorder=3))


def render_bar(D):
    S.figure_rc()
    ss = D["ss"]
    bc = bar_counts(ss)
    fig = plt.figure(figsize=(BAR_W_MM * MM, BAR_H_MM * MM), dpi=S.FIG_DPI)
    l_mm, r_mm = 3.0, 3.0
    ax = fig.add_axes([l_mm / BAR_W_MM, 18.2 / BAR_H_MM, (BAR_W_MM - l_mm - r_mm) / BAR_W_MM, 7.0 / BAR_H_MM])
    ax.set_xlim(0, len(ss)); ax.set_ylim(0, 1)
    y, h = 0.0, 0.52
    left = 0
    seg_rows = []
    for rr in bc.itertuples():
        dark = rr.covered_it_class == "over 200 MW"
        ax.add_patch(Rectangle((left, y), rr.n_sites, h, fc=rr.fill, ec=S.FIG_BLACK, lw=S.FIG_LW_SECONDARY, zorder=2))
        if rr.n_unverified:
            _hatch_rect(ax, left + rr.n_verified, rr.n_unverified, y, h, dark)
            ax.plot([left + rr.n_verified] * 2, [y, y + h], color=S.FIG_BLACK if not dark else "white",
                    lw=S.FIG_LW_TERTIARY, zorder=4)
        ax.text(left + rr.n_sites / 2, y + h + 0.1, f"{rr.n_sites}", ha="center", va="bottom", fontsize=S.FIG_FONT_SIZE)
        seg_rows.append({**rr._asdict(), "left": left, "right": left + rr.n_sites,
                         "hatch_from": left + rr.n_verified if rr.n_unverified else None,
                         "hatch_color": ("white" if dark else "black") if rr.n_unverified else None})
        left += rr.n_sites
    for s_ in ("top", "right", "left"):
        ax.spines[s_].set_visible(False)
    ax.spines["bottom"].set_linewidth(S.FIG_LW_SECONDARY)
    ax.set_yticks([]); ax.set_xticks([0, 6, 12, 18, 24])
    ax.tick_params(axis="x", length=2.0, width=S.FIG_LW_SECONDARY, pad=1.2)
    ax.set_xlabel("Active planned sites (count)", labelpad=1.5)
    # key below the axis: swatches laid out by measured text width; wraps to a second row if needed
    W = BAR_W_MM - l_mm - r_mm
    kx = fig.add_axes([l_mm / BAR_W_MM, 3.6 / BAR_H_MM, W / BAR_W_MM, 7.0 / BAR_H_MM])
    kx.set_axis_off(); kx.set_xlim(0, W); kx.set_ylim(0, 7.0)
    items = [("Over 200 MW", S.FIG_FILL["over 200 MW"], False), ("50 to 200 MW", S.FIG_FILL["50 to 200 MW"], False),
             ("No eligible plant within 10 mi", S.FIG_FILL["no eligible plant within 10 mi"], False), ("Unverified", "white", True)]
    fig.canvas.draw(); rend = fig.canvas.get_renderer()
    px_per_mm = fig.dpi / 25.4
    x, row = 0.0, 0
    for lab, fc, hatch in items:
        t = kx.text(0, 0, lab, fontsize=S.FIG_FONT_SIZE, va="center")
        tw = t.get_window_extent(rend).width / px_per_mm
        t.remove()
        if x + 4.2 + tw > W and x > 0:
            x, row = 0.0, row + 1
        yc = 5.2 - row * 3.6
        kx.add_patch(Rectangle((x, yc - 1.15), 3.2, 2.3, fc=fc, ec=S.FIG_BLACK, lw=S.FIG_LW_SECONDARY))
        if hatch:
            kx.add_patch(Rectangle((x, yc - 1.15), 3.2, 2.3, fill=False, hatch=S.FIG_HATCH * 2, lw=0, ec=S.FIG_BLACK))
        kx.text(x + 4.2, yc, lab, va="center", fontsize=S.FIG_FONT_SIZE)
        x += 4.2 + tw + 3.0
    S.figure_source_line(fig, BAR_SOURCES, y_mm=0.5, x_mm=l_mm)
    overlaps = text_overlaps(fig)
    stem = FIGURES / "supply_screen_bar"
    for ext_ in ("png", "pdf", "svg"):
        fig.savefig(f"{stem}.{ext_}", dpi=S.FIG_DPI)
    pd.DataFrame(seg_rows).drop(columns=["Index"]).to_csv(f"{stem}_data.csv", index=False)
    plt.close(fig)
    return {"text_overlaps": overlaps, "counts": bc.to_dict("records")}


# ------------------------------------------------------------------------------------------------ detail
def render_detail(D):
    S.figure_rc()
    ss = D["ss"].set_index("site_id")
    fig = plt.figure(figsize=(DET_W_MM * MM, DET_H_MM * MM), dpi=S.FIG_DPI)
    gap, l_mm, b_mm = 9.0, 8.0, 12.0
    pw = (DET_W_MM - l_mm - 2.0 - gap) / 2
    ph = DET_H_MM - b_mm - 7.0
    panels = [("A", "DRB12", 12.0, 0.1, (5, 1, 3, 1)), ("B", "DRB31", 6.5, 0.05, (2, 1, 1, 1))]
    reports, rows = {}, []
    s_all = D["sites"].set_index("site_id")
    for i, (tag, sid, half_km, step, sbar) in enumerate(panels):
        ax = fig.add_axes([(l_mm + i * (pw + gap)) / DET_W_MM, b_mm / DET_H_MM, pw / DET_W_MM, ph / DET_H_MM])
        g = s_all.loc[sid].geometry
        hx = half_km * 1000.0; hy = hx * ph / pw
        ext = (g.x - hx, g.y - hy, g.x + hx, g.y + hy)
        relief, rext = build_relief_aea(ext, D["drb"])
        draw_base(ax, D, ext, relief, rext, relief_strength=0.06, rivers_lw=S.FIG_LW_PRIMARY)
        draw_features(ax, D)
        ticks = edge_ticks(ax, ext, step)
        mpm = 2 * hx / pw
        axl = (l_mm + i * (pw + gap))
        sa, sb = scale_bar_axes(fig, [(axl + pw - 44.0) / DET_W_MM, (b_mm + 2.0) / DET_H_MM, 42.0 / DET_W_MM,
                                      11.0 / DET_H_MM], mpm, *sbar, bar_mm=0.9)
        sa.patch.set_alpha(1.0); sa.patch.set_facecolor("white"); sa.set_axis_on(); sa.set_xticks([]); sa.set_yticks([])
        for sp in sa.spines.values():
            sp.set_linewidth(S.FIG_LW_TERTIARY)
        ax.text(0.0, 1.0, tag, transform=ax.transAxes, ha="left", va="bottom", fontsize=S.FIG_FONT_SIZE + 1)
        fig.canvas.draw(); r = fig.canvas.get_renderer()
        hard = [_tbb(t, r) for t in ticks] + [sa.get_window_extent(r)]
        sym = symbols_px(ax, D)
        r_ = ss.loc[sid]
        pl = D["plants"].set_index("npdes_id")
        ids = [r_.plant_npdes_id] + ([r_.same_state_npdes_id] if isinstance(r_.same_state_npdes_id, str)
                                     and r_.same_state_npdes_id != r_.plant_npdes_id else [])
        in_frame = [n for n in ids if ext[0] < pl.loc[n].geometry.x < ext[2] and ext[1] < pl.loc[n].geometry.y < ext[3]]
        short = {n: pl.loc[n]["name"].title().replace("Stp", "STP").replace("Borough", "Boro.") for n in in_frame}
        plabs, prep = place_numbers(ax, [(pl.loc[n].geometry.x, pl.loc[n].geometry.y) for n in in_frame],
                                    [short[n] for n in in_frame], hard, sym, color=S.FIG_GRAY_DARK,
                                    radii=[5.0, 7.0, 9.5, 13.0, 17.0], leader_from=9.5)
        vis = [(q.geometry.x, q.geometry.y, str(q.number)) for q in D["sites"].itertuples()
               if ext[0] < q.geometry.x < ext[2] and ext[1] < q.geometry.y < ext[3]]
        nlabs, nrep = place_numbers(ax, [(a, b) for a, b, _ in vis], [t for _, _, t in vis],
                                    hard + [_tbb(t, r) for t in plabs], sym)
        reports[tag] = {"plant_labels": prep, "site_labels": nrep}
        for n in in_frame:
            rows.append({"panel": tag, "element": "municipal_plant", "id": n, "name": pl.loc[n]["name"],
                         "median_flow_mgd": pl.loc[n].median_flow_mgd})
        for a, b, t in vis:
            rows.append({"panel": tag, "element": "planned_site", "id": t, "name": D["ss"].set_index("number").loc[int(t)]["name"]})
    S.figure_source_line(fig, DET_SOURCES, y_mm=1.8, x_mm=l_mm)
    overlaps = text_overlaps(fig)
    stem = FIGURES / "falls_plymouth_detail"
    for ext_ in ("png", "pdf", "svg"):
        fig.savefig(f"{stem}.{ext_}", dpi=S.FIG_DPI)
    pd.DataFrame(rows).to_csv(f"{stem}_data.csv", index=False)
    plt.close(fig)
    return {"text_overlaps": overlaps, **reports}


# ------------------------------------------------------------------------------------------------ captions
def _fmt_mw(v):
    return "" if pd.isna(v) else f"{v:,.0f}"


def map_caption_base(D, key):
    """Caption text of the supply-screen map before the map-specific sentences are added."""
    ss, summ = D["ss"], D["summ"]
    hi, bins = summ["headline_capacity_independent"], summ["covered_it_bins"]
    n = hi["of"]; n_ge50 = bins["50 to 200 MW"] + bins["over 200 MW"]
    n_unv = int(ss.unverified.astype(bool).sum())
    per_mw = float(ss.peak_day_gpd.iloc[0] / ss.it_mw.iloc[0])
    table = ["| No. | Site | Municipality | Stated capacity (MW) | IT load covered (MW) | Verified |",
             "|---:|:--|:--|---:|---:|:-:|"]
    for r in key.itertuples():
        # the source lists multi-municipality sites with "; " (site_key.csv keeps that form). Captions carry no
        # semicolons, so the table joins the same names with " and ".
        muni = str(r.municipality).replace("; ", " and ")
        table.append(f"| {r.number} | {r.name} | {muni} | {_fmt_mw(r.stated_mw) or 'not published'} | "
                     f"{r.covered_it_mw:,.0f} | {r.verified} |")
    m = "\n".join([
        "# Figure 1 (supply_screen_map)", "",
        f"**Figure 1.** The map shows the {n} active planned data center sites in the Delaware River Basin and the "
        f"municipal wastewater treatment plants whose effluent could supply their cooling water. Each site is shaded by "
        f"the largest information technology (IT) load whose modeled peak-day cooling makeup the median effluent flow "
        f"of the nearest eligible municipal plant within 10 miles could cover. {n_ge50} of {n} sites have such a plant "
        f"able to cover at least 50 megawatts (MW) of IT load. Of these, {bins['over 200 MW']} sites fall over 200 MW "
        f"(solid) and {bins['50 to 200 MW']} sites fall between 50 and 200 MW (half-tone). The remaining "
        f"{bins['no eligible plant within 10 mi']} sites (open) have no eligible plant within 10 miles. Dashed "
        f"outlines mark the {n_unv} sites held as unverified because the location is approximate or uncertain or "
        f"the cited source is unconfirmed. Circle area is proportional to the median monthly effluent flow reported from July 2023 to "
        f"June 2026 [epa_echo]. Dashed gray circles are 10-mile radii around each site. Numbers identify sites in the "
        f"key below.", "",
        f"Demand is the calibrated hybrid cooling model at {per_mw:,.0f} gallons per day of peak-day makeup per MW of "
        f"IT load, driven by hourly Trenton weather for 2005 to 2024 [noaa_isd, stull_2011]. The model is calibrated "
        f"to the reported Falls Township average cooling demand of 135,000 gallons per day and peak of 4.4 million "
        f"gallons per day [falls_levittown_2026]. These rates are model-derived. Covered IT load does not depend on "
        f"each site's own capacity, which {hi['n_no_published_capacity']} of {n} sites do not publish. Eligible "
        f"plants are municipal major dischargers with at least 12 months of flow reports. Industrial dischargers are "
        f"excluded. The basin boundary is the union of hydrologic units 020401 and 020402 [usgs_wbd]. Rivers, "
        f"reservoirs and Delaware Bay are from NHDPlus High Resolution [usgs_nhdplus_hr]. State and county lines are "
        f"the Census cartographic boundary files, and city locations are TIGERweb place interior points "
        f"[census_tiger]. Relief is Natural Earth shaded relief [natural_earth]. Site locations and sources are from "
        f"the Data Center Proposal Tracker [trackdatacenters_2026]. The source line credits DRBC for the basin "
        f"framing and review thresholds [drbc_admin_manual]. The projection is Albers "
        f"equal-area conic on the North American Datum of 1983. Its standard parallels are 39 and 42 degrees north, "
        f"and its central meridian is 75.3 degrees west.", "",
        "**Site key**", "",
        "The site key is also in figures/site_key.csv. Stated capacity is campus power as published. IT load covered "
        "is the model value described above.", ""] + table + ["",
        "The citation keys are epa_echo, noaa_isd, stull_2011, falls_levittown_2026, usgs_wbd, usgs_nhdplus_hr, "
        "census_tiger, natural_earth, trackdatacenters_2026 and drbc_admin_manual.", ""])
    return m


def write_captions(D):
    """Captions of the bar chart and the Falls/Plymouth detail maps."""
    ss, summ = D["ss"], D["summ"]
    n, bins = summ["headline_capacity_independent"]["of"], summ["covered_it_bins"]
    n_unv = int(ss.unverified.astype(bool).sum())
    per_mw = float(ss.peak_day_gpd.iloc[0] / ss.it_mw.iloc[0])
    f = ss.set_index("site_id").loc["DRB12"]; p = ss.set_index("site_id").loc["DRB31"]
    bc = bar_counts(ss)
    b = "\n".join([
        "# Figure 2 (supply_screen_bar)", "",
        f"**Figure 2.** The bar chart divides the {n} active planned data center sites in the Delaware River Basin "
        f"[trackdatacenters_2026] by the largest IT load whose modeled peak-day cooling makeup the nearest "
        f"eligible municipal plant within 10 miles could cover [epa_echo]. {bins['over 200 MW']} sites fall over "
        f"200 MW (solid), {bins['50 to 200 MW']} between 50 and 200 MW (half-tone), and "
        f"{bins['no eligible plant within 10 mi']} with no eligible plant within 10 miles (open). Fills and counts "
        f"are identical to figure 1. Diagonal hatching marks the {n_unv} sites with an unverified location or "
        f"source. The hatch is drawn in white on the solid segment so that it remains visible. The demand rate is "
        f"the model value of figure 1 ({per_mw:,.0f} gallons per day per MW of IT load on the peak day) "
        f"[noaa_isd, falls_levittown_2026].", "",
        "| Class | Sites | Verified | Unverified |", "|:--|---:|---:|---:|"] +
        [f"| {r.covered_it_class} | {r.n_sites} | {r.n_verified} | {r.n_unverified} |" for r in bc.itertuples()] + ["",
        "The citation keys are trackdatacenters_2026, epa_echo, noaa_isd and falls_levittown_2026.", ""])
    (FIGURES / "supply_screen_bar_caption.md").write_text(b)
    num = ss.set_index("site_id")["number"]
    d = "\n".join([
        "# Figure A1 (falls_plymouth_detail)", "",
        f"**Figure A1.** The maps show two planned data center sites and the municipal treatment plants nearest to "
        f"them. Panel A covers Lower Bucks County, Pennsylvania. Site {num['DRB12']} (AWS Keystone Trade Center, "
        f"Falls Township) is matched to the Trenton Sewer Utility in New Jersey, {f.distance_mi:.3g} miles away. "
        f"That plant's median flow of {f.plant_median_flow_mgd:.3g} million gallons per day covers "
        f"{f.covered_it_mw:,.0f} MW of IT load. The nearest eligible Pennsylvania plant, the Morrisville Borough "
        f"STP, is {f.same_state_distance_mi:.3g} miles away. Its flow of {f.same_state_median_flow_mgd:.3g} million "
        f"gallons per day covers {f.same_state_covered_it_mw:,.0f} MW. Panel B covers Conshohocken, Plymouth "
        f"Township, Pennsylvania. Site {num['DRB31']} is matched to the Matsunk STP, {p.distance_mi:.3g} miles "
        f"away, whose flow of {p.plant_median_flow_mgd:.3g} million gallons per day covers {p.covered_it_mw:,.0f} MW "
        f"[epa_echo, trackdatacenters_2026]. Symbols, model and projection are as in figure 1.", "",
        "The citation keys are epa_echo, trackdatacenters_2026, usgs_wbd, usgs_nhdplus_hr and census_tiger.", ""])
    (FIGURES / "falls_plymouth_detail_caption.md").write_text(d)

# ------------------------------------------------------------------------------------------------ map layout

MAP_W_MM = 180.0
OUTSIDE_ALPHA = 0.40
LABEL_PAD_PT = 1.0            # clearance around every label box
NUM_SIZE = S.FIG_FONT_SIZE     # site numbers, narrow face
CITY_SIZE = S.FIG_FONT_SIZE    # city labels, narrow face, gray
CITY_HALO = False             # brief map only: haloed city labels may cross thin plant outlines
CITY_RADII = [2.2, 3.2, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 14.0]
CITY_LEADER_FROM = 99.0       # city labels never get leaders on the full-size map
TXT_K = 1.0                   # multiplier on text-bound layout spacing (key rows, scale-bar rows); 1 at 180 mm
SCALE_ROWS = ((50, 10, "KILOMETERS", 1000.0), (30, 10, "MILES", 1609.344))
LEADER_LW = None              # None: styles.FIG_LW_TERTIARY; the brief map uses FIG_LW_SECONDARY x 120/180 so
                              # leaders stay visible at 120 mm (scaled tertiary, 0.17 pt, vanishes at 1:1)


# ------------------------------------------------------------------------------------------------ drawing
def draw_map_features(ax, D):
    s, p = D["sites"], D["plants"]
    for g in s.geometry:
        ax.add_patch(Circle((g.x, g.y), 16093.44, fill=False, ec=S.FIG_GRAY, lw=S.FIG_LW_TERTIARY,
                            linestyle=S.FIG_DASH, zorder=8))
    basin = D["drb"].geometry.union_all()
    inside = p.geometry.within(basin).to_numpy()
    for msk, alpha in ((~inside, OUTSIDE_ALPHA), (inside, 1.0)):
        q = p[msk]
        ax.scatter(q.geometry.x, q.geometry.y, s=plant_area(q.median_flow_mgd), facecolors="none",
                   edgecolors=S.FIG_BLACK, linewidths=S.FIG_LW_TERTIARY * 2, alpha=alpha, zorder=9)
    for unv, ls in ((False, "solid"), (True, S.FIG_DASH)):
        q = s[s.unverified.astype(bool) == unv]
        if len(q):
            ax.scatter(q.geometry.x, q.geometry.y, s=SITE_S, marker="s",
                       c=[S.FIG_FILL[b] for b in q.covered_it_bin], edgecolors=S.FIG_BLACK,
                       linewidths=S.FIG_LW_PRIMARY, linestyles=[ls], zorder=10)
    return inside


def map_scale_bar(fig, rect_fig, m_per_mm, rows=None, bar_mm=None, north=True):
    """Two stacked scale bars; numbers above each bar, the unit label centered below it; north arrow at left."""
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
            sa.add_patch(Rectangle((x0 + i * seg, yb), seg, bar_mm, fc=S.FIG_BLACK if i % 2 == 0 else "white",
                                   ec=S.FIG_BLACK, lw=S.FIG_LW_TERTIARY * 2, clip_on=False))
        for i in range(n + 1):
            arts.append(sa.text(x0 + i * seg, yb + bar_mm + 0.5 * k, f"{i * step:g}", ha="center", va="bottom",
                                fontsize=S.FIG_FONT_SIZE))
        arts.append(sa.text(x0 + n * seg / 2, yb - 0.6 * k, unit, ha="center", va="top", fontsize=S.FIG_FONT_SIZE))
    if north:
        sa.annotate("", xy=(3.0 * k, H - 4.2 * k), xytext=(3.0 * k, H - 13.2 * k),
                    arrowprops=dict(arrowstyle="-|>,head_width=0.22,head_length=0.5", lw=S.FIG_LW_SECONDARY,
                                    color=S.FIG_BLACK, shrinkA=0, shrinkB=0))
        arts.append(sa.text(3.0 * k, H - 3.8 * k, "N", ha="center", va="bottom", fontsize=S.FIG_FONT_SIZE))
    return sa, arts


def map_key(fig, ax, anchor_mm, aw, ah, l_mm, b_mm, m_per_mm):
    """Key in the lower-right corner. Swatches in one column, all text left-aligned, uniform row spacing."""
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    px_mm = fig.dpi / 25.4
    def tw(s, **kw):
        t = fig.text(0, 0, s, fontsize=S.FIG_FONT_SIZE, **kw); w = t.get_window_extent(r).width / px_mm; t.remove()
        return w
    k = TXT_K
    PAD, SW_X, TX, ROW, GAP = 2.4 * k, 5.0 * k, 9.6 * k, 3.9 * k, 1.6 * k
    items = [("head", "Key"), ("group", "Planned site, IT load coverable at peak (MW)")]
    items += [("site", "> 200", S.FIG_FILL["over 200 MW"], "solid"), ("site", "50 to 200", S.FIG_FILL["50 to 200 MW"], "solid"),
              ("site", "No eligible plant within 10 mi", S.FIG_FILL["no eligible plant within 10 mi"], "solid"), ("site", "Unverified", "#FFFFFF", "dashed")]
    items += [("gap",), ("group", "Treatment plant, median flow (MGD)")]
    items += [("plant", "5", 5), ("plant", "25", 25), ("plant", "100", 100)]
    items += [("gap",), ("radius", "10-mile radius"), ("line", "Basin boundary", S.FIG_BLACK, S.FIG_LW_PRIMARY, "solid"),
              ("line", "State boundary", S.FIG_GRAY_DARK, S.FIG_LW_SECONDARY, "dashed")]
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
            d = np.sqrt(plant_area(it[2])) / PT_PER_MM
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
        sp.set_linewidth(S.FIG_LW_SECONDARY)
    rows_out = []
    for it, yy in zip(items, ys):
        if yy is None:
            continue
        kind = it[0]
        if kind in ("head", "group"):
            lg.text(PAD, yy, it[1], fontsize=S.FIG_FONT_SIZE, va="center", ha="left",
                    weight="bold" if kind == "head" else "normal")
        elif kind == "site":
            lg.scatter([SW_X], [yy], s=SITE_S, marker="s", c=it[2], edgecolors=S.FIG_BLACK,
                       linewidths=S.FIG_LW_PRIMARY, linestyles=[S.FIG_DASH if it[3] == "dashed" else "solid"],
                       clip_on=False)
            lg.text(TX, yy, it[1], fontsize=S.FIG_FONT_SIZE, va="center", ha="left")
        elif kind == "plant":
            lg.scatter([SW_X], [yy], s=plant_area(it[2]), facecolors="none", edgecolors=S.FIG_BLACK,
                       linewidths=S.FIG_LW_TERTIARY * 2, clip_on=False)
            lg.text(TX, yy, it[1], fontsize=S.FIG_FONT_SIZE, va="center", ha="left")
        elif kind == "radius":
            lg.add_patch(Circle((SW_X, yy), 1.55 * k, fill=False, ec=S.FIG_GRAY, lw=S.FIG_LW_SECONDARY, linestyle=S.FIG_DASH))
            lg.text(TX, yy, it[1], fontsize=S.FIG_FONT_SIZE, va="center", ha="left")
        elif kind == "line":
            lg.plot([SW_X - 2.6 * k, SW_X + 2.6 * k], [yy, yy], color=it[2], lw=it[3],
                    linestyle=S.FIG_DASH if it[4] == "dashed" else "solid")
            lg.text(TX, yy, it[1], fontsize=S.FIG_FONT_SIZE, va="center", ha="left")
        rows_out.append({"kind": kind, "text": it[1], "y_mm": yy})
    fx = lambda xm: (l_mm + xm) / MAP_W_MM
    fig_h = fig.get_size_inches()[1] * 25.4
    sb_top_from_axes_top = y_top + h_mm - PAD - SB_H
    rect = [fx(x_mm + PAD - 1.0 * k), (b_mm + ah - sb_top_from_axes_top - SB_H) / fig_h, (w_mm - 2 * PAD) / MAP_W_MM,
            SB_H / fig_h]
    sa, sb = map_scale_bar(fig, rect, m_per_mm)
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
    sq_half = (SITE_MS_PT / 2 + S.FIG_LW_PRIMARY / 2) * k
    pl = np.array([T.transform((g.x, g.y)) for g in D["plants"].geometry])
    pl_rad = np.sqrt(plant_area(D["plants"].median_flow_mgd.to_numpy())) / 2 * k
    boundary = [g.boundary for g in D["drb"].geometry]
    borders = list(shared_state_borders(D["states"]).geometry)
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
    Distances run from the text center to the center of every site square (and city dot, when O includes them).
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


MAP_LABEL_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.75, 0.75), (-0.75, 0.75), (0.75, -0.75), (-0.75, -0.75),
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
            for di, (ux, uy) in enumerate(MAP_LABEL_DIRS):
                ha = "left" if ux > 0.3 else ("right" if ux < -0.3 else "center")
                va = "bottom" if uy > 0.3 else ("top" if uy < -0.3 else "center")
                lead = rr >= leader_from
                t = ax.annotate(txt, (x, y), xytext=(ux * rr, uy * rr), textcoords="offset points", ha=ha, va=va,
                                fontsize=size, color=color, family=family, zorder=26,
                                arrowprops=(dict(arrowstyle="-", lw=S.FIG_LW_TERTIARY if LEADER_LW is None else LEADER_LW,
                                                 color=S.FIG_BLACK, shrinkA=0.6,
                                                 shrinkB=SITE_MS_PT / 2 + 0.8) if lead else None))
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
            best._peakflow_plants_soft = True
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
    g = gpd.read_file(RAW / "gis" / f"nhd_{key}_river.geojson").to_crs(AEA)
    pts = []
    for geom in g.geometry:
        for ln in ([geom] if geom.geom_type == "LineString" else list(getattr(geom, "geoms", []))):
            c = np.asarray(ln.segmentize(500.0).coords)[:, :2]
            if len(c) < 3:
                continue
            lat = np.array([TO_LL.transform(*q)[1] for q in c])
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
                                color=S.FIG_GRAY_DARK, family=family, zorder=26)
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
        t._peakflow_rect = rect
        out.append(t)
        rep.append({"label": txt, "rotation_deg": round(ang, 1),
                    "anchor_lonlat": [round(v_, 4) for v_ in TO_LL.transform(*t.xy)],
                    "offset_pt": [round(v_, 1) for v_ in t.xyann]})
    return out, rep


def final_check(fig, ax, O, map_labels):
    """At export resolution: every pair of visible text boxes, plus each map label against site squares, plant
    circles and the basin/state lines. Returns lists of conflicts (empty lists mean clean)."""
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    ts = [t for t in fig.findobj(mtext.Text) if t.get_visible() and t.get_text().strip()]
    boxes = [(t, _tbb(t, r)) for t in ts]
    def _pair_overlap(a, ba, b, bb):
        ra, rb = getattr(a, "_peakflow_rect", None), getattr(b, "_peakflow_rect", None)
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
        if getattr(t, "_peakflow_rect", None) is not None:
            n_sq, n_pl, n_ln, _, _ = _rot_hits(_rot_rect(t, r), O, [])
            if n_sq or n_pl or n_ln:
                sym.append({"label": t.get_text(), "squares": n_sq, "plants": n_pl, "boundary_or_state_line": n_ln})
            continue
        bb = _tbb(t, r)
        own = ax.transData.transform(t.xy)
        n_sq, n_pli, n_plo, n_ln, _ = _hits(bb, O, own=own)
        if getattr(t, "arrow_patch", None) is not None:
            n_ln += _leader_line_hits(bb, own, O, ax.figure.dpi / 72)
        sqs = O["sq"]; h = O["sq_half"]
        own_sq = any(np.hypot(*(sqs - own).T) < 0.5)
        if own_sq and (bb.x0 - h < own[0] < bb.x1 + h and bb.y0 - h < own[1] < bb.y1 + h):
            n_sq -= 1
        if getattr(t, "_peakflow_plants_soft", False):
            halo.append({"label": t.get_text(), "plant_outlines": int(n_pli + n_plo)}) if (n_pli or n_plo) else None
            n_pli = n_plo = 0
        if n_sq > 0 or n_pli or n_plo or n_ln:
            sym.append({"label": t.get_text(), "squares": n_sq, "plants_inside": n_pli, "plants_outside": n_plo,
                        "boundary_or_state_line": n_ln})
    amb = []
    for t in map_labels:
        if t.get_text().isdigit() and t.arrow_patch is None:
            f, ratio = _ambiguous(_tbb(t, r), ax.transData.transform(t.xy), O)
            if f:
                amb.append({"label": t.get_text(), "other_to_own_distance_ratio": round(ratio, 2)})
    segs = [(t, _leader_seg(_tbb(t, r), ax.transData.transform(t.xy))) for t in map_labels
            if getattr(t, "arrow_patch", None) is not None]
    lx = []
    for (ta, sa_), (tb_, sb_) in combinations(segs, 2):
        if _segs_cross(*sa_, *sb_):
            lx.append([ta.get_text(), tb_.get_text()])
    for ta, (p, q) in segs:
        for t in map_labels:
            if t is not ta and _seg_box(p, q, _tbb(t, r)):
                lx.append([ta.get_text() + " leader", t.get_text()])
    out = {"text_text": tt, "text_outside_figure": edge, "label_symbol_or_line": sym, "site_number_ambiguous": amb,
           "leader_crossings": lx}
    if halo:
        out["haloed_city_label_over_plant_outline"] = halo   # permitted on the brief map and reported
    return out


# ------------------------------------------------------------------------------------------------ map
def render_map(D, stem_name="supply_screen_map", map_h_mm=222.0, margins_mm=(8.0, 2.0, 11.0, 2.0),
                  sources=None, source_y_mm=1.8, rivers_lw=None):
    S.figure_rc()
    fam = S.register_fonts(); narrow = S.narrow_family()
    fig = plt.figure(figsize=(MAP_W_MM * MM, map_h_mm * MM), dpi=S.FIG_DPI)
    l_mm, r_mm, b_mm, t_mm = margins_mm
    aw, ah = MAP_W_MM - l_mm - r_mm, map_h_mm - b_mm - t_mm
    ax = fig.add_axes([l_mm / MAP_W_MM, b_mm / map_h_mm, aw / MAP_W_MM, ah / map_h_mm])
    x0, y0, x1, y1 = D["drb"].total_bounds
    pad = 3500.0
    hgt = (y1 - y0) + 2 * pad
    wid = hgt * aw / ah
    xl = x0 - pad - 8000.0
    ext = (xl, y0 - pad, xl + wid, y1 + pad)
    relief, rext = build_relief_aea(ext, D["drb"])
    draw_base(ax, D, ext, relief, rext, rivers_lw=S.FIG_LW_SECONDARY if rivers_lw is None else rivers_lw)
    inside = draw_map_features(ax, D)
    tick_txt = edge_ticks(ax, ext, 0.5)
    m_per_mm = wid / aw
    lg, sa, sb, lg_info = map_key(fig, ax, 2.5 * TXT_K, aw, ah, l_mm, b_mm, m_per_mm)
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    O = obstacles(ax, D, inside)
    hard = [_tbb(t, r) for t in tick_txt] + [lg.get_window_extent(r)]
    c = D["cities"]
    ax.scatter(c.geometry.x, c.geometry.y, s=4, c=S.FIG_GRAY_DARK, lw=0, zorder=11)
    city_labels, city_rep = place(ax, [(g.x, g.y) for g in c.geometry], list(c["name"]), hard, O, narrow,
                                  S.FIG_GRAY_DARK, CITY_SIZE, radii=CITY_RADII, leader_from=CITY_LEADER_FROM,
                                  own_is_site=False, dot_r_pt=1.3, plants_soft=CITY_HALO)
    hard2 = hard + [_tbb(t, r) for t in city_labels]
    # city dots are obstacles for site numbers
    O2 = dict(O); O2["sq"] = np.vstack([O["sq"], np.array([ax.transData.transform((g.x, g.y)) for g in c.geometry])])
    s = D["sites"]
    num_labels, num_rep = place(ax, [(g.x, g.y) for g in s.geometry], [str(n) for n in s.number], hard2, O2, narrow,
                                S.FIG_BLACK, NUM_SIZE, radii=[4.4, 5.6, 7.0, 8.6, 10.5, 13.0, 16.0, 20.0],
                                leader_from=8.6, own_is_site=True)
    hard3 = hard2 + [_tbb(t, r) for t in num_labels]
    river_labels, river_rep = label_rivers(ax, D, hard3, O2, narrow, CITY_SIZE)
    S.figure_source_line(fig, MAP_SOURCES if sources is None else sources, y_mm=source_y_mm, x_mm=l_mm)
    chk = final_check(fig, ax, O2, num_labels + city_labels + river_labels)
    stem = FIGURES / stem_name
    for e in ("png", "pdf", "svg"):
        fig.savefig(f"{stem}.{e}", dpi=S.FIG_DPI)
    rows = []
    for g, rr, t in zip(s.geometry, s.itertuples(), num_labels):
        rows.append({"element": "planned_site", "number": rr.number, "site_id": rr.site_id, "name": rr.name,
                     "lon": rr.lon, "lat": rr.lat, "x_aea_m": g.x, "y_aea_m": g.y, "covered_it_mw": rr.covered_it_mw,
                     "covered_it_class": rr.covered_it_bin, "fill": S.FIG_FILL[rr.covered_it_bin],
                     "outline": "dashed" if rr.unverified else "solid", "radius_mi": 10.0,
                     "label_dx_pt": t.xyann[0], "label_dy_pt": t.xyann[1], "leader": t.arrow_patch is not None})
    p = D["plants"]
    for g, rr, ins in zip(p.geometry, p.itertuples(), inside):
        rows.append({"element": "municipal_plant", "site_id": rr.npdes_id, "name": rr.name, "lon": rr.lon,
                     "lat": rr.lat, "x_aea_m": g.x, "y_aea_m": g.y, "median_flow_mgd": rr.median_flow_mgd,
                     "marker_area_pt2": float(plant_area(rr.median_flow_mgd)), "inside_basin": bool(ins),
                     "opacity": 1.0 if ins else OUTSIDE_ALPHA})
    for g, nm, t in zip(c.geometry, c["name"], city_labels):
        lon, lat = TO_LL.transform(g.x, g.y)
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


# Brief map: symbols and line weights scale by 120/180 (0.667); all text is 6.5 pt or larger. City labels carry
# a white halo there and may cross thin plant outlines, which the layout check reports without failing.
BRIEF_W_MM = 120.0
BRIEF_MIN_FONT_PT = 6.5


def render_brief(D):
    """Brief-size copy of the supply-screen map: same design and crop at 120 mm wide. Geometry (symbols, line weights,
    margins) scales by 120/180; text is set at max(7 x 120/180, 6.5) = 6.5 pt, and text-bound spacing (key rows,
    scale-bar rows) scales with the font. Module constants are patched for the duration of the call only."""
    global MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, SCALE_ROWS, CITY_LEADER_FROM, CITY_RADII, CITY_HALO, LEADER_LW
    global SITE_MS_PT, SITE_S, PLANT_AREA_PER_MGD
    k = BRIEF_W_MM / MAP_W_MM
    saved_leader = LEADER_LW
    LEADER_LW = S.FIG_LW_SECONDARY * k    # 0.33 pt, as the plant outlines; scaled tertiary (0.17 pt) is invisible
    font = max(S.FIG_FONT_SIZE * k, BRIEF_MIN_FONT_PT)
    fk = font / S.FIG_FONT_SIZE
    saved_S = {n: getattr(S, n) for n in ("FIG_FONT_SIZE", "FIG_LW_PRIMARY", "FIG_LW_SECONDARY", "FIG_LW_TERTIARY")}
    saved_sym = (SITE_MS_PT, SITE_S, PLANT_AREA_PER_MGD)
    saved_me = (MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, SCALE_ROWS, CITY_LEADER_FROM, CITY_RADII, CITY_HALO)
    try:
        S.FIG_FONT_SIZE = font
        for n in ("FIG_LW_PRIMARY", "FIG_LW_SECONDARY", "FIG_LW_TERTIARY"):
            setattr(S, n, saved_S[n] * k)
        SITE_MS_PT = saved_sym[0] * k
        SITE_S = SITE_MS_PT ** 2
        PLANT_AREA_PER_MGD = saved_sym[2] * k * k
        MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, CITY_LEADER_FROM = BRIEF_W_MM, font, font, fk, 7.5
        CITY_RADII = CITY_RADII + [16.0, 18.0]
        CITY_HALO = True
        SCALE_ROWS = ((50, 25, "KILOMETERS", 1000.0), (30, 10, "MILES", 1609.344))
        src = MAP_SOURCES.replace("NOAA ISD; ", "NOAA ISD;\n")
        info = render_map(D, stem_name="supply_screen_map_brief", map_h_mm=222.0 * k,
                         margins_mm=(8.0 * fk, 2.0 * k, 11.0 * fk + 2.6, 2.0 * k), sources=src,
                         source_y_mm=1.2, rivers_lw=saved_S["FIG_LW_SECONDARY"] * k)
    finally:
        for n, v in saved_S.items():
            setattr(S, n, v)
        SITE_MS_PT, SITE_S, PLANT_AREA_PER_MGD = saved_sym
        MAP_W_MM, NUM_SIZE, CITY_SIZE, TXT_K, SCALE_ROWS, CITY_LEADER_FROM, CITY_RADII, CITY_HALO = saved_me
        LEADER_LW = saved_leader
    info.update({"scale": k, "font_pt": font})
    return info


def write_map_caption(D, key):
    txt = map_caption_base(D, key)
    txt = txt.replace("Circle area is proportional to the median monthly effluent flow reported from July 2023 to "
                      "June 2026 [epa_echo].",
                      "Circle area is proportional to the median monthly effluent flow reported from July 2023 to "
                      "June 2026 [epa_echo], and plants outside the basin are drawn at 40 percent opacity so that "
                      "plants inside the basin read first. In the key, IT load coverable at peak is the largest IT "
                      "load, in megawatts, whose peak-day makeup the nearest eligible plant's median flow covers.")
    assert "40 percent opacity" in txt, "map caption template changed, so the plant-opacity sentence was not applied"
    (FIGURES / "supply_screen_map_caption.md").write_text(txt)
    return txt


def run():
    FIGURES.mkdir(exist_ok=True)
    D = load()
    key = site_key(D["ss"])
    rep = {"bar": render_bar(D), "detail": render_detail(D)}
    write_captions(D)
    rep["palette_check"] = S.cvd_check({"accent": S.FIG_ACCENT, "half": S.FIG_ACCENT_HALF, "open": "#FFFFFF",
                                        "water": S.FIG_WATER})
    (RESULTS / "supply_figures_report.json").write_text(json.dumps(rep, indent=1, default=str))
    info = render_map(D)
    cap = write_map_caption(D, key)
    # consistency with the bar chart: same fills and counts per class
    m = pd.read_csv(FIGURES / "supply_screen_map_data.csv")
    ms = m[m.element == "planned_site"].groupby(["covered_it_class", "fill"]).size().to_dict()
    bc = bar_counts(D["ss"])
    bs = {(r.covered_it_class, r.fill): int(r.n_sites) for r in bc.itertuples()}
    info["map_bar_identical"] = all(ms.get(k) == v for k, v in bs.items()) and sum(bs.values()) == len(D["ss"])
    (RESULTS / "supply_screen_map_report.json").write_text(json.dumps(info, indent=1, default=str))
    brief = render_brief(D)
    cap = cap.replace("# Figure 1 (supply_screen_map)", "# Figure 1, brief size (supply_screen_map_brief)")
    cap += (f"\n\nThe brief-size version has the same design and extent at {BRIEF_W_MM:.0f} mm wide. The kilometer "
            "scale bar is divided at 25 km. City labels displaced from their point carry a short leader line. Plotted "
            "values are in figures/supply_screen_map_brief_data.csv.\n")
    (FIGURES / "supply_screen_map_brief_caption.md").write_text(cap)
    (RESULTS / "supply_screen_map_brief_report.json").write_text(json.dumps(brief, indent=1, default=str))
    info["brief"] = {"check": brief["check"], "min_font_pt": brief["min_font_pt"], "leaders": brief["n_leaders"]}
    write_stem_checks(rep, info, brief)
    return {"bar": rep["bar"], "detail": rep["detail"], "palette_check": rep["palette_check"], "map": info}


def write_stem_checks(rep, info, brief):
    """One results/<stem>_check.json per figure, with the conflict lists and a pass flag."""
    per = {"supply_screen_bar": {"text_text_or_edge": rep["bar"]["text_overlaps"]},
           "falls_plymouth_detail": {"text_text_or_edge": rep["detail"]["text_overlaps"]}}
    for stem, chk in per.items():
        ok = not any(chk.values())
        (RESULTS / f"{stem}_check.json").write_text(json.dumps({"figure": f"figures/{stem}", "pass": ok, **chk},
                                                               indent=1, default=str))
    # Haloed city labels over plant outlines on the brief map are reported but permitted, so they do not fail.
    for stem, d, min_pt in (("supply_screen_map", info, S.FIG_FONT_SIZE), ("supply_screen_map_brief", brief,
                                                                            BRIEF_MIN_FONT_PT)):
        gate = {k: v for k, v in d["check"].items() if k != "haloed_city_label_over_plant_outline"}
        ok = not any(gate.values()) and d["min_font_pt"] >= min_pt - 1e-9
        (RESULTS / f"{stem}_check.json").write_text(json.dumps(
            {"figure": f"figures/{stem}", "pass": ok, "min_font_pt": d["min_font_pt"], "required_min_font_pt": min_pt,
             **d["check"]}, indent=1, default=str))


if __name__ == "__main__":
    r = run()
    i = r["map"]
    print(json.dumps({"bar_overlaps": r["bar"]["text_overlaps"], "detail_overlaps": r["detail"]["text_overlaps"],
                      "palette_min_dE": r["palette_check"], "map_fonts": i["fonts"], "map_check": i["check"],
                      "map_bar_identical": i["map_bar_identical"], "map_leaders": i["n_leaders"],
                      "plants_in_out": [i["n_plants_inside"], i["n_plants_outside"]]}, indent=1, default=str))
