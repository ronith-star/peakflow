"""Wet-bulb temperature.

Stull, R. (2011). Wet-bulb temperature from relative humidity and air temperature.
Journal of Applied Meteorology and Climatology, 50(11), 2267-2269. doi:10.1175/JAMC-D-11-0143.1
[stull_2011]

The Stull fit is empirical at standard sea-level pressure (101.325 kPa) and is valid for
RH 5-99 % and T -20 to 50 C; its mean absolute error is below 0.3 C over that range.
Relative humidity is derived from temperature and dew point with the Magnus form of the
saturation vapour pressure (Alduchov and Eskridge 1996 coefficients) [alduchov_1996].
Station pressure is carried in the processed data but, consistent with the Stull method,
is not used in the wet-bulb calculation; this is stated as an assumption in results.md.
"""
from __future__ import annotations

import numpy as np

MAGNUS_A = 17.625
MAGNUS_B = 243.04  # deg C


def rh_from_dewpoint(t_c, td_c):
    """Relative humidity (%) from air temperature and dew point (deg C), Magnus form."""
    t_c = np.asarray(t_c, dtype=float)
    td_c = np.asarray(td_c, dtype=float)
    es = np.exp(MAGNUS_A * t_c / (MAGNUS_B + t_c))
    e = np.exp(MAGNUS_A * td_c / (MAGNUS_B + td_c))
    return np.clip(100.0 * e / es, 0.0, 100.0)


def stull_wetbulb(t_c, rh_pct):
    """Wet-bulb temperature (deg C) from air temperature (deg C) and RH (%), Stull (2011) eq. 1."""
    t = np.asarray(t_c, dtype=float)
    rh = np.asarray(rh_pct, dtype=float)
    return (
        t * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
        + np.arctan(t + rh)
        - np.arctan(rh - 1.676331)
        + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh)
        - 4.686035
    )


def wetbulb_from_dewpoint(t_c, td_c):
    return stull_wetbulb(t_c, rh_from_dewpoint(t_c, td_c))
