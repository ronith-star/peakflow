"""Vector and relief context layers for the static supply-screen map (no tile service).

Layers and sources:
  shaded relief   Natural Earth 1:10m Shaded Relief (SR_HR), public domain [natural_earth], cropped to the map
                  extent and stored as data/processed/relief_drb.npz (grayscale, Web Mercator grid).
  cities          TIGERweb incorporated places, interior points, selected by name and state FIPS [census_tiger].
  waterbodies     USGS NHDPlus HR NHDWaterbody (areasqkm > 4) and NHDArea (areasqkm > 20) in VPU 0204
                  [usgs_nhdplus_hr]; the NHDArea layer carries the Delaware River and Bay shoreline.
  states/counties TIGERweb (already in data/raw/gis/counties_pa_nj_de_ny.geojson) [census_tiger].
"""
from __future__ import annotations

import json
import time
import zipfile

import geopandas as gpd
import numpy as np
import requests

from .paths import PROCESSED, RAW, USER_AGENT, record_download

NE = "https://naciscdn.org/naturalearth/10m"
RELIEF_URL = f"{NE}/raster/SR_HR.zip"
PLACES_URL = f"{NE}/cultural/ne_10m_populated_places_simple.zip"
NHD = "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer"
WATERBODY_Q = {9: "areasqkm > 4 AND vpuid LIKE '0204%'", 8: "areasqkm > 20 AND vpuid LIKE '0204%'"}
CITIES = [("Philadelphia", "Pennsylvania"), ("Trenton", "New Jersey"), ("Wilmington", "Delaware"),
          ("Allentown", "Pennsylvania"), ("Camden", "New Jersey"), ("Reading", "Pennsylvania"),
          ("Scranton", "Pennsylvania")]
GIS = RAW / "gis"
NE_DIR = RAW / "natural_earth"
RELIEF_NPZ = PROCESSED / "relief_drb.npz"
MAP_BOUNDS_4326 = (-76.7, 38.6, -73.6, 42.5)  # crop window, generous around the DRB


def _get(url, **kw):
    for i in range(4):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=300, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == 3:
                raise
            time.sleep(3 * (i + 1))


def ensure_row(path, url: str) -> None:
    """Add a MANIFEST row only when the cached file has none, so reruns leave MANIFEST.md unchanged."""
    from .fetch import ensure_row as _ensure_row
    _ensure_row(path, url)


def fetch_natural_earth(force=False):
    NE_DIR.mkdir(parents=True, exist_ok=True)
    for url in (RELIEF_URL,):
        dst = NE_DIR / url.rsplit("/", 1)[1]
        if force or not dst.exists():
            dst.write_bytes(_get(url).content)
            record_download(dst, url)
        else:
            ensure_row(dst, url)


def fetch_waterbodies(force=False):
    for layer, where in WATERBODY_Q.items():
        name = "nhd_waterbody_0204.geojson" if layer == 9 else "nhd_area_0204.geojson"
        dst = GIS / name
        url = f"{NHD}/{layer}/query"
        prm = {"where": where, "outFields": "gnis_name,ftype,fcode,areasqkm", "outSR": 4326, "f": "geojson",
               "maxAllowableOffset": 0.0005, "geometryPrecision": 5, "returnGeometry": "true"}
        if force or not dst.exists():
            dst.write_text(_get(url, params=prm).text)
            record_download(dst, requests.Request("GET", url, params=prm).prepare().url)
        else:
            ensure_row(dst, requests.Request("GET", url, params=prm).prepare().url)


def build_relief(force=False):
    """Crop SR_HR to MAP_BOUNDS_4326, reproject to Web Mercator, store grayscale array + extent."""
    if RELIEF_NPZ.exists() and not force:
        return RELIEF_NPZ
    import rasterio
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    from rasterio.windows import from_bounds

    zf = zipfile.ZipFile(NE_DIR / "SR_HR.zip")
    tif = next(n for n in zf.namelist() if n.lower().endswith(".tif"))
    with rasterio.MemoryFile(zf.read(tif)) as mem, mem.open() as src:
        win = from_bounds(*MAP_BOUNDS_4326, transform=src.transform)
        arr = src.read(1, window=win).astype("float32")
        tr = src.window_transform(win)
        dst_tr, w, h = calculate_default_transform(src.crs, "EPSG:3857", arr.shape[1], arr.shape[0], *MAP_BOUNDS_4326)
        out = np.zeros((h, w), dtype="float32")
        reproject(arr, out, src_transform=tr, src_crs=src.crs, dst_transform=dst_tr, dst_crs="EPSG:3857",
                  resampling=Resampling.bilinear)
    extent = (dst_tr.c, dst_tr.c + dst_tr.a * w, dst_tr.f + dst_tr.e * h, dst_tr.f)  # left, right, bottom, top
    np.savez_compressed(RELIEF_NPZ, relief=out, extent=np.array(extent))
    return RELIEF_NPZ


TIGER_PLACES = ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
                "Places_CouSub_ConCity_SubMCD/MapServer/4/query")
CITY_STATE_FIPS = {"Pennsylvania": "42", "New Jersey": "34", "Delaware": "10"}


def fetch_cities(force=False):
    """TIGERweb incorporated places: interior points (INTPTLAT/INTPTLON) for the reference cities."""
    dst = GIS / "tiger_reference_cities.json"
    where = " OR ".join(f"(BASENAME='{n}' AND STATE='{CITY_STATE_FIPS[s]}')" for n, s in CITIES)
    prm = {"where": where, "outFields": "NAME,BASENAME,STATE,GEOID,INTPTLAT,INTPTLON", "returnGeometry": "false",
           "f": "json"}
    if force or not dst.exists():
        dst.write_text(_get(TIGER_PLACES, params=prm).text)
        record_download(dst, requests.Request("GET", TIGER_PLACES, params=prm).prepare().url)
    else:
        ensure_row(dst, requests.Request("GET", TIGER_PLACES, params=prm).prepare().url)


def load_cities() -> gpd.GeoDataFrame:
    feats = [f["attributes"] for f in json.loads((GIS / "tiger_reference_cities.json").read_text())["features"]]
    df = gpd.pd.DataFrame(feats)
    g = gpd.GeoDataFrame(df.rename(columns={"BASENAME": "name"}),
                         geometry=gpd.points_from_xy(df.INTPTLON.astype(float), df.INTPTLAT.astype(float)), crs=4326)
    g.attrs["missing"] = sorted({n for n, _ in CITIES} - set(g.name))
    return g




CB_FILES = {k: f"https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_{k}_500k.zip" for k in ("state", "county")}


def fetch_cartographic(force=False):
    """Census cartographic boundary files (1:500,000, shoreline-clipped) for the map land mask and state lines."""
    from .paths import record_download
    for k, url in CB_FILES.items():
        dst = RAW / "gis" / f"cb_2023_us_{k}_500k.zip"
        if dst.exists() and not force:
            continue
        r = _get(url)
        dst.write_bytes(r.content)
        record_download(dst, url,
                        note="Census cartographic boundary 1:500k, shoreline-clipped; land mask and state lines")


def fetch_all(force=False):
    fetch_cartographic(force=force)
    fetch_natural_earth(force)
    fetch_waterbodies(force)
    fetch_cities(force)
    build_relief(force)
    c = load_cities()
    return {"cities": list(c.name), "cities_missing": c.attrs["missing"]}


if __name__ == "__main__":
    print(json.dumps(fetch_all(), indent=2))
