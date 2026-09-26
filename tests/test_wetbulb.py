"""Stull (2011) wet-bulb: published worked example and array/NaN behavior."""
import numpy as np

from peakflow.wetbulb import rh_from_dewpoint, stull_wetbulb, wetbulb_from_dewpoint


def test_stull_worked_example():
    # Stull (2011): T = 20 C, RH = 50 % gives Tw = 13.7 C.
    assert abs(float(stull_wetbulb(20.0, 50.0)) - 13.7) < 0.1


def test_vectorised_and_nan():
    t = np.array([20.0, np.nan, 30.0, 10.0])
    rh = np.array([50.0, 50.0, np.nan, 100.0])
    tw = stull_wetbulb(t, rh)
    assert tw.shape == (4,)
    assert np.isnan(tw[1]) and np.isnan(tw[2])
    assert abs(tw[0] - 13.7) < 0.1
    assert abs(tw[3] - 10.0) < 0.5  # saturated air: Tw ~ T (Stull fit error < 0.3-0.5 C near RH 100)


def test_dewpoint_path_bounds():
    t = np.array([25.0, 25.0, np.nan])
    td = np.array([25.0, 10.0, 5.0])
    rh = rh_from_dewpoint(t, td)
    assert abs(rh[0] - 100.0) < 1e-9 and np.isnan(rh[2])
    tw = wetbulb_from_dewpoint(t, td)
    assert td[1] <= tw[1] <= t[1]
