"""V2 technical figures (style of a USGS Scientific Investigations Report).

Builds, from the latest results (results/supply_screen.csv, results/supply_summary.json, results/calibration.json):
  figures/supply_screen_map_v2.{png,pdf,svg}, _caption.md, _data.csv   single-panel map, 180 mm wide
  figures/supply_screen_bar_v2.{png,pdf,svg}, _caption.md, _data.csv   one-bar summary, 85 mm wide
  figures/falls_plymouth_detail_v2.{png,pdf,svg}, _caption.md, _data.csv  two-panel appendix detail
  figures/site_key.csv                                                 number -> site key for the map
  results/figures_v2_check.json                                        text-overlap and fill/count checks
No titles, sentences, citation keys or file paths inside images; explanation lives in the caption files.
Projection: Albers equal-area conic, NAD83, standard parallels 39 and 42 N, central meridian 75.3 W, so that
north is up at the basin and the scale bar is valid across the map.
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
MAP_W_MM, MAP_H_MM = 180.0, 228.0
BAR_W_MM, BAR_H_MM = 85.0, 30.0
DET_W_MM, DET_H_MM = 180.0, 96.0
SITE_MS_PT = 5.2                    # square side in points
SITE_S = SITE_MS_PT ** 2            # scatter area (pt^2) for marker "s"
PLANT_AREA_PER_MGD = 3.0            # pt^2 per MGD, area-proportional (same as v1)
CITIES_V2 = ["Philadelphia", "Trenton", "Wilmington", "Allentown", "Scranton"]
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
    cities = cities[cities["name"].isin(CITIES_V2)].to_crs(AEA)
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


def draw_base(ax, D, ext, relief, rext, relief_strength=0.10, rivers_lw=S.V2_LW_SECONDARY):
    ax.set_xlim(ext[0], ext[2]); ax.set_ylim(ext[1], ext[3]); ax.set_aspect("equal")
    ax.set_facecolor(S.V2_WATER)                                      # ocean and bay
    frame = box(*ext)
    land = D["states"].clip(frame)
    land.plot(ax=ax, color=S.V2_OUTSIDE, lw=0, zorder=1)
    D["drb"].plot(ax=ax, color="white", lw=0, zorder=2)
    if relief is not None:
        v = relief
        lo, hi = np.nanpercentile(v, 2), np.nanpercentile(v, 98)
        shade = np.clip((v - lo) / (hi - lo), 0, 1)
        rgba = np.zeros(v.shape + (4,), dtype="float32")
        rgba[..., 3] = np.where(np.isnan(v), 0.0, relief_strength * (1 - shade))
        ax.imshow(rgba, extent=rext, origin="upper", interpolation="bilinear", zorder=3)
    D["counties"].clip(frame).boundary.plot(ax=ax, color=S.V2_GRAY_LIGHT, lw=S.V2_LW_TERTIARY, zorder=4)
    borders = shared_state_borders(D["states"]).clip(frame)
    if not borders.empty:  # the Falls/Plymouth detail frame contains no state border
        borders.plot(ax=ax, color=S.V2_GRAY_DARK, lw=S.V2_LW_SECONDARY, linestyle=S.V2_DASH, zorder=5)
    D["water"].clip(frame).plot(ax=ax, color=S.V2_WATER, lw=0, zorder=6)
    D["rivers"].clip(frame).plot(ax=ax, color=S.V2_WATER, lw=rivers_lw, zorder=6)
    D["drb"].boundary.plot(ax=ax, color=S.V2_BLACK, lw=S.V2_LW_PRIMARY, zorder=7)
    for sp in ax.spines.values():
        sp.set_linewidth(S.V2_LW_SECONDARY); sp.set_color(S.V2_BLACK); sp.set_zorder(30)
    ax.set_xticks([]); ax.set_yticks([])


def draw_features(ax, D, radii=True):
    s = D["sites"]
    if radii:
        for g in s.geometry:
            ax.add_patch(Circle((g.x, g.y), 16093.44, fill=False, ec=S.V2_GRAY, lw=S.V2_LW_TERTIARY,
                                linestyle=S.V2_DASH, zorder=8))
    p = D["plants"]
    ax.scatter(p.geometry.x, p.geometry.y, s=plant_area(p.median_flow_mgd), facecolors="none",
               edgecolors=S.V2_BLACK, linewidths=S.V2_LW_TERTIARY * 2, zorder=9)
    for unv, ls in ((False, "solid"), (True, S.V2_DASH)):
        q = s[s.unverified.astype(bool) == unv]
        if len(q):
            ax.scatter(q.geometry.x, q.geometry.y, s=SITE_S, marker="s", c=[S.V2_FILL[b] for b in q.covered_it_bin],
                       edgecolors=S.V2_BLACK, linewidths=S.V2_LW_PRIMARY, linestyles=[ls], zorder=10)


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
                ax.plot([fx, fx], [fy, fy + sgn * k / ax.bbox.height], transform=ax.transAxes, color=S.V2_BLACK,
                        lw=S.V2_LW_SECONDARY, clip_on=False, zorder=31)
                if edge in label_edges and 0.04 < fx < 0.96:
                    out.append(ax.annotate(fmt(lon, "W" if lon < 0 else "E"), (fx, 0), xycoords="axes fraction",
                                           xytext=(0, -2), textcoords="offset points", ha="center", va="top",
                                           fontsize=S.V2_FONT_SIZE))
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
                ax.plot([fx, fx + sgn * k / ax.bbox.width], [fy, fy], transform=ax.transAxes, color=S.V2_BLACK,
                        lw=S.V2_LW_SECONDARY, clip_on=False, zorder=31)
                if edge in label_edges and 0.04 < fy < 0.96:
                    out.append(ax.annotate(fmt(lat, "N"), (0, fy), xycoords="axes fraction", xytext=(-2, 0),
                                           textcoords="offset points", ha="center", va="bottom",
                                           fontsize=S.V2_FONT_SIZE, rotation=90, rotation_mode="anchor"))
    return out


def scale_bar_axes(fig, rect_fig, m_per_mm, km_total, km_step, mi_total, mi_step, bar_mm=1.0, with_north=False):
    """Scale bar in its own transparent axes (x and y in millimetres): kilometres with labels above, miles with
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
            sa.add_patch(Rectangle((x0 + i * seg, yy), seg, bar_mm, fc=S.V2_BLACK if i % 2 == 0 else "white",
                                   ec=S.V2_BLACK, lw=S.V2_LW_TERTIARY * 2, clip_on=False))
        ty = yy + bar_mm + 0.5 if va == "bottom" else yy - 0.5
        for i in range(n + 1):
            arts.append(sa.text(x0 + i * seg, ty, f"{i * step:g}", ha="center", va=va, fontsize=S.V2_FONT_SIZE))
        ends.append((x0 + n * seg, unit, ty, va))
    xe = max(e[0] for e in ends) + 3.5
    for _, unit, ty, va in ends:
        arts.append(sa.text(xe, ty, unit, ha="left", va=va, fontsize=S.V2_FONT_SIZE))
    if with_north:
        sa.annotate("", xy=(2.5, h_mm - 3.0), xytext=(2.5, 1.0),
                    arrowprops=dict(arrowstyle="-|>,head_width=0.22,head_length=0.5", lw=S.V2_LW_SECONDARY,
                                    color=S.V2_BLACK, shrinkA=0, shrinkB=0))
        arts.append(sa.text(2.5, h_mm - 2.6, "N", ha="center", va="bottom", fontsize=S.V2_FONT_SIZE))
    return sa, arts


