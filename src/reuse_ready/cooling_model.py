"""Hourly cooling-water makeup model for three data center cooling architectures.

Physics (model-derived; see results.md assumptions):
  Heat rejected to the cooling system is approximated by total facility power, Q = P_IT * PUE (MW).
  Evaporating water removes its latent heat, L_v = 2.43 MJ/kg near 30 C [engineering constant].
  Evaporation per MW of evaporatively rejected heat: 1e6 / 2.43e6 kg/s = 1.481 m3/h = 391 US gal/h.
  Makeup = evaporation * C / (C - 1), where C is cycles of concentration (blowdown = E / (C - 1)).
  Drift is neglected.

Architectures:
  evaporative_tower : all heat rejected evaporatively in every hour (phi = 1).
  hybrid            : dry cooling below switchover wet-bulb T_sw (phi = 0); above it the evaporative
                      fraction rises as a part-load curve phi = ((Twb - T_sw) / (Twb_ref - T_sw)) ** gamma,
                      clipped to [0, 1], where Twb_ref is the maximum hourly wet-bulb in the 20-year
                      KTTN record. T_sw and gamma are calibrated to the Falls Township targets.
  air_cooled_chiller: closed-loop dry heat rejection, phi = 0 in every hour (zero evaporative makeup).

WUE follows the Green Grid definition: annual site water (L) / annual IT energy (kWh) [greengrid_wue_2011].
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

L_V_MJ_PER_KG = 2.43
M3_TO_GAL = 264.172
EVAP_M3_PER_MWH = 3600.0 / (L_V_MJ_PER_KG * 1000.0)  # m3 of water per MWh of heat, = 1.4815
EVAP_GAL_PER_MWH = EVAP_M3_PER_MWH * M3_TO_GAL      # = 391.4 gal per MWh


@dataclass
class CoolingParams:
    p_it_mw: float = 100.0
    pue: float = 1.2
    cycles: float = 4.0
    t_sw_c: float = 22.0
    gamma: float = 1.0
    twb_ref_c: float = 28.6
    architecture: str = "hybrid"

    def to_dict(self) -> dict:
        return asdict(self)


def evaporative_fraction(twb_c: np.ndarray, p: CoolingParams) -> np.ndarray:
    twb = np.asarray(twb_c, dtype=float)
    if p.architecture == "evaporative_tower":
        return np.where(np.isnan(twb), np.nan, 1.0)
    if p.architecture == "air_cooled_chiller":
        return np.where(np.isnan(twb), np.nan, 0.0)
    x = (twb - p.t_sw_c) / max(p.twb_ref_c - p.t_sw_c, 1e-6)
    phi = np.clip(x, 0.0, 1.0) ** p.gamma
    return np.where(np.isnan(twb), np.nan, np.where(twb > p.t_sw_c, phi, 0.0))


def hourly_makeup_gal(twb_c: np.ndarray, p: CoolingParams) -> np.ndarray:
    """Makeup water per hour (US gal) for each hourly wet-bulb value."""
    phi = evaporative_fraction(twb_c, p)
    heat_mwh = p.p_it_mw * p.pue  # per hour
    return phi * heat_mwh * EVAP_GAL_PER_MWH * p.cycles / (p.cycles - 1.0)


def wue_l_per_kwh(p: CoolingParams, phi_mean: float) -> float:
    """Annual-mean site WUE (L per IT kWh) implied by a mean evaporative fraction."""
    return phi_mean * p.pue * EVAP_M3_PER_MWH * p.cycles / (p.cycles - 1.0)  # m3/MWh == L/kWh


def daily_makeup(weather: pd.DataFrame, p: CoolingParams, min_hours: int = 20) -> pd.DataFrame:
    """Daily makeup (gal/day) on local (America/New_York) calendar days.

    Days with fewer than `min_hours` valid wet-bulb hours are set to NaN (and counted by callers).
    Days with min_hours..23 valid hours are scaled to 24 h by the mean of the valid hours.
    """
    w = weather[["time_utc", "wetbulb_c"]].copy()
    w["local_date"] = pd.to_datetime(w.time_utc, utc=True).dt.tz_convert("America/New_York").dt.date
    w["makeup_gal"] = hourly_makeup_gal(w.wetbulb_c.to_numpy(), p)
    w["wet"] = (evaporative_fraction(w.wetbulb_c.to_numpy(), p) > 0).astype(float)
    w.loc[w.wetbulb_c.isna(), "wet"] = np.nan
    g = w.groupby("local_date").agg(n_valid=("makeup_gal", "count"), mean_gal_h=("makeup_gal", "mean"),
                                    wet_hours=("wet", "sum"))
    g["makeup_gpd"] = np.where(g.n_valid >= min_hours, g.mean_gal_h * 24.0, np.nan)
    g.index = pd.to_datetime(g.index)
    return g[["makeup_gpd", "n_valid", "wet_hours"]]
