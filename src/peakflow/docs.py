"""Generate sources.md from references.bib, and check that every citation key used is defined.

For each BibTeX entry, sources.md lists the key, publisher or author, title, year, URL, accessed date, the
exact figure or fact taken (custom `figure` field), a verbatim quote where one exists, and a verified flag.
It also carries the verbatim regulatory passages behind the two DRBC blind-spot mechanisms, and the
per-site source verification counts from data/sites/planned_sites.csv.

The key check scans results.md, README.md and figures/*_caption.md for [key] citations and fails if any key
is not in references.bib.
"""
from __future__ import annotations

import json
import re
import sys

import pandas as pd

from .paths import ROOT, SITES

BIB = ROOT / "references.bib"
OUT = ROOT / "sources.md"
REG_PASSAGES = [
    ("drbc_admin_manual", "18 CFR 401.35(a) (DRBC Administrative Manual Part I), lead-in",
     "Except as the Commission may specially direct by notice to the project owner or sponsor, a project in any of "
     "the following classifications will be deemed not to have a substantial effect on the water resources of the "
     "Basin and is not required to be submitted under Section 3.8 of the Compact:"),
    ("drbc_admin_manual", "18 CFR 401.35(a)(2)",
     "A withdrawal from ground water when the daily average gross withdrawal during any 30 consecutive day period "
     "does not exceed 100,000 gallons"),
    ("drbc_admin_manual", "18 CFR 401.35(a)(3)",
     "A withdrawal from impoundments or running streams for any purpose when the daily average gross withdrawal "
     "during any 30 consecutive day period does not exceed 100,000 gallons"),
    ("drbc_admin_manual", "18 CFR 401.35(c)",
     "Regardless of whether expressly excluded from review by paragraph (a) of this section, any project or class of "
     "projects that in the view of the Commission could have a substantial effect on the water resources of the basin "
     "may, upon special notice to the project sponsor or landowner, be subject to the requirement for review under "
     "section 3.8 of the Compact."),
    ("drbc_datacenters_2026", "DRBC, Data Centers in the Delaware River Basin (existing facilities)",
     "There are approximately sixty data centers currently operating within the Delaware River Basin, most of which "
     "are small-to medium-scale traditional and colocation centers. To date, the DRBC has not received any "
     "applications for data center projects because the existing data centers in the Basin purchase water from "
     "public water supply systems rather than operate their own withdrawal systems."),
    ("drbc_datacenters_2026", "DRBC, Data Centers in the Delaware River Basin (planned facilities)",
     "The DRBC is aware of approximately 24 new data centers being planned within the Delaware River Basin. As of "
     "June 2026, none has applied to the DRBC."),
]
# Raw copies of the regulator pages, used to confirm each passage appears verbatim.
REG_FILES = {"drbc_admin_manual": ROOT / "data/raw/drbc/admin_manualCFR.pdf",
             "drbc_datacenters_2026": ROOT / "data/raw/drbc/datacenters.html"}


def parse_bib(text: str) -> list[dict]:
    entries = []
    for m in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, flags=re.S):
        body, fields = m.group(3), {}
        for f in re.finditer(r"(\w+)\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", body, flags=re.S):
            fields[f.group(1).lower()] = re.sub(r"\s+", " ", f.group(2).replace("{", "").replace("}", "")).strip()
        entries.append({"type": m.group(1), "key": m.group(2).strip(), **fields})
    return entries


def _page_text(path):
    if path.suffix == ".pdf":
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(path))
        t = " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    else:
        import html
        t = path.read_text(encoding="utf-8", errors="ignore")
        t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
        t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t.replace("\u2019", "'"))


def passage_check() -> list[dict]:
    for p in REG_FILES.values():
        if not p.exists():
            raise SystemExit(f"docs: raw copy {p.relative_to(ROOT)} is missing; run `make data`")
    texts = {k: _page_text(p) for k, p in REG_FILES.items()}
    out = []
    for key, where, q in REG_PASSAGES:
        norm = re.sub(r"\s+", " ", q)
        out.append({"key": key, "where": where, "quote": q, "verbatim_in_raw_copy": norm in texts.get(key, "")})
    return out


def cited_keys() -> dict[str, set]:
    files = [ROOT / "results/results.md", ROOT / "README.md", ROOT / "LICENSES.md"] + sorted((ROOT / "figures").glob("*_caption.md"))
    used = {}
    for f in files:
        if f.exists():
            for grp in re.findall(r"\[([a-z0-9_;, ]+)\]", f.read_text()):
                for k in re.split(r"[;,]\s*", grp):
                    if re.fullmatch(r"[a-z][a-z0-9_]+_\d{4}|[a-z][a-z0-9_]+", k.strip()):
                        used.setdefault(k.strip(), set()).add(f.relative_to(ROOT).as_posix())
    return used