def north_arrow(ax, x_m, y_m, len_m):
    ax.annotate("", xy=(x_m, y_m + len_m), xytext=(x_m, y_m),
                arrowprops=dict(arrowstyle="-|>,head_width=0.22,head_length=0.5", lw=S.V2_LW_SECONDARY,
                                color=S.V2_BLACK, shrinkA=0, shrinkB=0), zorder=25)
    return ax.text(x_m, y_m + len_m * 1.08, "N", ha="center", va="bottom", fontsize=S.V2_FONT_SIZE, zorder=25)


def _tbb(t, r):
    if isinstance(t, mtext.Annotation):
        t.update_positions(r)
    return mtext.Text.get_window_extent(t, r)


DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.75, 0.75), (-0.75, 0.75), (0.75, -0.75), (-0.75, -0.75),
        (1, 0.45), (-1, 0.45), (1, -0.45), (-1, -0.45)]
RADII = [4.6, 6.0, 7.8, 10.5, 14.0, 18.0, 23.0]
LEADER_FROM = 7.8


def place_numbers(ax, pts, texts, hard_boxes, symbols, color=S.V2_BLACK, size=S.V2_FONT_SIZE, radii=RADII,
                  leader_from=LEADER_FROM):
    """Place short labels next to points. Hard constraints: inside axes; no overlap with other labels or hard
    boxes; no overlap with any site square. Plant circles are soft (minimised). Leader lines only when the
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
            for di, (ux, uy) in enumerate(DIRS):
                dx, dy = ux * rr, uy * rr
                ha = "left" if ux > 0.3 else ("right" if ux < -0.3 else "center")
                va = "bottom" if uy > 0.3 else ("top" if uy < -0.3 else "center")
                lead = rr >= leader_from
                t = ax.annotate(txt, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                                fontsize=size, color=color, zorder=26,
                                arrowprops=(dict(arrowstyle="-", lw=S.V2_LW_TERTIARY, color=S.V2_BLACK, shrinkA=0.5,
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


# ------------------------------------------------------------------------------------------------ legend
def legend_box(ax, D, fig_mm_to_axes, x_mm, y_mm, w_mm, h_mm):
    """Compact boxed legend in axes coordinates; contents laid out in millimetres from the box's top-left."""
    lg = ax.inset_axes(fig_mm_to_axes(x_mm, y_mm, w_mm, h_mm))
    lg.set_xlim(0, w_mm); lg.set_ylim(h_mm, 0); lg.set_xticks([]); lg.set_yticks([])
    lg.set_facecolor("white"); lg.set_zorder(40)
    for sp in lg.spines.values():
        sp.set_linewidth(S.V2_LW_SECONDARY)
    to_pt = lambda s: s
    y = 3.2
    lg.text(2.5, y, "EXPLANATION", fontsize=S.V2_FONT_SIZE, weight="bold", va="center")
    y += 4.6
    lg.text(2.5, y, "Planned data center site, by IT load", fontsize=S.V2_FONT_SIZE, va="center")
    y += 3.3
    lg.text(2.5, y, "covered by nearest plant", fontsize=S.V2_FONT_SIZE, va="center")
    rows = [("over 200 MW", "Over 200 megawatts", "solid"), ("50 to 200 MW", "50 to 200 megawatts", "solid"),
            ("no eligible plant within 10 mi", "No eligible plant within 10 miles", "solid"), (None, "Unverified location or source", "dashed")]
    y += 4.2
    for b, lab, ls in rows:
        lg.scatter([5.0], [y], s=SITE_S, marker="s", c=S.V2_FILL[b] if b else "white", edgecolors=S.V2_BLACK,
                   linewidths=S.V2_LW_PRIMARY, linestyles=[S.V2_DASH if ls == "dashed" else "solid"], clip_on=False)
        lg.text(9.0, y, lab, fontsize=S.V2_FONT_SIZE, va="center")
        y += 4.0
    y += 1.4
    lg.text(2.5, y, "Municipal wastewater treatment plant,", fontsize=S.V2_FONT_SIZE, va="center")
    y += 3.3
    lg.text(2.5, y, "median flow, in million gallons per day", fontsize=S.V2_FONT_SIZE, va="center")
    y += 7.0
    for xx, q in ((7.0, 5), (18.0, 25), (32.0, 100)):
        lg.scatter([xx], [y], s=plant_area(q), facecolors="none", edgecolors=S.V2_BLACK,
                   linewidths=S.V2_LW_TERTIARY * 2, clip_on=False)
        lg.text(xx + np.sqrt(plant_area(q)) / 2 / PT_PER_MM + 1.0, y, f"{q}", fontsize=S.V2_FONT_SIZE, va="center")
    y += 7.0
    lg.add_patch(Circle((5.0, y), 2.0, fill=False, ec=S.V2_GRAY, lw=S.V2_LW_SECONDARY, linestyle=S.V2_DASH))
    lg.text(9.0, y, "10-mile radius around site", fontsize=S.V2_FONT_SIZE, va="center")
    y += 4.8
    lg.plot([2.5, 7.5], [y, y], color=S.V2_BLACK, lw=S.V2_LW_PRIMARY)
    lg.text(9.0, y, "Delaware River Basin boundary", fontsize=S.V2_FONT_SIZE, va="center")
    y += 4.4
    lg.plot([2.5, 7.5], [y, y], color=S.V2_GRAY_DARK, lw=S.V2_LW_SECONDARY, linestyle=S.V2_DASH)
    lg.text(9.0, y, "State boundary", fontsize=S.V2_FONT_SIZE, va="center")
    return lg, y + 2.8


