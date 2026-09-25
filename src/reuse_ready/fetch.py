"""Idempotent download of every raw dataset into data/raw/, with a MANIFEST.md row for each file.

Usage:
    PYTHONPATH=src python -m reuse_ready.fetch            # download what is missing, record provenance
    PYTHONPATH=src python -m reuse_ready.fetch --force    # re-download everything downloadable
    PYTHONPATH=src python -m reuse_ready.fetch --only isd usgs
    PYTHONPATH=src python -m reuse_ready.fetch --verify   # check every MANIFEST row: file exists, SHA-256 matches

Rules:
  * A file is downloaded only if it is missing (or empty), or when ``force=True``.
  * Every raw file always gets a MANIFEST row. A fresh download is recorded with the current UTC
    time. A file already on disk that has no row is recorded with its mtime (UTC) as
    downloaded_utc and the note 'recorded from existing file'. Existing rows are never rewritten
    unless the file is re-downloaded.
  * User-provided inputs (the two tracker CSVs) cannot be downloaded; missing CSVs are a hard error.
  * Documents read by reuse_ready.docs, calibration and wue (DRBC rule PDF, DRBC data-centers page, four
    press pages, LBNL 2024 report) and the Natural Earth populated places archive are downloaded from the
    URLs recorded in MANIFEST.md (steps 'documents' and 'basemap').
  * Web pages carry per-request markup (bot-protection tokens, nonces), so a re-download of an HTML page
    usually has a different SHA-256 from the recorded copy. The new file is recorded with a note naming the
    previous hash, and the step prints a drift list; the page text used downstream is re-checked by
    reuse_ready.docs (verbatim passages).
  * --verify fails (exit 1) unless every MANIFEST row names a file that exists with the recorded SHA-256
    and every raw file has a row.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.parse
from pathlib import Path

import requests

from .paths import MANIFEST, PROCESSED, RAW, USER_AGENT, read_manifest, record_download, sha256

EXISTING_NOTE = "recorded from existing file"
HEADERS = {"User-Agent": USER_AGENT}

# ----------------------------------------------------------------------------- URLs
ISD_STATIONS = ("72409514792", "72408013739")  # KTTN Trenton Mercer, KPHL Philadelphia Intl
ISD_YEARS = range(2005, 2026)
ISD_URL = "https://www.ncei.noaa.gov/data/global-hourly/access/{year}/{id}.csv"

USGS_DV_URL = ("https://waterservices.usgs.gov/nwis/dv/?format=rdb&sites=01463500&parameterCd=00060"
               "&statCd=00003&startDT=1900-01-01&siteStatus=all")

WBD = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer"
NHD_FLOWLINE = "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer/3/query"
TIGER_COUNTIES = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query"


def _q(where: str) -> str:
    return urllib.parse.quote(where)


GIS = {
    "wbd_huc4_0204.geojson": f"{WBD}/2/query?where=huc4%3D%270204%27&outFields=*&outSR=4326&f=geojson",
    "wbd_huc6_0204.geojson": (f"{WBD}/3/query?where=huc6+like+%270204%25%27"
                              "&outFields=huc6,name,areasqkm&outSR=4326&f=geojson"),
    "counties_pa_nj_de_ny.geojson": (f"{TIGER_COUNTIES}?where=STATE+IN+(%2742%27,%2734%27,%2710%27,%2736%27)"
                                     "&outFields=GEOID,NAME,STATE,BASENAME&outSR=4326"
                                     "&maxAllowableOffset=0.002&f=geojson"),
}
for _name in ("Delaware River", "Schuylkill River"):
    GIS[f"nhd_{_name.lower().replace(' ', '_')}.geojson"] = (
        f"{NHD_FLOWLINE}?where=" + _q("gnis_name='" + _name + "' AND vpuid LIKE '0204%'")
        + "&outFields=gnis_name,streamorde,vpuid,ftype,levelpathi,totdasqkm&outSR=4326"
        "&maxAllowableOffset=0.0005&geometryPrecision=5&f=geojson"
    )

TRACKER_SOURCE = "provided by author (hand-built from https://trackdatacenters.com)"
LBNL_URL = ("https://eta-publications.lbl.gov/sites/default/files/2024-12/"
            "lbnl-2024-united-states-data-center-energy-usage-report_1.pdf")
USER_INPUTS = {
    "trackdatacenters_drb.csv": (TRACKER_SOURCE, True),
    "trackdatacenters_drb_nearmiss.csv": (TRACKER_SOURCE, True),
}

# Documents read by reuse_ready.docs (verbatim regulatory passages), calibration (press figures) and wue
# (LBNL comparators). file under data/raw -> (URL, MANIFEST note).
DOCUMENTS = {
    "drbc/admin_manualCFR.pdf": ("https://www.nj.gov/drbc/library/documents/admin_manualCFR.pdf",
                                 "regulator source opened"),
    "drbc/datacenters.html": ("https://www.nj.gov/drbc/programs/supply/datacenters.html",
                              "regulator source opened"),
    "press/amazon_falls_campus_2026.html": ("https://www.amazoninnovationinpa.com/falls-township-innovation-campus/",
                                            "press page opened for calibration targets"),
    "press/falls_herald_2026.html": (
        "https://www.buckscountyherald.com/news/data-center-opponents-speak-out-against-falls-site-during-town-"
        "hall-meeting/article_94decac9-8f4e-413b-a82a-7b204f39a845.html", "press page opened for calibration targets"),
    "press/falls_keystone_2026.html": (
        "https://keystonenewsroom.com/news/infrastructure/bucks-countys-first-data-center-will-open-soon-what-you-"
        "need-to-know/", "press page opened"),
    "press/falls_levittown_2026.html": (
        "https://levittownnow.com/2026/07/15/tensions-flare-at-falls-twp-town-hall-over-amazon-data-center/",
        "press page opened for calibration targets"),
    "lbnl_2024.pdf": (LBNL_URL, "LBNL 2024 United States Data Center Energy Usage Report [shehabi_2024]"),
}
NE_PLACES_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places_simple.zip"
DRIFT_NOTE = "re-downloaded; differs from previously recorded sha256 {old} (dynamic page markup)"

DRB_NAME = "Delaware River Basin (WBD HUC6 020401+020402)"
DRB_HUC6 = ("020401", "020402")


# ----------------------------------------------------------------------------- helpers
def _have(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _mtime_utc(path: Path) -> dt.datetime:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)


def ensure_row(path: Path, url: str) -> None:
    """Add a MANIFEST row for an on-disk file that lacks one (mtime as downloaded_utc)."""
    rel = Path(path).relative_to(RAW).as_posix()
    if rel not in read_manifest():
        record_download(path, url, when=_mtime_utc(path), note=EXISTING_NOTE)


def _get(url: str, timeout: int = 600, tries: int = 4) -> requests.Response:
    for attempt in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


DRIFT: list[str] = []  # files re-downloaded this run whose SHA-256 differs from the recorded row


def _download(path: Path, url: str, force: bool, getter=None, note: str = "") -> bool:
    """Download url -> path if missing (or force); always leave a MANIFEST row. Returns True if fetched.

    If the MANIFEST already had a row for the file with a different SHA-256, the new row's note names the old
    hash and the file is added to DRIFT (reported at the end of fetch_all)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if force or not _have(path):
        rel = path.relative_to(RAW).as_posix()
        old = read_manifest().get(rel)
        content = getter(url) if getter else _get(url).content
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(content)
        tmp.replace(path)
        if old and old[4] and old[4] != sha256(path):
            DRIFT.append(rel)
            note = "; ".join(x for x in (note, DRIFT_NOTE.format(old=old[4][:16])) if x)
        record_download(path, url, note=note)
        return True
    ensure_row(path, url)
    return False


