"""Interactive supply-screen map (figures/supply_screen_map.html).

Esri World Light Gray Canvas tiles with Esri's attribution [esri_light_gray]. Sites are colored by covered_it_mw:
the largest IT load whose calibrated peak-day makeup the nearest eligible municipal plant's median effluent flow
covers. Outline: solid = exact location AND source page confirmed; dashed = approximate or uncertain location,
or source not confirmed.
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import styles
from ..paths import FIGURES, PROCESSED, RAW, RESULTS, SITES
from ..supply_screen import eligible_mask

BIN_FILL = {"over 200 MW": "#9A4A0B", "50 to 200 MW": "#E8A15A", "no eligible plant within 10 mi": "#FFFFFF"}
SITE_EDGE = "#4A2506"


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
                f"modeled peak-day makeup at {r.it_mw:,.0f} MW IT: {r.peak_day_gpd:,.0f} gal/day<br>{verified}<br>"
                f"<a href='{r.source_url}' target='_blank'>source</a>")
        folium.RegularPolygonMarker([r.lat, r.lon], number_of_sides=4, rotation=45, radius=7, color=SITE_EDGE,
                                    weight=1.2, dash_array="3,2" if r.unverified else None, fill=True,
                                    fill_color=BIN_FILL[r.covered_it_bin], fill_opacity=1,
                                    tooltip=folium.Tooltip(html), popup=folium.Popup(html, max_width=320)).add_to(fs)
    folium.LayerControl(collapsed=True).add_to(m)
    m.save(str(out))
    return out



def run():
    """Write the interactive HTML map (figures/supply_screen_map.html)."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    html = render_html()
    return {"html": str(html)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