# ------------------------------------------------------------------------------------------------ map
def render_map(D):
    S.v2_rc()
    fig = plt.figure(figsize=(MAP_W_MM * MM, MAP_H_MM * MM), dpi=S.V2_DPI)
    l_mm, r_mm, b_mm, t_mm = 8.0, 2.0, 12.0, 2.0
    aw, ah = MAP_W_MM - l_mm - r_mm, MAP_H_MM - b_mm - t_mm
    ax = fig.add_axes([l_mm / MAP_W_MM, b_mm / MAP_H_MM, aw / MAP_W_MM, ah / MAP_H_MM])
    x0, y0, x1, y1 = D["drb"].total_bounds
    pad = 6000.0
    hgt = (y1 - y0) + 2 * pad
    wid = hgt * aw / ah
    ext = (x0 - pad - 12000.0, y0 - pad, x0 - pad - 12000.0 + wid, y1 + pad)
    relief, rext = build_relief_aea(ext, D["drb"])
    draw_base(ax, D, ext, relief, rext)
    draw_features(ax, D)
    tick_txt = edge_ticks(ax, ext, 0.5)
    m_per_mm = wid / aw

    def mm_to_axes(x_mm, y_mm, w_mm, h_mm):   # x from left, y from top, in map-axes millimetres
        return [x_mm / aw, 1 - (y_mm + h_mm) / ah, w_mm / aw, h_mm / ah]
    lw_mm, lh_mm = 57.0, 84.0
    lx_mm, ly_mm = aw - lw_mm - 2.5, ah - lh_mm - 2.5
    lg, used = legend_box(ax, D, mm_to_axes, lx_mm, ly_mm, lw_mm, lh_mm)
    fx = lambda xm: (l_mm + xm) / MAP_W_MM
    fy = lambda ym_from_top: (b_mm + ah - ym_from_top) / MAP_H_MM
    sa, sb = scale_bar_axes(fig, [fx(lx_mm + 1.0), fy(ly_mm + lh_mm - 1.0), (lw_mm - 2.0) / MAP_W_MM, 16.0 / MAP_H_MM],
                            m_per_mm, 50, 10, 30, 10, bar_mm=1.0, with_north=True)
    sa.set_zorder(41)
    na = sb[-1]

    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    hard = [_tbb(t, r) for t in tick_txt] + [lg.get_window_extent(r)]
    sym = symbols_px(ax, D)
    # cities first (small gray type, small gray dot), then site numbers
    c = D["cities"]
    ax.scatter(c.geometry.x, c.geometry.y, s=4, c=S.V2_GRAY_DARK, lw=0, zorder=11)
    sym_c = sym + [(*ax.transData.transform((g.x, g.y)), 1.2, "site") for g in c.geometry]
    to_d = lambda syms: [(x / (fig.dpi / 72) * (fig.dpi / 72), y, rad, k) for x, y, rad, k in syms]
    city_labels, city_rep = place_numbers(ax, [(g.x, g.y) for g in c.geometry], list(c["name"]), hard,
                                          [(x, y, rad, k) for x, y, rad, k in sym_c], color=S.V2_GRAY_DARK,
                                          radii=[2.5, 3.5, 5.0], leader_from=99)
    hard2 = hard + [_tbb(t, r) for t in city_labels]
    s = D["sites"]
    num_labels, num_rep = place_numbers(ax, [(g.x, g.y) for g in s.geometry], [str(n) for n in s.number], hard2,
                                        sym_c)
    S.v2_source_line(fig, MAP_SOURCES, y_mm=1.8, x_mm=l_mm)
    overlaps = text_overlaps(fig)
    stem = FIGURES / "supply_screen_map_v2"
    for ext_ in ("png", "pdf", "svg"):
        fig.savefig(f"{stem}.{ext_}", dpi=S.V2_DPI)
    # data
    rows = []
    for g, rr, t in zip(s.geometry, s.itertuples(), num_labels):
        rows.append({"element": "planned_site", "number": rr.number, "site_id": rr.site_id, "name": rr.name,
                     "lon": rr.lon, "lat": rr.lat, "x_aea_m": g.x, "y_aea_m": g.y, "covered_it_mw": rr.covered_it_mw,
                     "covered_it_class": rr.covered_it_bin, "fill": S.V2_FILL[rr.covered_it_bin],
                     "outline": "dashed" if rr.unverified else "solid", "radius_mi": 10.0,
                     "label_dx_pt": t.xyann[0], "label_dy_pt": t.xyann[1],
                     "leader": t.arrow_patch is not None})
    p = D["plants"]
    for g, rr in zip(p.geometry, p.itertuples()):
        rows.append({"element": "municipal_plant", "site_id": rr.npdes_id, "name": rr.name, "lon": rr.lon,
                     "lat": rr.lat, "x_aea_m": g.x, "y_aea_m": g.y, "median_flow_mgd": rr.median_flow_mgd,
                     "marker_area_pt2": float(plant_area(rr.median_flow_mgd))})
    for g, nm in zip(c.geometry, c["name"]):
        ll = TO_LL.transform(g.x, g.y)
        rows.append({"element": "reference_city", "name": nm, "lon": ll[0], "lat": ll[1], "x_aea_m": g.x, "y_aea_m": g.y})
    pd.DataFrame(rows).to_csv(f"{stem}_data.csv", index=False)
    plt.close(fig)
    return {"text_overlaps": overlaps, "site_labels": num_rep, "city_labels": city_rep,
            "n_leaders": int(sum(x["leader"] for x in num_rep)), "legend_used_mm": used, "legend_h_mm": lh_mm}