def _arcgis_geojson(url: str, page_size: int | None = None) -> bytes:
    """ArcGIS REST query returning GeoJSON; follows resultOffset pages if the transfer limit is exceeded."""
    first = _get(url, timeout=300)
    d = first.json()
    if "error" in d:
        raise RuntimeError(f"ArcGIS error for {url}: {d['error']}")
    exceeded = d.get("exceededTransferLimit") or d.get("properties", {}).get("exceededTransferLimit")
    if not exceeded:
        return first.content
    feats = list(d["features"])
    step = page_size or len(feats)
    while exceeded:
        page = _get(f"{url}&resultOffset={len(feats)}&resultRecordCount={step}", timeout=300).json()
        if "error" in page:
            raise RuntimeError(f"ArcGIS error for {url} at offset {len(feats)}: {page['error']}")
        if not page.get("features"):
            break
        feats += page["features"]
        exceeded = page.get("exceededTransferLimit") or page.get("properties", {}).get("exceededTransferLimit")
    d["features"] = feats
    d.pop("exceededTransferLimit", None)
    d.get("properties", {}).pop("exceededTransferLimit", None)
    return json.dumps(d).encode()


# ----------------------------------------------------------------------------- datasets
def fetch_isd(force: bool = False) -> None:
    """NOAA NCEI ISD global-hourly CSVs, 2005-2025, KTTN and KPHL -> data/raw/isd/{id}_{year}.csv."""
    for sid in ISD_STATIONS:
        for year in ISD_YEARS:
            if _download(RAW / "isd" / f"{sid}_{year}.csv", ISD_URL.format(year=year, id=sid), force):
                time.sleep(0.5)


