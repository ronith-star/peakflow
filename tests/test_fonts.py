"""Every figure PDF embeds only the approved font stack (Helvetica/Arial/Liberation Sans and the narrow
variants); the Inter UI typeface, and any other UI font, must not appear."""
import re

import pytest

from reuse_ready.paths import FIGURES

PDFS = sorted(FIGURES.glob("*.pdf"))
ALLOWED = ("Helvetica", "Arial", "ArialNarrow", "ArialMT", "Arial-Narrow", "LiberationSans", "LiberationSansNarrow")
BANNED = ("Inter", "DejaVu", "Roboto", "SFPro", "SegoeUI", "OpenSans")


def base_fonts(pdf) -> set[str]:
    raw = pdf.read_bytes()
    return {m.decode("latin-1").split("+")[-1] for m in re.findall(rb"/BaseFont\s*/([A-Za-z0-9+\-_,]+)", raw)}


@pytest.mark.skipif(not PDFS, reason="figures not built")
@pytest.mark.parametrize("pdf", PDFS, ids=[p.name for p in PDFS])
def test_pdf_fonts_allowed(pdf):
    fonts = base_fonts(pdf)
    assert fonts, f"{pdf.name}: no /BaseFont found"
    bad = sorted(f for f in fonts if any(f.startswith(b) for b in BANNED))
    assert not bad, f"{pdf.name} embeds banned fonts {bad}"
    other = sorted(f for f in fonts if not f.startswith(ALLOWED))
    assert not other, f"{pdf.name} embeds fonts outside the approved stack {other}"