# ------------------------------------------------------------------------------------------------ bar
def bar_counts(ss):
    rows = []
    for b in S.V2_BIN_ORDER:
        sub = ss[ss.covered_it_bin == b]
        rows.append({"covered_it_class": b, "fill": S.V2_FILL[b], "n_sites": len(sub),
                     "n_verified": int((~sub.unverified.astype(bool)).sum()),
                     "n_unverified": int(sub.unverified.astype(bool).sum())})
    return pd.DataFrame(rows)


def _hatch_rect(ax, x, w, y, h, dark):
    col = "white" if dark else S.V2_BLACK
    ax.add_patch(Rectangle((x, y), w, h, fill=False, hatch=S.V2_HATCH * 2, lw=0, ec=col, zorder=3))


def render_bar(D):
    S.v2_rc()
    ss = D["ss"]
    bc = bar_counts(ss)
    fig = plt.figure(figsize=(BAR_W_MM * MM, BAR_H_MM * MM), dpi=S.V2_DPI)
    l_mm, r_mm = 3.0, 3.0
    ax = fig.add_axes([l_mm / BAR_W_MM, 18.2 / BAR_H_MM, (BAR_W_MM - l_mm - r_mm) / BAR_W_MM, 7.0 / BAR_H_MM])
    ax.set_xlim(0, len(ss)); ax.set_ylim(0, 1)
    y, h = 0.0, 0.52
    left = 0
    seg_rows = []
    for rr in bc.itertuples():
        dark = rr.covered_it_class == "over 200 MW"
        ax.add_patch(Rectangle((left, y), rr.n_sites, h, fc=rr.fill, ec=S.V2_BLACK, lw=S.V2_LW_SECONDARY, zorder=2))
        if rr.n_unverified:
            _hatch_rect(ax, left + rr.n_verified, rr.n_unverified, y, h, dark)
            ax.plot([left + rr.n_verified] * 2, [y, y + h], color=S.V2_BLACK if not dark else "white",
                    lw=S.V2_LW_TERTIARY, zorder=4)
        ax.text(left + rr.n_sites / 2, y + h + 0.1, f"{rr.n_sites}", ha="center", va="bottom", fontsize=S.V2_FONT_SIZE)
        seg_rows.append({**rr._asdict(), "left": left, "right": left + rr.n_sites,
                         "hatch_from": left + rr.n_verified if rr.n_unverified else None,
                         "hatch_color": ("white" if dark else "black") if rr.n_unverified else None})
        left += rr.n_sites
    for s_ in ("top", "right", "left"):
        ax.spines[s_].set_visible(False)
    ax.spines["bottom"].set_linewidth(S.V2_LW_SECONDARY)
    ax.set_yticks([]); ax.set_xticks([0, 6, 12, 18, 24])
    ax.tick_params(axis="x", length=2.0, width=S.V2_LW_SECONDARY, pad=1.2)
    ax.set_xlabel("Active planned sites (count)", labelpad=1.5)
    # key below the axis: swatches laid out by measured text width; wraps to a second row if needed
    W = BAR_W_MM - l_mm - r_mm
    kx = fig.add_axes([l_mm / BAR_W_MM, 3.6 / BAR_H_MM, W / BAR_W_MM, 7.0 / BAR_H_MM])
    kx.set_axis_off(); kx.set_xlim(0, W); kx.set_ylim(0, 7.0)
    items = [("Over 200 MW", S.V2_FILL["over 200 MW"], False), ("50 to 200 MW", S.V2_FILL["50 to 200 MW"], False),
             ("No eligible plant within 10 mi", S.V2_FILL["no eligible plant within 10 mi"], False), ("Unverified", "white", True)]
    fig.canvas.draw(); rend = fig.canvas.get_renderer()
    px_per_mm = fig.dpi / 25.4
    x, row = 0.0, 0
    for lab, fc, hatch in items:
        t = kx.text(0, 0, lab, fontsize=S.V2_FONT_SIZE, va="center")
        tw = t.get_window_extent(rend).width / px_per_mm
        t.remove()
        if x + 4.2 + tw > W and x > 0:
            x, row = 0.0, row + 1
        yc = 5.2 - row * 3.6
        kx.add_patch(Rectangle((x, yc - 1.15), 3.2, 2.3, fc=fc, ec=S.V2_BLACK, lw=S.V2_LW_SECONDARY))
        if hatch:
            kx.add_patch(Rectangle((x, yc - 1.15), 3.2, 2.3, fill=False, hatch=S.V2_HATCH * 2, lw=0, ec=S.V2_BLACK))
        kx.text(x + 4.2, yc, lab, va="center", fontsize=S.V2_FONT_SIZE)
        x += 4.2 + tw + 3.0
    S.v2_source_line(fig, BAR_SOURCES, y_mm=0.5, x_mm=l_mm)
    overlaps = text_overlaps(fig)
    stem = FIGURES / "supply_screen_bar_v2"
    for ext_ in ("png", "pdf", "svg"):
        fig.savefig(f"{stem}.{ext_}", dpi=S.V2_DPI)
    pd.DataFrame(seg_rows).drop(columns=["Index"]).to_csv(f"{stem}_data.csv", index=False)
    plt.close(fig)
    return {"text_overlaps": overlaps, "counts": bc.to_dict("records")}


