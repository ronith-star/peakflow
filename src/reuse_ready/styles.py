"""Shared figure styling: font selection, palette constants, color-vision-deficiency check.

Font: Helvetica, falling back to Arial, then Liberation Sans, for all figures; Arial Narrow, falling back to
Liberation Sans Narrow, for site numbers and city labels on maps. These are system fonts and are not
redistributed in this repository. If none of the three families is installed, DejaVu Sans (bundled with
matplotlib) is used and a warning is printed; rendered text widths then differ slightly from the published
figures. Regular weight throughout; bold is used only for legend headings and the table headline.

Palettes: the v1 constants (WWTP, SITE, RIVER, ACCENT, INK, MUTED, RULE) serve the blind-spot table and the
v1 map; the V2_* constants (black, grays, one blue-gray for water, one deep-blue accent) serve the v2 and v3
technical figures. The CVD check simulates deuteranomaly, protanomaly and tritanomaly at severity 100
(Machado et al. 2009 via colorspacious) and reports the minimum pairwise CAM02-UCS delta-E'.
"""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

from .paths import ROOT

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
# V2 technical style (report figures in the manner of a USGS Scientific Investigations Report).
# No titles, subtitles, citation keys, file paths or sentences inside images; all explanation lives in
# figures/<name>_caption.md. One sans-serif font at 7 to 8 pt; bold only for legend headings.
# Palette: black, grays, one muted blue-gray for water, one accent. Line weights in points.
V2_BLACK = "#000000"
V2_GRAY_DARK = "#4D4D4D"      # state lines, city and river type
V2_GRAY = "#8C8C8C"           # 10-mile radii, tick labels secondary
V2_GRAY_LIGHT = "#C4C4C4"     # county lines
V2_OUTSIDE = "#E8E8E8"        # flat fill outside the basin
V2_WATER = "#AABFD1"          # rivers, bay, reservoirs (delta-E 12.1 from the mid-tone site fill, 11.9 worst CVD)
V2_ACCENT = "#1F3A5F"         # deep blue
V2_ACCENT_HALF = "#8F9CAF"    # 50 percent tint of the accent on white ("half-tone")
V2_FILL = {"over 200 MW": V2_ACCENT, "50 to 200 MW": V2_ACCENT_HALF, "no eligible plant within 10 mi": "#FFFFFF"}
V2_BIN_ORDER = ["over 200 MW", "50 to 200 MW", "no eligible plant within 10 mi"]
V2_LW_PRIMARY = 0.8
V2_LW_SECONDARY = 0.5
V2_LW_TERTIARY = 0.25
V2_FONT_SIZE = 7.0
V2_DASH = (0, (2.2, 1.4))
V2_HATCH = "/"                # lowest-density single diagonal
V2_HATCH_LW = 0.3
V2_DPI = 300
MM_PER_IN = 25.4


def v2_rc():
    """Matplotlib rcParams for the v2 technical style; returns the registered font family."""
    import matplotlib as mpl
    mpl.rcParams["svg.hashsalt"] = "reuse-ready"  # deterministic SVG ids
    fam = register_fonts()
    mpl.rcParams.update({
        "font.size": V2_FONT_SIZE, "axes.labelsize": V2_FONT_SIZE, "xtick.labelsize": V2_FONT_SIZE,
        "ytick.labelsize": V2_FONT_SIZE, "legend.fontsize": V2_FONT_SIZE, "font.weight": "normal",
        "axes.linewidth": V2_LW_SECONDARY, "xtick.major.width": V2_LW_SECONDARY,
        "ytick.major.width": V2_LW_SECONDARY, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.color": V2_BLACK, "ytick.color": V2_BLACK, "axes.edgecolor": V2_BLACK, "text.color": V2_BLACK,
        "hatch.color": V2_BLACK, "hatch.linewidth": V2_HATCH_LW, "savefig.dpi": V2_DPI,
        "svg.fonttype": "none", "pdf.fonttype": 42, "axes.unicode_minus": False,
    })
    return fam


def v2_source_line(fig, text: str, y_mm: float = 1.5, x_mm: float = 2.0):
    """The single short source line at the bottom-left of a v2 figure, e.g. 'Sources: DRBC; U.S. EPA ECHO.'"""
    w_in, h_in = fig.get_size_inches()
    return fig.text(x_mm / MM_PER_IN / w_in, y_mm / MM_PER_IN / h_in, text, ha="left", va="bottom",
                    fontsize=V2_FONT_SIZE, color=V2_BLACK)


# Color-vision check sets for the v2 and v3 maps (colors unchanged since v2; audit G20, 2026-09-25).
# FILL-ENCODED colors carry meaning by fill alone (the three site-coverage fills and water) and must be at least
# MIN_DELTA_E apart. OUTLINE-SEPARATED pairs never meet without a black line between them, so their fill
# contrast is a redundant cue: the basin interior (white, which is also the "open" site fill) meets the outside
# fill V2_OUTSIDE only along the basin boundary, drawn in V2_BLACK at V2_LW_PRIMARY, and every site square has a
# black outline. Their delta-E is reported, not tested against the threshold.
V2_CVD_FILLS = {"accent": V2_ACCENT, "half": V2_ACCENT_HALF, "open": "#FFFFFF", "water": V2_WATER}
V2_CVD_OUTLINE_SEPARATED = {
    ("open", "outside"): "basin boundary line (V2_BLACK, V2_LW_PRIMARY) and the black outline of every site square",
}


def v2_cvd_check() -> dict:
    """CVD check of the v2/v3 map palette: the fill-encoded set is tested against MIN_DELTA_E; the
    outline-separated pairs (V2_CVD_OUTLINE_SEPARATED) are reported with their minimum delta-E and separator."""
    out = cvd_check(V2_CVD_FILLS)
    named = dict(V2_CVD_FILLS, outside=V2_OUTSIDE)
    out["outline_separated"] = []
    for (a, b), sep in V2_CVD_OUTLINE_SEPARATED.items():
        r = cvd_check({a: named[a], b: named[b]})
        out["outline_separated"].append({"pair": f"{a}-{b}", "min_delta_e": r["overall_min_delta_e"],
                                         "separator": sep})
    out["tested_set"] = sorted(V2_CVD_FILLS)
    return out