def fetch_usgs(force: bool = False) -> None:
    """USGS NWIS daily mean discharge, 01463500 Delaware River at Trenton -> data/raw/usgs/dv_01463500.rdb.

    A fresh download includes days after the original retrieval (see the '# retrieved:' header line).
    """
    _download(RAW / "usgs" / "dv_01463500.rdb", USGS_DV_URL, force)


def fetch_gis(force: bool = False) -> None:
    """WBD HUC4/HUC6, NHDPlus HR Delaware/Schuylkill flowlines, TIGERweb counties -> data/raw/gis/."""
    for fname, url in GIS.items():
        _download(RAW / "gis" / fname, url, force, getter=_arcgis_geojson)


def build_drb_boundary(force: bool = True) -> Path:
    """data/processed/drb_boundary.geojson = make_valid(dissolve(WBD HUC6 020401 + 020402))."""
    import geopandas as gpd
    from shapely import make_valid

    out = PROCESSED / "drb_boundary.geojson"
    if _have(out) and not force:
        return out
    g = gpd.read_file(RAW / "gis" / "wbd_huc6_0204.geojson")
    sel = g[g.huc6.isin(DRB_HUC6)]
    if len(sel) != len(DRB_HUC6):
        raise RuntimeError(f"expected HUC6 {DRB_HUC6} in wbd_huc6_0204.geojson, found {sorted(sel.huc6)}")
    d = sel.dissolve()
    d["geometry"] = d.geometry.apply(make_valid)
    d = d[["geometry"]].assign(name=DRB_NAME)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.geojson")
    d.to_file(tmp, driver="GeoJSON")
    tmp.replace(out)
    return out


def fetch_echo(force: bool = False) -> None:
    """EPA ECHO majors per state (get_facilities -> get_download with echo.QCOLUMNS) and DMR effluent charts.

    Delegates to echo.py; both steps reuse cached files. The DMR list depends on the DRB boundary and
    the county layer (echo.select_permittees), so this runs after fetch_gis/build_drb_boundary.
    """
    import geopandas as gpd

    from . import echo

    echo.download_majors(force=force)
    for st in echo.STATES:
        ensure_row(echo.RAW_ECHO / f"majors_{st}.csv",
                   echo.majors_url(st) + " -> get_download (qcolumns " + echo.QCOLUMNS + ")")
    boundary = gpd.read_file(PROCESSED / "drb_boundary.geojson")
    counties = gpd.read_file(RAW / "gis" / "counties_pa_nj_de_ny.geojson")
    # Null-design permittees need DMRs before select_permittees can assign their fallback flow (G05).
    nd = echo.null_design_ids(boundary, counties)
    echo.download_dmrs(nd)
    ids = list(dict.fromkeys(nd + list(echo.select_permittees(boundary, counties).npdes_id)))
    if force:
        for pid in ids:
            (echo.RAW_DMR / f"{pid}.csv").unlink(missing_ok=True)
    echo.download_dmrs(ids)
    missing = []
    for pid in ids:
        p = echo.RAW_DMR / f"{pid}.csv"
        url = (f"{echo.ECHO}/eff_rest_services.download_effluent_chart?p_id={pid}"
               f"&start_date={echo.DMR_START}&end_date={echo.DMR_END}")
        if _have(p):
            ensure_row(p, url)
        else:
            missing.append(pid)
    if missing:
        raise RuntimeError(f"ECHO DMR download failed for {len(missing)} permittees: {missing}")


def fetch_drbc(force: bool = False) -> None:
    """DRBC drought-declaration page (flow.fetch_drought_page records its own MANIFEST row)."""
    from . import flow

    if force or not _have(flow.DROUGHT_HTML):
        flow.fetch_drought_page()
    else:
        ensure_row(flow.DROUGHT_HTML, flow.DROUGHT_URL)


def fetch_documents(force: bool = False) -> None:
    """DRBC rule PDF and data-centers page, four Falls Township press pages, LBNL 2024 report (DOCUMENTS)."""
    for rel, (url, note) in DOCUMENTS.items():
        if _download(RAW / rel, url, force, note=note):
            time.sleep(0.5)


def fetch_basemap(force: bool = False) -> None:
    """Natural Earth populated places, then Natural Earth relief / NHD waterbodies / city geocodes /
    cartographic boundaries via reuse_ready.basemap.fetch_all()."""
    import importlib

    _download(RAW / "natural_earth" / "ne_10m_populated_places_simple.zip", NE_PLACES_URL, force)
    basemap = importlib.import_module(f"{__package__}.basemap")
    basemap.fetch_all(force=force)