# ------------------------------------------------------------------------------------------------ detail
def render_detail(D):
    S.v2_rc()
    ss = D["ss"].set_index("site_id")
    fig = plt.figure(figsize=(DET_W_MM * MM, DET_H_MM * MM), dpi=S.V2_DPI)
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
        draw_base(ax, D, ext, relief, rext, relief_strength=0.06, rivers_lw=S.V2_LW_PRIMARY)
        draw_features(ax, D)
        ticks = edge_ticks(ax, ext, step)
        mpm = 2 * hx / pw
        axl = (l_mm + i * (pw + gap))
        sa, sb = scale_bar_axes(fig, [(axl + pw - 44.0) / DET_W_MM, (b_mm + 2.0) / DET_H_MM, 42.0 / DET_W_MM,
                                      11.0 / DET_H_MM], mpm, *sbar, bar_mm=0.9)
        sa.patch.set_alpha(1.0); sa.patch.set_facecolor("white"); sa.set_axis_on(); sa.set_xticks([]); sa.set_yticks([])
        for sp in sa.spines.values():
            sp.set_linewidth(S.V2_LW_TERTIARY)
        ax.text(0.0, 1.0, tag, transform=ax.transAxes, ha="left", va="bottom", fontsize=S.V2_FONT_SIZE + 1)
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
                                    [short[n] for n in in_frame], hard, sym, color=S.V2_GRAY_DARK,
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
    S.v2_source_line(fig, DET_SOURCES, y_mm=1.8, x_mm=l_mm)
    overlaps = text_overlaps(fig)
    stem = FIGURES / "falls_plymouth_detail_v2"
    for ext_ in ("png", "pdf", "svg"):
        fig.savefig(f"{stem}.{ext_}", dpi=S.V2_DPI)
    pd.DataFrame(rows).to_csv(f"{stem}_data.csv", index=False)
    plt.close(fig)
    return {"text_overlaps": overlaps, **reports}


