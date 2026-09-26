"""Shared figure styling: font selection, palette constants, color-vision-deficiency check.

Font: Helvetica, falling back to Arial, then Liberation Sans, for all figures; Arial Narrow, falling back to
Liberation Sans Narrow, for site numbers and city labels on maps. These are system fonts and are not
redistributed in this repository. If none of the three families is installed, DejaVu Sans (bundled with
matplotlib) is used and a warning is printed; rendered text widths then differ slightly from the published
figures. Regular weight throughout; bold is used only for legend headings and the table headline.

Palettes: the table constants (WWTP, SITE, RIVER, ACCENT, INK, MUTED, RULE) serve the blind-spot table and
peakflow.plotting.supply_map; the FIG_* constants (black, grays, one blue-gray for water, one deep-blue accent)
serve the technical-style figures. The CVD check simulates deuteranomaly, protanomaly and tritanomaly at severity 100
(Machado et al. 2009 via colorspacious) and reports the minimum pairwise CAM02-UCS delta-E'.
"""
from __future__ import annotations

from itertools import combinations


FONT_FAMILY_PREFERENCE = ["Helvetica", "Arial", "Liberation Sans"]
NARROW_FAMILY_PREFERENCE = ["Arial Narrow", "Liberation Sans Narrow"]

WWTP = "#237A70"     # muted teal
SITE = "#D9822B"     # warm accent (orange)
RIVER = "#8FA3B8"    # blue-gray
ACCENT = "#F6DDBF"   # table accent fill (light tint of SITE)
INK = "#1F2328"
MUTED = "#5F6670"
RULE = "#C9CDD2"

# Typography ladder (points). Title is the only larger size; body and subtitle share one size, and
# small text (column headers, footnotes) shares one size with the source line, so a figure uses three sizes.
TITLE_SIZE = 11.0
SUBTITLE_SIZE = 8.5
BODY_SIZE = 8.5
SMALL_SIZE = 7.0
SOURCE_SIZE = 7.0
FIG_MARGIN_IN = 0.2  # left/bottom inset (inches) for figure-level text such as the source line

PALETTE = {"wwtp": WWTP, "site": SITE, "river": RIVER, "accent": ACCENT, "ink": INK}
CVD_TYPES = ("deuteranomaly", "protanomaly", "tritanomaly")
MIN_DELTA_E = 10.0  # acceptance threshold in CAM02-UCS units for "distinguishable at a glance"


def register_fonts() -> str:
    """Select the figure font (Helvetica, then Arial, then Liberation Sans) and return its family name.
    Only system-installed fonts are considered; no bundled UI fonts are registered."""
    import sys
    import matplotlib as mpl
    from matplotlib import font_manager as fm

    names = {f.name for f in fm.fontManager.ttflist}
    family = next((n for n in FONT_FAMILY_PREFERENCE if n in names), None)
    if family is None:
        print("styles: Helvetica, Arial and Liberation Sans not found; using DejaVu Sans", file=sys.stderr)
        family = "DejaVu Sans"
    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["font.sans-serif"] = [family] + [n for n in FONT_FAMILY_PREFERENCE if n != family] + ["DejaVu Sans"]
    mpl.rcParams["font.weight"] = "normal"
    mpl.rcParams["pdf.fonttype"] = 42
    mpl.rcParams["ps.fonttype"] = 42
    # fontTools logs harmless table-parsing notices while subsetting the macOS system Helvetica for PDF
    # output ("1 extra bytes in post.stringData array", "'created' timestamp seems very low"); keep errors.
    import logging
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    return family


def narrow_family() -> str:
    """Condensed family for map site numbers and city labels (Arial Narrow, then Liberation Sans Narrow)."""
    from matplotlib import font_manager as fm
    names = {f.name for f in fm.fontManager.ttflist}
    return next((n for n in NARROW_FAMILY_PREFERENCE if n in names), register_fonts())


def source_line(fig, keys, extra: str = "", y_in: float = FIG_MARGIN_IN, x_in: float = FIG_MARGIN_IN):
    """Draw the standard source line at the bottom-left of `fig`: 'Sources: [k1]; [k2]. <extra>'.

    `keys` are citation keys from references.bib; `extra` is an optional complete sentence (for example
    a pointer to a repository file). Returns the matplotlib Text object so callers can measure it."""
    w_in, h_in = fig.get_size_inches()
    txt = "Sources: " + "; ".join(f"[{k}]" for k in keys) + "."
    if extra:
        txt += " " + extra.strip()
    return fig.text(x_in / w_in, y_in / h_in, txt, ha="left", va="bottom", fontsize=SOURCE_SIZE,
                    color=MUTED)


