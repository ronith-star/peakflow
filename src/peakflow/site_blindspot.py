"""Per-site DRBC blind-spot test for the 24 active planned sites.

For each site in results/supply_screen.csv the calibrated hybrid (results/calibration.json 'primary') is run at the
site's it_mw (stated campus MW / PUE, or an assumed 100 MW IT; column capacity_basis). At fixed PUE, cycles and
climate, makeup is exactly proportional to IT load, so one 1-MW daily series (blindspot.daily_series, KTTN
2005-2024 local days, days with < 20 valid hours NaN) is scaled by it_mw.

Columns (same rules as blindspot.summarize):
  r30_max_gpd               maximum trailing 30-day mean, computed when >= 27 of the 30 days are valid
  peak_day_max_gpd          maximum single day
  days_per_year_30day_over  days whose trailing 30-day mean exceeds 100,000 gal/day, divided by valid
                            window-years (valid windows / 365.25)
  below_trigger_30day       r30_max_gpd <= 100,000 (excluded from review under 18 CFR 401.35(a)(2)-(3))
  averaging_blind_spot      below_trigger_30day and peak_day_max_gpd > 100,000
  review_if_self_supplied   not below_trigger_30day

Supplier join: data/sites/site_suppliers.csv (compiled by hand from published sources and validated by
peakflow.suppliers) supplies supplier_class (public_or_authority, self_supplied, unknown). A site that purchases
from a public or authority system is not itself a withdrawal project and needs no DRBC review
[drbc_datacenters_2026; drbc_admin_manual].
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from . import blindspot as B
from .paths import RESULTS, SITES

OUT_COLS = ["site_id", "name", "it_mw", "capacity_basis", "r30_max_gpd", "peak_day_max_gpd",
            "days_per_year_30day_over", "below_trigger_30day", "averaging_blind_spot", "review_if_self_supplied"]
SUPPLIERS = SITES / "site_suppliers.csv"
SUPPLIER_CLASSES = ("public_or_authority", "self_supplied", "unknown")


def per_mw_series(name: str = "primary") -> pd.Series:
    w, cal, _, _ = B.load_inputs(name)
    return B.daily_series(w, B.config_params(1.0, "hybrid", cal))


def site_metrics(d1: pd.Series, it_mw: float) -> dict:
    d = d1 * float(it_mw)
    r30 = d.rolling(B.WINDOW_DAYS, min_periods=B.WINDOW_MIN_VALID).mean()
    r30_max, peak = float(r30.max()), float(d.max())
    below = r30_max <= B.TRIGGER_GPD
    return {"r30_max_gpd": r30_max, "peak_day_max_gpd": peak,
            "days_per_year_30day_over": float((r30 > B.TRIGGER_GPD).sum() / (r30.notna().sum() / 365.25)),
            "below_trigger_30day": bool(below), "averaging_blind_spot": bool(below and peak > B.TRIGGER_GPD),
            "review_if_self_supplied": bool(not below)}


def run_sites(d1: pd.Series | None = None, screen: pd.DataFrame | None = None) -> pd.DataFrame:
    d1 = per_mw_series() if d1 is None else d1
    ss = pd.read_csv(RESULTS / "supply_screen.csv") if screen is None else screen
    rows = [{"site_id": r.site_id, "name": r.name, "it_mw": float(r.it_mw), "capacity_basis": r.capacity_basis,
             **site_metrics(d1, r.it_mw)} for r in ss.itertuples()]
    return pd.DataFrame(rows, columns=OUT_COLS)


def band_mw(d1: pd.Series) -> tuple[float, float]:
    """IT-load band (MW) of the averaging blind spot: trigger / per-MW max day to trigger / per-MW max 30-day mean."""
    r30 = d1.rolling(B.WINDOW_DAYS, min_periods=B.WINDOW_MIN_VALID).mean()
    return B.TRIGGER_GPD / float(d1.max()), B.TRIGGER_GPD / float(r30.max())


def wait_for_suppliers(path: Path = SUPPLIERS, timeout_s: float = 1800.0, poll_s: float = 30.0) -> bool:
    """Optional wait for data/sites/site_suppliers.csv when that file is produced separately.

    Polls every poll_s seconds until the file has rows with site_id and supplier_class, and returns False after
    timeout_s. The Makefile passes --no-wait, so the build reads the file only if it is present.
    """
    t0 = time.time()
    while True:
        if path.exists() and path.stat().st_size > 0:
            try:
                s = pd.read_csv(path)
                if {"site_id", "supplier_class"} <= set(s.columns) and len(s):
                    return True
            except Exception:  # file incomplete or unreadable; retry
                pass
        if time.time() - t0 >= timeout_s:
            return False
        time.sleep(poll_s)


def join_suppliers(t: pd.DataFrame, path: Path = SUPPLIERS) -> tuple[pd.DataFrame, dict]:
    s = pd.read_csv(path, dtype={"site_id": str})
    keep = ["site_id", "supplier_class"] + [c for c in ("supplier_name", "confidence", "source_url", "bib_key")
                                            if c in s.columns]
    j = t.merge(s[keep].drop_duplicates("site_id"), on="site_id", how="left")
    j["supplier_class"] = j.supplier_class.fillna("unknown")
    j["review_under_supplier_class"] = j.review_if_self_supplied & (j.supplier_class == "self_supplied")
    j["purchased_supply_blind_spot"] = j.review_if_self_supplied & (j.supplier_class == "public_or_authority")
    rev = j[j.review_if_self_supplied]
    counts = {"n_sites": int(len(j)), "n_review_if_self_supplied": int(len(rev)),
              **{f"n_review_if_self_supplied_and_{c}": int((rev.supplier_class == c).sum()) for c in SUPPLIER_CLASSES},
              **({f"n_review_if_self_supplied_and_{c}_by_confidence": rev[rev.supplier_class == c]
                  .confidence.fillna("none").value_counts().to_dict() for c in SUPPLIER_CLASSES}
                 if "confidence" in rev.columns else {}),
              "n_supplier_class_not_in_vocabulary": int((~j.supplier_class.isin(SUPPLIER_CLASSES)).sum()),
              "n_sites_missing_from_supplier_file": int((~j.site_id.isin(s.site_id)).sum())}
    return j, counts


def run(wait: bool = True, timeout_s: float = 1800.0) -> dict:
    d1 = per_mw_series()
    t = run_sites(d1)
    t.to_csv(RESULTS / "site_blindspot.csv", index=False)
    lo, hi = band_mw(d1)
    out = {"calibration": "primary", "n_sites": int(len(t)),
           "n_below_trigger_30day": int(t.below_trigger_30day.sum()),
           "n_averaging_blind_spot": int(t.averaging_blind_spot.sum()),
           "n_review_if_self_supplied": int(t.review_if_self_supplied.sum()),
           "n_assumed_100MW": int((t.capacity_basis == "assumed_100MW_IT").sum()),
           "blind_spot_band_mw": [lo, hi], "min_it_mw": float(t.it_mw.min()),
           "r30_max_gpd_per_mw": float(t.r30_max_gpd.iloc[0] / t.it_mw.iloc[0]),
           "peak_day_max_gpd_per_mw": float(t.peak_day_max_gpd.iloc[0] / t.it_mw.iloc[0]),
           "days_per_year_30day_over_range": [float(t.days_per_year_30day_over.min()),
                                              float(t.days_per_year_30day_over.max())]}
    have = wait_for_suppliers(timeout_s=timeout_s) if wait else (SUPPLIERS.exists())
    if have:
        j, c = join_suppliers(t)
        j.to_csv(RESULTS / "site_blindspot_suppliers.csv", index=False)
        out["suppliers"] = {"status": "joined", "file": "data/sites/site_suppliers.csv", **c}
    else:
        out["suppliers"] = {"status": "pending", "file": "data/sites/site_suppliers.csv",
                            "note": "supplier file not present; supplier counts not computed"}
    (RESULTS / "site_blindspot_summary.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    import sys

    print(json.dumps(run(wait="--no-wait" not in sys.argv), indent=1))