# ------------------------------------------------------------------------------------------------ captions
def _fmt_mw(v):
    return "" if pd.isna(v) else f"{v:,.0f}"


def write_captions(D, key, out_dir=None):
    out_dir = out_dir or FIGURES
    ss, summ, cal = D["ss"], D["summ"], D["cal"]
    hi, bins = summ["headline_capacity_independent"], summ["covered_it_bins"]
    n = hi["of"]; n_ge50 = bins["50 to 200 MW"] + bins["over 200 MW"]
    n_unv = int(ss.unverified.astype(bool).sum())
    per_mw = float(ss.peak_day_gpd.iloc[0] / ss.it_mw.iloc[0])
    f = ss.set_index("site_id").loc["DRB12"]; p = ss.set_index("site_id").loc["DRB31"]
    table = ["| No. | Site | Municipality | Stated capacity (MW) | IT load covered (MW) | Verified |",
             "|---:|:--|:--|---:|---:|:-:|"]
    for r in key.itertuples():
        table.append(f"| {r.number} | {r.name} | {r.municipality} | {_fmt_mw(r.stated_mw) or 'not published'} | "
                     f"{r.covered_it_mw:,.0f} | {r.verified} |")
    m = "\n".join([
        "# Figure 1 (supply_screen_map_v2)", "",
        f"**Figure 1.** Map showing the {n} active planned data center sites in the Delaware River Basin and the "
        f"municipal wastewater treatment plants whose effluent could supply their cooling water. Each site is shaded by "
        f"the largest information technology (IT) load whose modelled peak-day cooling makeup the median effluent flow "
        f"of the nearest eligible municipal plant within 10 miles could cover. {n_ge50} of {n} sites have such a plant "
        f"able to cover at least 50 megawatts (MW) of IT load: {bins['over 200 MW']} sites over 200 MW (solid) and "
        f"{bins['50 to 200 MW']} sites between 50 and 200 MW (half-tone). The remaining {bins['no eligible plant within 10 mi']} sites "
        f"(open) have no eligible plant within 10 miles. Dashed outlines mark the {n_unv} sites whose location is "
        f"approximate or uncertain or whose cited source could not be confirmed. Circle area is proportional to the "
        f"median monthly effluent flow reported from July 2023 to June 2026 [epa_echo]. Dashed gray circles are "
        f"10-mile radii around each site. Numbers identify sites in the key below.", "",
        f"Demand is the calibrated hybrid cooling model at {per_mw:,.0f} gallons per day of peak-day makeup per MW of "
        f"IT load, driven by hourly Trenton weather for 2005 to 2024 [noaa_isd; stull_2011] and calibrated to the "
        f"reported Falls Township average cooling demand of 135,000 gallons per day and peak of 4.4 million gallons "
        f"per day [falls_levittown_2026]. These rates are model-derived. Covered IT load does not depend on each "
        f"site's own capacity, which {hi['n_no_published_capacity']} of {n} sites do not publish. Eligible plants are "
        f"municipal major dischargers with at least 12 months of flow reports; industrial dischargers are excluded. "
        f"The basin boundary is the union of hydrologic units 020401 and 020402 [usgs_wbd]; rivers, reservoirs and "
        f"Delaware Bay are from NHDPlus High Resolution [usgs_nhdplus_hr]; state and county lines are the Census "
        f"cartographic boundary files and city locations are TIGERweb place interior points [census_tiger]; relief "
        f"is Natural Earth shaded relief [natural_earth]; site locations and sources are from the Data Center "
        f"Proposal Tracker [trackdatacenters_2026]. The source line lists DRBC because the basin framing and review "
        f"thresholds come from the Commission [drbc_admin_manual]. Albers equal-area conic projection, North American "
        f"Datum of 1983, standard parallels 39 and 42 degrees north, central meridian 75.3 degrees west.", "",
        "**Site key** (also in figures/site_key.csv). Stated capacity is campus power as published; IT load covered "
        "is the model value described above.", ""] + table + ["",
        "**Citation keys.** epa_echo, noaa_isd, stull_2011, falls_levittown_2026, usgs_wbd, usgs_nhdplus_hr, "
        "census_tiger, natural_earth, trackdatacenters_2026, drbc_admin_manual.", ""])
    (out_dir / "supply_screen_map_v2_caption.md").write_text(m)
    bc = bar_counts(ss)
    b = "\n".join([
        "# Figure 2 (supply_screen_bar_v2)", "",
        f"**Figure 2.** Bar chart showing the {n} active planned data center sites in the Delaware River Basin "
        f"[trackdatacenters_2026] divided by the largest IT load whose modelled peak-day cooling makeup the nearest "
        f"eligible municipal plant within 10 miles could cover [epa_echo]. {bins['over 200 MW']} sites fall over "
        f"200 MW (solid), {bins['50 to 200 MW']} between 50 and 200 MW (half-tone), and {bins['no eligible plant within 10 mi']} with "
        f"no eligible plant within 10 miles (open). Fills and counts are identical to figure 1. Diagonal hatching marks the {n_unv} sites with an "
        f"unverified location or source; the hatch is drawn in white on the solid segment so that it remains "
        f"visible. The demand rate is the model value of figure 1 ({per_mw:,.0f} gallons per day per MW of IT load "
        f"on the peak day) [noaa_isd; falls_levittown_2026].", "",
        "| Class | Sites | Verified | Unverified |", "|:--|---:|---:|---:|"] +
        [f"| {r.covered_it_class} | {r.n_sites} | {r.n_verified} | {r.n_unverified} |" for r in bc.itertuples()] + ["",
        "**Citation keys.** trackdatacenters_2026, epa_echo, noaa_isd, falls_levittown_2026.", ""])
    (out_dir / "supply_screen_bar_v2_caption.md").write_text(b)
    num = ss.set_index("site_id")["number"]
    d = "\n".join([
        "# Figure A1 (falls_plymouth_detail_v2), appendix and presentation only", "",
        f"**Figure A1.** Maps showing two planned data center sites and the municipal treatment plants nearest to "
        f"them. (A) Lower Bucks County, Pennsylvania: site {num['DRB12']} (AWS Keystone Trade Center, Falls Township) "
        f"is matched to the Trenton Sewer Utility in New Jersey, {f.distance_mi:.3g} miles away, with a median flow "
        f"of {f.plant_median_flow_mgd:.3g} million gallons per day that covers {f.covered_it_mw:,.0f} MW of IT load; "
        f"the nearest eligible Pennsylvania plant, the Morrisville Borough STP, is {f.same_state_distance_mi:.3g} "
        f"miles away with {f.same_state_median_flow_mgd:.3g} million gallons per day, covering "
        f"{f.same_state_covered_it_mw:,.0f} MW. (B) Conshohocken, Plymouth Township, Pennsylvania: site "
        f"{num['DRB31']} is matched to the Matsunk STP, {p.distance_mi:.3g} miles away, with "
        f"{p.plant_median_flow_mgd:.3g} million gallons per day covering {p.covered_it_mw:,.0f} MW [epa_echo; "
        f"trackdatacenters_2026]. Symbols, model and projection are as in figure 1.", "",
        "**Citation keys.** epa_echo, trackdatacenters_2026, usgs_wbd, usgs_nhdplus_hr, census_tiger.", ""])
    (out_dir / "falls_plymouth_detail_v2_caption.md").write_text(d)