def _hex_to_rgb1(h: str):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def cvd_check(colors: dict | None = None, severity: int = 100) -> dict:
    """Minimum pairwise CAM02-UCS delta-E among `colors` for normal vision and each simulated CVD."""
    import warnings

    import numpy as np
    with warnings.catch_warnings():  # colorspacious 1.1.2 comparison.py has an invalid escape in a docstring
        warnings.simplefilter("ignore", SyntaxWarning)
        from colorspacious import cspace_convert, deltaE

    colors = colors or {k: v for k, v in PALETTE.items()}
    out = {}
    for cvd in ("normal",) + CVD_TYPES:
        rgb = {k: np.array(_hex_to_rgb1(v)) for k, v in colors.items()}
        if cvd != "normal":
            space = {"name": "sRGB1+CVD", "cvd_type": cvd, "severity": severity}
            rgb = {k: np.clip(cspace_convert(v, space, "sRGB1"), 0, 1) for k, v in rgb.items()}
        pairs = {f"{a}-{b}": float(deltaE(rgb[a], rgb[b], input_space="sRGB1"))
                 for a, b in combinations(rgb, 2)}
        worst = min(pairs, key=pairs.get)
        out[cvd] = {"min_delta_e": pairs[worst], "min_pair": worst}
    out["overall_min_delta_e"] = min(v["min_delta_e"] for v in out.values() if isinstance(v, dict))
    out["threshold"] = MIN_DELTA_E
    out["passes"] = out["overall_min_delta_e"] >= MIN_DELTA_E
    out["severity"] = severity
    return out


if __name__ == "__main__":
    import json

    print(register_fonts())
    print(json.dumps(cvd_check(), indent=2))


# ---------------------------------------------------------------------------------------------------------------
# Technical figure style (report figures in the manner of a USGS Scientific Investigations Report).
# No titles, subtitles, citation keys, file paths or sentences inside images; all explanation lives in
# figures/<name>_caption.md. One sans-serif font at 7 to 8 pt; bold only for legend headings.
# Palette: black, grays, one muted blue-gray for water, one accent. Line weights in points.
FIG_BLACK = "#000000"
FIG_GRAY_DARK = "#4D4D4D"      # state lines, city and river type
FIG_GRAY = "#8C8C8C"           # 10-mile radii, tick labels secondary
FIG_GRAY_LIGHT = "#C4C4C4"     # county lines
FIG_OUTSIDE = "#E8E8E8"        # flat fill outside the basin
FIG_WATER = "#AABFD1"          # rivers, bay, reservoirs (delta-E 12.1 from the mid-tone site fill, 11.9 worst CVD)
FIG_ACCENT = "#1F3A5F"         # deep blue
FIG_ACCENT_HALF = "#8F9CAF"    # 50 percent tint of the accent on white ("half-tone")
FIG_FILL = {"over 200 MW": FIG_ACCENT, "50 to 200 MW": FIG_ACCENT_HALF, "no eligible plant within 10 mi": "#FFFFFF"}
FIG_BIN_ORDER = ["over 200 MW", "50 to 200 MW", "no eligible plant within 10 mi"]
FIG_LW_PRIMARY = 0.8
FIG_LW_SECONDARY = 0.5
FIG_LW_TERTIARY = 0.25
FIG_FONT_SIZE = 7.0
FIG_DASH = (0, (2.2, 1.4))
FIG_HATCH = "/"                # lowest-density single diagonal
FIG_HATCH_LW = 0.3
FIG_DPI = 300
MM_PER_IN = 25.4


def figure_rc():
    """Matplotlib rcParams for the technical figure style; returns the registered font family."""
    import matplotlib as mpl
    mpl.rcParams["svg.hashsalt"] = "peakflow"  # deterministic SVG ids
    fam = register_fonts()
    mpl.rcParams.update({
        "font.size": FIG_FONT_SIZE, "axes.labelsize": FIG_FONT_SIZE, "xtick.labelsize": FIG_FONT_SIZE,
        "ytick.labelsize": FIG_FONT_SIZE, "legend.fontsize": FIG_FONT_SIZE, "font.weight": "normal",
        "axes.linewidth": FIG_LW_SECONDARY, "xtick.major.width": FIG_LW_SECONDARY,
        "ytick.major.width": FIG_LW_SECONDARY, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.color": FIG_BLACK, "ytick.color": FIG_BLACK, "axes.edgecolor": FIG_BLACK, "text.color": FIG_BLACK,
        "hatch.color": FIG_BLACK, "hatch.linewidth": FIG_HATCH_LW, "savefig.dpi": FIG_DPI,
        "svg.fonttype": "none", "pdf.fonttype": 42, "axes.unicode_minus": False,
    })
    return fam


def figure_source_line(fig, text: str, y_mm: float = 1.5, x_mm: float = 2.0):
    """The single short source line at the bottom-left of a technical-style figure, e.g. 'Sources: DRBC; U.S. EPA ECHO.'"""
    w_in, h_in = fig.get_size_inches()
    return fig.text(x_mm / MM_PER_IN / w_in, y_mm / MM_PER_IN / h_in, text, ha="left", va="bottom",
                    fontsize=FIG_FONT_SIZE, color=FIG_BLACK)
