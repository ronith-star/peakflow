"""The project is named PeakFlow. The full title appears in exactly three places, and the old name nowhere
in the documentation, results or captions. The Python package keeps its name (reuse_ready)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = ("PeakFlow: Probabilistic Peak-Demand Modeling for Data Center Water Policy in the Delaware River Basin")
TITLE_FILES = {"README.md", "CITATION.cff", "references.bib"}
OLD = ("Reuse-Ready", "Reuse Ready", "ReuseReady")


def _docs():
    fs = [ROOT / p for p in ("README.md", "CITATION.cff", "references.bib", "sources.md", "pyproject.toml",
                              "Makefile", "results/results.md", "results/brief_numbers.md")]
    return [f for f in fs + sorted((ROOT / "figures").glob("*_caption.md")) if f.exists()]


def test_full_title_in_exactly_three_places():
    hits = {f.relative_to(ROOT).as_posix(): f.read_text().count(TITLE) for f in _docs()}
    assert {k for k, v in hits.items() if v} == TITLE_FILES, hits
    assert all(hits[k] == 1 for k in TITLE_FILES), hits
    assert (ROOT / "README.md").read_text().splitlines()[0] == "# " + TITLE


def test_old_name_absent():
    bad = [f.relative_to(ROOT).as_posix() for f in _docs() if any(o in f.read_text() for o in OLD)]
    assert not bad, bad