def run():
    FIGURES.mkdir(exist_ok=True)
    D = load()
    key = site_key(D["ss"])
    rep = {"map": render_map(D), "bar": render_bar(D), "detail": render_detail(D)}
    write_captions(D, key)
    # map and bar consistency: identical fills and counts from the same table
    mdat = pd.read_csv(FIGURES / "supply_screen_map_v2_data.csv")
    ms = mdat[mdat.element == "planned_site"].groupby(["covered_it_class", "fill"]).size().to_dict()
    bd = pd.read_csv(FIGURES / "supply_screen_bar_v2_data.csv")
    bs = {(r.covered_it_class, r.fill): int(r.n_sites) for r in bd.itertuples()}
    rep["map_bar_consistent"] = {str(k): (ms.get(k), bs.get(k)) for k in bs}
    rep["map_bar_identical"] = all(ms.get(k) == v for k, v in bs.items()) and sum(bs.values()) == len(D["ss"])
    rep["palette_check"] = S.cvd_check({"accent": S.V2_ACCENT, "half": S.V2_ACCENT_HALF, "open": "#FFFFFF",
                                        "water": S.V2_WATER})
    (RESULTS / "figures_v2_check.json").write_text(json.dumps(rep, indent=1, default=str))
    write_stem_checks(rep)
    return rep


