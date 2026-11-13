"""Unit tests for the detection limit. No network, no FITS files."""

import numpy as np
import pytest

from src.limit import effective_pixels, limit_from_arrays, systematic_budget


def test_effective_pixels_matches_gaussian_area():
    # FWHM 2.0 px -> sigma 0.849 px -> 4*pi*sigma^2 = 9.06 px
    assert effective_pixels(2.0) == pytest.approx(9.06, abs=0.01)


def test_limit_scales_as_inverse_sqrt_visits():
    var = np.full((64, 64), 1e-3)
    flags = np.zeros((64, 64), dtype=int)
    one = limit_from_arrays(var, flags, 1, 2.0, "synthetic")
    four = limit_from_arrays(var, flags, 4, 2.0, "synthetic")
    assert four.flux_limit_mjy_sr_px == pytest.approx(one.flux_limit_mjy_sr_px / 2, rel=1e-6)


def test_flagged_pixels_are_excluded():
    var = np.full((64, 64), 1e-3)
    flags = np.zeros((64, 64), dtype=int)
    flags[:32, :] = 64
    lim = limit_from_arrays(var, flags, 1, 2.0, "synthetic")
    assert lim.usable_fraction == pytest.approx(0.5, abs=1e-6)


def test_no_usable_pixels_raises():
    var = np.full((8, 8), 1e-3)
    flags = np.ones((8, 8), dtype=int)
    with pytest.raises(ValueError):
        limit_from_arrays(var, flags, 1, 2.0, "synthetic")


def test_systematic_budget_brackets_the_central_value():
    var = np.full((64, 64), 1e-3)
    flags = np.zeros((64, 64), dtype=int)
    central = limit_from_arrays(var, flags, 4, 2.0, "synthetic")
    budget = systematic_budget(var, flags, 4, 2.0, "synthetic")
    assert budget["peak_min"] <= central.peak_limit_mjy_sr <= budget["peak_max"]
    assert budget["peak_max"] > budget["peak_min"]
