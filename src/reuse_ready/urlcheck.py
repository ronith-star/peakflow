"""Live HTTP check of every planned-site source URL (the only networked step outside `make data`).

Usage:
    PYTHONPATH=src python -m reuse_ready.urlcheck        # writes data/processed/site_url_check.csv

`make map` does not run this module: reuse_ready.sites.run(check=False) reads the cached CSV, so the map
build is offline and deterministic. Run `make urls` to refresh the cache; results depend on the day and on
the network (publishers that refuse automated clients return 403, which is recorded, not retried).

Checked URLs: every source_url in the two tracker CSVs plus every replacement URL in
data/sites/source_url_overrides.csv (Wayback snapshots and alternate outlets), so a replacement that stops
resolving is visible in the same file.

Status classes (url_check):
    resolves                         HTTP 200 after redirects
    resolves_paywalled               HTTP 402
    bot_blocked                      HTTP 403 from a domain in BOT_BLOCK_DOMAINS (bot-challenge page)
    forbidden_to_automated_client    any other HTTP 403
    not_found                        HTTP 404
    network_error                    anything else (timeouts, redirect loops, proxy refusals)
"""
from __future__ import annotations

import concurrent.futures as cf
import subprocess
import sys

import pandas as pd

from .paths import PROCESSED, RAW, SITES, USER_AGENT

MAIN = RAW / "trackdatacenters_drb.csv"
NEARMISS = RAW / "trackdatacenters_drb_nearmiss.csv"
OVERRIDES = SITES / "source_url_overrides.csv"
OUT = PROCESSED / "site_url_check.csv"
BOT_BLOCK_DOMAINS = {"www.datacenterdynamics.com"}
COLUMNS = ["source_url", "url_http_code", "url_final", "url_redirects", "url_check", "url_error"]


def classify_code(code: str, domain: str) -> str:
    if code == "200":
        return "resolves"
    if code == "402":
        return "resolves_paywalled"
    if code == "403":
        return "bot_blocked" if domain in BOT_BLOCK_DOMAINS else "forbidden_to_automated_client"
    if code == "404":
        return "not_found"
    return "network_error"


def check_url(u: str) -> dict:
    """curl -L the URL once (40 s limit) and classify the final HTTP status."""
    r = subprocess.run(["curl", "-sS", "-L", "-m", "40", "-A", USER_AGENT, "-o", "/dev/null",
                        "-w", "%{http_code}\t%{url_effective}\t%{num_redirects}", u],
                       capture_output=True, text=True)
    code, final, nred = (r.stdout.split("\t") + ["", "", ""])[:3]
    dom = u.split("/")[2] if "://" in u else ""
    return {"source_url": u, "url_http_code": code, "url_final": final if final and final != u else "",
            "url_redirects": int(nred or 0), "url_check": classify_code(code, dom),
            "url_error": r.stderr.strip()[:120]}


def check_urls(urls) -> pd.DataFrame:
    with cf.ThreadPoolExecutor(8) as ex:
        return pd.DataFrame(list(ex.map(check_url, sorted(set(urls)))), columns=COLUMNS)


def urls_to_check() -> list[str]:
    urls = list(pd.read_csv(MAIN).source_url.dropna()) + list(pd.read_csv(NEARMISS).source_url.dropna())
    if OVERRIDES.exists():
        urls += list(pd.read_csv(OVERRIDES).source_url.dropna())
    return sorted(set(urls))


def run(out=OUT) -> pd.DataFrame:
    uc = check_urls(urls_to_check())
    out.parent.mkdir(parents=True, exist_ok=True)
    uc.to_csv(out, index=False)
    return uc


def load(path=OUT) -> pd.DataFrame | None:
    """Cached check results, or None if `make urls` has never been run."""
    return pd.read_csv(path, dtype=str) if path.exists() else None


if __name__ == "__main__":
    uc = run()
    print(uc.url_check.value_counts().to_string())
    print(f"urlcheck: wrote {OUT.relative_to(OUT.parents[2])} ({len(uc)} URLs)", file=sys.stderr)
