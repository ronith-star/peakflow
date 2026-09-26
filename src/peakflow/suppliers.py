"""Published water-supplier evidence for the 24 active planned data center sites (work order item 11).

The table data/sites/site_suppliers.csv is compiled by hand from published sources. Each row names the
likely cooling or process water supplier and classifies it as:

* public_or_authority: water bought from an existing public system, municipal authority or investor-owned
  utility. Purchase alone does not trigger DRBC project review under 18 CFR 401.35, whose thresholds apply
  to the project's own withdrawal.
* self_supplied: the developer proposes its own wells or surface intake.
* unknown: no opened source names a supplier.

confidence is stated_in_source, inferred_service_area (utility territory is the only evidence) or none.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .paths import RESULTS, SITES

CSV = SITES / "site_suppliers.csv"
PLANNED = SITES / "planned_sites.csv"
CLASSES = ("public_or_authority", "self_supplied", "unknown")
CONFIDENCE = ("stated_in_source", "inferred_service_area", "none")
COLUMNS = [
    "site_id", "name", "municipality", "supplier_name", "supplier_class", "confidence",
    "evidence_quote", "source_url", "source_title", "source_publisher", "source_date",
    "access_date", "bib_key", "notes",
]
N_ACTIVE = 24
KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def active_site_ids(planned: Path | pd.DataFrame = PLANNED) -> set[str]:
    """Site ids with list == 'main', active and is_data_center."""
    d = pd.read_csv(planned) if not isinstance(planned, pd.DataFrame) else planned
    m = (d["list"] == "main") & d["active"].astype(bool) & d["is_data_center"].astype(bool)
    return set(d.loc[m, "site_id"])


def _blank(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def validate(df: pd.DataFrame, expected_ids: set[str] | None = None, n: int = N_ACTIVE) -> pd.DataFrame:
    """Raise ValueError if the supplier table breaks any rule; return the table unchanged otherwise."""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if len(df) != n:
        raise ValueError(f"expected {n} rows, got {len(df)}")
    if df["site_id"].duplicated().any():
        raise ValueError(f"duplicate site_id: {sorted(df.loc[df.site_id.duplicated(), 'site_id'])}")
    if expected_ids is not None and set(df["site_id"]) != set(expected_ids):
        raise ValueError(
            f"site_id mismatch: extra {sorted(set(df.site_id) - set(expected_ids))}, "
            f"missing {sorted(set(expected_ids) - set(df.site_id))}"
        )
    bad = df.loc[~df["supplier_class"].isin(CLASSES), "site_id"]
    if len(bad):
        raise ValueError(f"supplier_class not in {CLASSES}: {list(bad)}")
    bad = df.loc[~df["confidence"].isin(CONFIDENCE), "site_id"]
    if len(bad):
        raise ValueError(f"confidence not in {CONFIDENCE}: {list(bad)}")

    known = df["supplier_class"] != "unknown"
    url, key, sup = _blank(df["source_url"]), _blank(df["bib_key"]), _blank(df["supplier_name"])
    bad = df.loc[known & ((url == "") | (key == "")), "site_id"]
    if len(bad):
        raise ValueError(f"classified rows need source_url and bib_key: {list(bad)}")
    bad = df.loc[known & (sup == ""), "site_id"]
    if len(bad):
        raise ValueError(f"classified rows need supplier_name: {list(bad)}")
    bad = df.loc[known & (df["confidence"] == "none"), "site_id"]
    if len(bad):
        raise ValueError(f"classified rows cannot have confidence 'none': {list(bad)}")
    bad = df.loc[~known & ~sup.str.lower().isin(["", "unknown"]), "site_id"]
    if len(bad):
        raise ValueError(f"unknown rows must have supplier_name empty or 'unknown': {list(bad)}")
    bad = df.loc[~known & (df["confidence"] != "none"), "site_id"]
    if len(bad):
        raise ValueError(f"unknown rows must have confidence 'none': {list(bad)}")

    used = key[key != ""]
    if used.duplicated().any():
        raise ValueError(f"duplicate bib_key: {sorted(set(used[used.duplicated()]))}")
    bad = [k for k in used if not KEY_RE.match(k)]
    if bad:
        raise ValueError(f"bib_key not snake_case: {bad}")
    long_q = df.loc[_blank(df["evidence_quote"]).str.split().str.len() >= 20, "site_id"]
    if len(long_q):
        raise ValueError(f"evidence_quote must be under 20 words: {list(long_q)}")
    return df


def load_suppliers(path: Path = CSV, planned: Path | pd.DataFrame | None = PLANNED) -> pd.DataFrame:
    """Read and validate site_suppliers.csv against the active site list."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    expected = active_site_ids(planned) if planned is not None else None
    if expected is not None and len(expected) != N_ACTIVE:
        raise ValueError(f"planned site filter gave {len(expected)} sites, expected {N_ACTIVE}")
    return validate(df, expected)


def summarize(df: pd.DataFrame | None = None) -> dict:
    """Counts by supplier_class (and by class x confidence) plus the self-supplied site ids."""
    df = load_suppliers() if df is None else df
    by_class = {c: int((df["supplier_class"] == c).sum()) for c in CLASSES}
    by_conf = {
        f"{c}|{k}": int(((df["supplier_class"] == c) & (df["confidence"] == k)).sum())
        for c in CLASSES for k in CONFIDENCE
        if ((df["supplier_class"] == c) & (df["confidence"] == k)).any()
    }
    self_sup = df.loc[df["supplier_class"] == "self_supplied", ["site_id", "name", "supplier_name"]]
    return {
        "n_sites": int(len(df)),
        "by_class": by_class,
        "by_class_confidence": by_conf,
        "self_supplied_sites": self_sup.to_dict(orient="records"),
        "source": "data/sites/site_suppliers.csv",
    }


if __name__ == "__main__":
    s = summarize()
    out = RESULTS / "suppliers_summary.json"
    out.write_text(json.dumps(s, indent=2) + "\n")
    print(json.dumps(s["by_class"]), "->", out)
