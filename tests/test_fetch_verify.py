"""`fetch --verify` must fail on a missing file, an altered file, or an unrecorded file (temp manifest)."""
import hashlib

import pytest

from peakflow import fetch


def _manifest(raw, files):
    rows = ["# Raw data manifest", "", "| file | source_url | downloaded_utc | rows | sha256 | note |",
            "| --- | --- | --- | --- | --- | --- |"]
    for rel, data in files.items():
        rows.append(f"| {rel} | https://example.org/{rel} | 2026-09-25T00:00:00Z | 1 | "
                    f"{hashlib.sha256(data).hexdigest()} |  |")
    (raw / "MANIFEST.md").write_text("\n".join(rows) + "\n")
    return raw / "MANIFEST.md"


@pytest.fixture
def raw(tmp_path):
    r = tmp_path / "raw"
    (r / "sub").mkdir(parents=True)
    files = {"a.csv": b"x,y\n1,2\n", "sub/b.html": b"<html>b</html>"}
    for rel, data in files.items():
        (r / rel).write_bytes(data)
    return r, _manifest(r, files)


def test_verify_passes_when_all_files_match(raw):
    r, m = raw
    assert fetch.manifest_failures(m, r) == []
    assert fetch.verify_manifest(m, r) == 2


def test_verify_fails_on_missing_file(raw):
    r, m = raw
    (r / "sub" / "b.html").unlink()
    fails = fetch.manifest_failures(m, r)
    assert [(f["file"], f["problem"]) for f in fails] == [("sub/b.html", "missing")]
    with pytest.raises(SystemExit) as e:
        fetch.verify_manifest(m, r)
    assert "sub/b.html: missing" in str(e.value) and e.value.code != 0


def test_verify_fails_on_altered_file(raw):
    r, m = raw
    (r / "a.csv").write_bytes(b"x,y\n1,3\n")
    fails = fetch.manifest_failures(m, r)
    assert len(fails) == 1 and fails[0]["file"] == "a.csv" and fails[0]["problem"].startswith("sha256 mismatch")
    with pytest.raises(SystemExit):
        fetch.verify_manifest(m, r)


def test_verify_fails_on_unrecorded_file(raw):
    r, m = raw
    (r / "extra.txt").write_text("not in manifest")
    fails = fetch.manifest_failures(m, r)
    assert [(f["file"], f["problem"]) for f in fails] == [("extra.txt", "no MANIFEST row")]
    with pytest.raises(SystemExit):
        fetch.verify_manifest(m, r)


def test_every_pipeline_document_has_a_fetch_step():
    """The DRBC rule PDF, DRBC data-centers page, press pages and LBNL report are downloadable (audit G01)."""
    from peakflow import docs

    for key, path in docs.REG_FILES.items():
        rel = path.relative_to(fetch.RAW).as_posix()
        assert rel in fetch.DOCUMENTS, rel
    for rel in ("press/amazon_falls_campus_2026.html", "press/falls_herald_2026.html",
                "press/falls_keystone_2026.html", "press/falls_levittown_2026.html", "lbnl_2024.pdf"):
        assert rel in fetch.DOCUMENTS
        assert fetch.DOCUMENTS[rel][0].startswith("https://")
    assert "documents" in fetch.STEPS
