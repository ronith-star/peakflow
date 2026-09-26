"""The project and its Python package are named PeakFlow (package: peakflow). The full title appears in exactly
three places, and the old name nowhere in the repository's source, documentation, results or captions."""
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = ("PeakFlow: Probabilistic Peak-Demand Modeling for Data Center Water Policy in the Delaware River Basin")
TITLE_FILES = {"README.md", "CITATION.cff", "references.bib"}
# Built from parts so this file does not match itself; covers every separator and case variant.
OLD = re.compile("reuse" r"[\W_]?" "ready", re.IGNORECASE)
# Downloaded data, derived data, working files and caches are outside the scan.
SKIP_DIRS = {".git", "scratch", "__pycache__", ".pytest_cache", ".ipynb_checkpoints"}
SKIP_PREFIXES = ("data/raw/", "data/processed/")


def _docs():
    fs = [ROOT / p for p in ("README.md", "LICENSES.md", "CITATION.cff", "references.bib", "sources.md", "pyproject.toml",
                              "Makefile", "results/results.md", "results/brief_numbers.md")]
    return [f for f in fs + sorted((ROOT / "figures").glob("*_caption.md")) if f.exists()]


def _repo_files():
    for f in sorted(ROOT.rglob("*")):
        rel = f.relative_to(ROOT).as_posix()
        if f.is_file() and not SKIP_DIRS & set(f.relative_to(ROOT).parts) and not rel.startswith(SKIP_PREFIXES):
            yield f, rel


def test_full_title_in_exactly_three_places():
    hits = {f.relative_to(ROOT).as_posix(): f.read_text().count(TITLE) for f in _docs()}
    assert {k for k, v in hits.items() if v} == TITLE_FILES, hits
    assert all(hits[k] == 1 for k in TITLE_FILES), hits
    assert (ROOT / "README.md").read_text().splitlines()[0] == "# " + TITLE


def test_package_is_peakflow():
    assert (ROOT / "src" / "peakflow" / "__init__.py").is_file()
    assert [p.name for p in (ROOT / "src").iterdir() if (p / "__init__.py").is_file()] == ["peakflow"]
    assert importlib.import_module("peakflow").__name__ == "peakflow"
    assert re.search(r'^name = "peakflow"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE)


def test_old_name_absent():
    bad = []
    for f, rel in _repo_files():
        if OLD.search(rel):
            bad.append(rel)
            continue
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue
        bad += [f"{rel}:{i}" for i, line in enumerate(text.splitlines(), 1) if OLD.search(line)]
    assert not bad, bad
