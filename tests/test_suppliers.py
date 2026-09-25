"""Validation rules for the site water-supplier table (data/sites/site_suppliers.csv)."""
import pandas as pd
import pytest

from reuse_ready.suppliers import CLASSES, COLUMNS, CSV, load_suppliers, summarize, validate


def _row(i, cls="public_or_authority", conf="stated_in_source", sup="Some Authority", key=None, url="https://x.org"):
    return dict(
        site_id=f"S{i:02d}", name=f"site {i}", municipality="m", supplier_name=sup, supplier_class=cls,
        confidence=conf, evidence_quote="short quote", source_url=url, source_title="t", source_publisher="p",
        source_date="2026-01-01", access_date="2026-09-25", bib_key=f"key_{i}" if key is None else key, notes="",
    )


@pytest.fixture
def table():
    rows = [_row(i) for i in range(3)]
    rows.append(_row(3, cls="self_supplied", sup="own wells"))
    rows.append(_row(4, cls="unknown", conf="none", sup="", key="", url=""))
    return pd.DataFrame(rows)[COLUMNS]


def _ids(df):
    return set(df.site_id)


def test_synthetic_table_passes(table):
    assert validate(table, _ids(table), n=5) is table


def test_row_count_enforced(table):
    with pytest.raises(ValueError, match="expected"):
        validate(table.iloc[:4], n=5)


def test_duplicate_site_id(table):
    t = table.copy()
    t.loc[1, "site_id"] = "S00"
    with pytest.raises(ValueError, match="duplicate site_id"):
        validate(t, n=5)


def test_site_ids_must_match_active_list(table):
    with pytest.raises(ValueError, match="mismatch"):
        validate(table, _ids(table) - {"S00"} | {"ZZ99"}, n=5)


def test_bad_class(table):
    t = table.copy()
    t.loc[0, "supplier_class"] = "municipal"
    with pytest.raises(ValueError, match="supplier_class"):
        validate(t, n=5)


def test_bad_confidence(table):
    t = table.copy()
    t.loc[0, "confidence"] = "likely"
    with pytest.raises(ValueError, match="confidence"):
        validate(t, n=5)


@pytest.mark.parametrize("field", ["source_url", "bib_key"])
def test_classified_rows_need_url_and_key(table, field):
    t = table.copy()
    t.loc[3, field] = ""
    with pytest.raises(ValueError, match="source_url and bib_key"):
        validate(t, n=5)


def test_unknown_rows_have_no_supplier(table):
    t = table.copy()
    t.loc[4, "supplier_name"] = "Aqua"
    with pytest.raises(ValueError, match="unknown rows"):
        validate(t, n=5)
    t.loc[4, "supplier_name"] = "unknown"
    validate(t, n=5)


def test_unknown_rows_confidence_none(table):
    t = table.copy()
    t.loc[4, "confidence"] = "inferred_service_area"
    with pytest.raises(ValueError, match="confidence 'none'"):
        validate(t, n=5)


def test_bib_keys_unique_and_snake_case(table):
    t = table.copy()
    t.loc[1, "bib_key"] = "key_0"
    with pytest.raises(ValueError, match="duplicate bib_key"):
        validate(t, n=5)
    t.loc[1, "bib_key"] = "Key-One"
    with pytest.raises(ValueError, match="snake_case"):
        validate(t, n=5)


def test_quote_under_20_words(table):
    t = table.copy()
    t.loc[0, "evidence_quote"] = " ".join(["word"] * 20)
    with pytest.raises(ValueError, match="under 20 words"):
        validate(t, n=5)


def test_summary_counts(table):
    s = summarize(table)
    assert s["by_class"] == {"public_or_authority": 3, "self_supplied": 1, "unknown": 1}
    assert [r["site_id"] for r in s["self_supplied_sites"]] == ["S03"]


@pytest.mark.skipif(not CSV.exists(), reason="site_suppliers.csv not built")
def test_repository_table_is_valid():
    df = load_suppliers()
    assert len(df) == 24
    s = summarize(df)
    assert sum(s["by_class"].values()) == 24
    assert set(s["by_class"]) == set(CLASSES)