def run() -> dict:
    entries = parse_bib(BIB.read_text())
    keys = {e["key"] for e in entries}
    used = cited_keys()
    undefined = {k: sorted(v) for k, v in used.items() if k not in keys and not k.isdigit()}
    checks = passage_check()
    sites = pd.read_csv(SITES / "planned_sites.csv")
    main = sites[(sites.list == "main") & sites.on_map.astype(bool)] if "on_map" in sites else sites
    L = ["# Sources", "",
         "This file is generated by `make docs` (src/peakflow/docs.py) from references.bib. Each entry gives the "
         "exact figure or fact taken from the source and whether the source itself was retrieved and read. A "
         "search-engine snippet does not count as verification.", "",
         f"There are {len(entries)} entries: {sum(e.get('verified') == 'true' for e in entries)} verified and "
         f"{sum(e.get('verified') != 'true' for e in entries)} unverified.", "",
         "## Regulatory passages behind the two review blind spots", "",
         "Each passage below is quoted verbatim. The line under each heading records whether the passage was found "
         "word for word in the raw copy stored under data/raw/drbc.", ""]
    for c in checks:
        L += [f"**{c['where']}** [{c['key']}]", "",
              "The passage " + ("was found" if c["verbatim_in_raw_copy"] else "was not found") + " verbatim in the raw copy.",
              "", f"> {c['quote']}", ""]
    rep = main[main.replacement_kind.fillna("").astype(str).ne("")]
    from . import sites as _sites
    n_forced = len(set(main.site_id) & set(_sites.FORCE_UNVERIFIED))
    L += ["The 30-day averaging test in 401.35(a)(2) and (a)(3) is the basis of the averaging blind spot. The "
          "classifications apply to a project's own withdrawal. The Commission's statement that existing data "
          "centers purchase water from public water supply systems, and that none has applied, is the basis of the "
          "purchased-supply blind spot. Paragraph (c) is the Commission's discretionary power to require review of "
          "an otherwise excluded project.", "",
          "## Planned-site sources", "",
          f"Each of the {len(main)} active mapped sites cites its own source_url in data/sites/planned_sites.csv. "
          f"{int(main.source_verified.sum())} sources were opened and name the site. "
          f"{int((~main.source_verified.astype(bool)).sum())} were not confirmed (bot-blocked, forbidden to automated "
          "clients, or not naming the site) and are drawn with a dashed outline. "
          f"{int(rep.shape[0])} sources that were bot-blocked or had expired are cited through a replacement "
          f"({int((rep.replacement_kind == 'wayback').sum())} Wayback Machine snapshots, "
          f"{int((rep.replacement_kind == 'alternate_outlet').sum())} alternate outlets), with the original kept in "
          f"original_url. {n_forced} sites are classed as unverified regardless of these checks, for the reason "
          "given in verification_note. Per-URL results are in data/processed/site_url_verification.csv and "
          "data/processed/site_url_check.csv.", "",
          "## Reference entries", ""]
    for e in sorted(entries, key=lambda e: e["key"]):
        who = e.get("author", e.get("institution", ""))
        # The full project title appears only in README.md, CITATION.cff and references.bib.
        title = "PeakFlow (this repository)" if e["key"] == "peakflow_model" else e.get("title", "")
        # A semicolon inside a DOI URL is written percent-encoded (%3B), which resolves to the same record.
        url = e.get("url", "").replace(";", "%3B")
        L += [f"### {e['key']}", "",
              f"{who}. {title}. {e.get('year', '')}. {url} (accessed {e.get('urldate', 'n/a')}).", "",
              "**Figure or fact taken**", "", e.get("figure", "No figure or fact is taken from this source."), ""]
        if e.get("quote"):
            # Verbatim quotes are not reworded. A quote that runs across a semicolon is shown as its parts.
            L += [ln for part in e["quote"].split(";") if part.strip() for ln in (f"> {part.strip()}", "")]
        L += ["The source was opened and is verified." if e.get("verified") == "true"
              else "The source is not verified.", ""]
    txt = "\n".join(L).replace("\u2014", ", ").replace("\u2013", " to ")
    OUT.write_text(txt)
    report = {"entries": len(entries), "undefined_keys": undefined,
              "passages_verbatim": {c["where"]: c["verbatim_in_raw_copy"] for c in checks},
              "unused_keys": sorted(keys - set(used))}
    if not all(c["verbatim_in_raw_copy"] for c in checks):
        sys.exit("docs: a regulatory passage was not found verbatim in its raw copy")
    if undefined:
        print(json.dumps(report, indent=1))
        sys.exit(f"docs: citation keys used but not defined in references.bib: {sorted(undefined)}")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