def check_user_inputs() -> None:
    """Author-provided inputs: the two tracker CSVs are required. Records MANIFEST rows."""
    missing = []
    for fname, (src, required) in USER_INPUTS.items():
        p = RAW / fname
        if _have(p):
            ensure_row(p, src)
        elif required:
            missing.append(fname)
        else:
            print(f"fetch: optional input data/raw/{fname} not found ({src})", file=sys.stderr)
    if missing:
        raise SystemExit(
            "fetch: required user-provided input(s) missing: "
            + ", ".join(f"data/raw/{m}" for m in missing)
            + ". These are hand-built by the author from https://trackdatacenters.com and cannot be "
              "downloaded; place them in data/raw/ (they are tracked in git) and re-run."
        )


# ----------------------------------------------------------------------------- manifest check
def parse_manifest(manifest: Path = MANIFEST) -> dict[str, list[str]]:
    """Rows of a MANIFEST.md file keyed by path relative to its directory (same format as paths.read_manifest)."""
    rows = {}
    if Path(manifest).exists():
        for ln in Path(manifest).read_text().splitlines():
            if ln.startswith("| ") and not ln.startswith("| file ") and not ln.startswith("| ---"):
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                cells += [""] * (6 - len(cells))
                rows[cells[0]] = cells[:6]
    return rows


def unrecorded_files(manifest: Path = MANIFEST, raw: Path | None = None) -> list[str]:
    raw = Path(raw) if raw is not None else Path(manifest).parent
    rows = parse_manifest(manifest)
    files = sorted(p.relative_to(raw).as_posix() for p in raw.rglob("*")
                   if p.is_file() and p != Path(manifest) and p.name != ".DS_Store" and not p.name.endswith(".part"))
    return [f for f in files if f not in rows]


def manifest_failures(manifest: Path = MANIFEST, raw: Path | None = None) -> list[dict]:
    """Every MANIFEST problem: missing file, SHA-256 mismatch, row without a hash, raw file without a row."""
    raw = Path(raw) if raw is not None else Path(manifest).parent
    out = []
    for rel, row in sorted(parse_manifest(manifest).items()):
        p = raw / rel
        if not p.is_file():
            out.append({"file": rel, "problem": "missing", "source_url": row[1]})
        elif not row[4]:
            out.append({"file": rel, "problem": "no sha256 recorded", "source_url": row[1]})
        else:
            got = sha256(p)
            if got != row[4]:
                out.append({"file": rel, "problem": f"sha256 mismatch (recorded {row[4][:12]}, on disk {got[:12]})",
                            "source_url": row[1]})
    out += [{"file": f, "problem": "no MANIFEST row", "source_url": ""} for f in unrecorded_files(manifest, raw)]
    return out


def verify_manifest(manifest: Path = MANIFEST, raw: Path | None = None) -> int:
    """Check existence and SHA-256 of every MANIFEST row; exit 1 listing each failure."""
    fails = manifest_failures(manifest, raw)
    n = len(parse_manifest(manifest))
    if fails:
        lines = [f"  {f['file']}: {f['problem']}" + (f" [{f['source_url']}]" if f["source_url"] else "")
                 for f in fails]
        raise SystemExit(f"fetch --verify: {len(fails)} failure(s) among {n} MANIFEST rows:\n" + "\n".join(lines)
                         + "\nRun `make data` (python -m reuse_ready.fetch) to download missing files.")
    print(f"fetch --verify: all {n} MANIFEST rows present with matching SHA-256; no unrecorded raw files")
    return n


STEPS = {
    "inputs": check_user_inputs,
    "isd": fetch_isd,
    "usgs": fetch_usgs,
    "gis": fetch_gis,
    "boundary": lambda force=False: build_drb_boundary(force=True),
    "echo": fetch_echo,
    "drbc": fetch_drbc,
    "documents": fetch_documents,
    "basemap": fetch_basemap,
}


def fetch_all(force: bool = False, only: list[str] | None = None) -> None:
    for name, fn in STEPS.items():
        if only and name not in only:
            continue
        t0 = time.time()
        fn() if name == "inputs" else fn(force=force)
        print(f"fetch: {name} ok ({time.time() - t0:.1f} s)")
    if DRIFT:
        print(f"fetch: {len(DRIFT)} re-downloaded file(s) differ from the previously recorded SHA-256 "
              f"(new hash recorded): {DRIFT}", file=sys.stderr)
    verify_manifest()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m reuse_ready.fetch", description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    ap.add_argument("--only", nargs="+", choices=list(STEPS), help="run only these steps")
    ap.add_argument("--verify", action="store_true",
                    help="only check that every MANIFEST row's file exists with the recorded SHA-256")
    a = ap.parse_args(argv)
    if a.verify:
        verify_manifest()
    else:
        fetch_all(force=a.force, only=a.only)


if __name__ == "__main__":
    main()