def write_stem_checks(rep):
    """STANDARDS H1: one results/<stem>_check.json per figure, with the conflict lists and a pass flag."""
    m = rep["map"]
    site_bad = [x for x in m["site_labels"] if x["label_overlaps"] or x["square_overlaps"] or x["outside_axes"]
                or x.get("plant_circle_overlaps")]
    city_bad = [x for x in m["city_labels"] if x["label_overlaps"] or x["square_overlaps"]]
    per = {"supply_screen_map_v2": {"text_text_or_edge": m["text_overlaps"], "site_label_conflicts": site_bad,
                                    "city_label_conflicts": city_bad},
           "supply_screen_bar_v2": {"text_text_or_edge": rep["bar"]["text_overlaps"]},
           "falls_plymouth_detail_v2": {"text_text_or_edge": rep["detail"]["text_overlaps"]}}
    for stem, chk in per.items():
        ok = not any(chk.values())
        (RESULTS / f"{stem}_check.json").write_text(json.dumps({"figure": f"figures/{stem}", "pass": ok, **chk},
                                                               indent=1, default=str))


if __name__ == "__main__":
    r = run()
    print(json.dumps({"map_overlaps": r["map"]["text_overlaps"], "bar_overlaps": r["bar"]["text_overlaps"],
                      "detail_overlaps": r["detail"]["text_overlaps"], "identical": r["map_bar_identical"],
                      "leaders": r["map"]["n_leaders"],
                      "site_label_issues": [x for x in r["map"]["site_labels"] if x["label_overlaps"] or x["square_overlaps"] or x["outside_axes"]],
                      "city_label_issues": [x for x in r["map"]["city_labels"] if x["label_overlaps"] or x["square_overlaps"]],
                      "palette_min_dE": r["palette_check"]["overall_min_delta_e"],
                      "legend_used_mm": r["map"]["legend_used_mm"]}, indent=1, default=str))
