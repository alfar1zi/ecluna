"""Unit tests for the completeness measurement. No network, no FITS files."""

import numpy as np
import pytest

from src.inject import (completeness, gaussian_psf, inject, interpolate_f50,
                        wilson, Level)


def test_psf_sums_to_one():
    kernel = gaussian_psf(2.0)
    assert kernel.sum() == pytest.approx(1.0, rel=1e-9)
    assert kernel.shape[0] % 2 == 1


def test_inject_adds_the_requested_flux():
    cube = np.zeros((3, 32, 32), dtype=np.float32)
    variance = np.ones_like(cube)
    filled, _ = inject(cube, variance, 16.0, 16.0, 0.0, 0.0, flux=2.0)
    assert filled.sum() == pytest.approx(2.0 * 3, rel=1e-5)


def test_inject_does_not_modify_the_input():
    cube = np.zeros((3, 32, 32), dtype=np.float32)
    variance = np.ones_like(cube)
    inject(cube, variance, 16.0, 16.0, 0.0, 0.0, flux=2.0)
    assert cube.sum() == 0.0


def test_inject_returns_none_when_the_track_leaves_the_grid():
    cube = np.zeros((3, 32, 32), dtype=np.float32)
    variance = np.ones_like(cube)
    filled, _ = inject(cube, variance, 30.0, 16.0, 5.0, 0.0, flux=1.0)
    assert filled is None


def test_wilson_interval_brackets_the_estimate():
    low, high = wilson(50, 100)
    assert low < 0.5 < high
    assert 0.39 < low < 0.42
    assert 0.58 < high < 0.61


def test_wilson_handles_zero_trials():
    assert wilson(0, 0) == (0.0, 1.0)


def test_f50_interpolates_a_rising_curve():
    levels = [
        Level(flux=0.1, injected=100, recovered=10, completeness=0.10,
              wilson_low=0.05, wilson_high=0.18),
        Level(flux=0.2, injected=100, recovered=90, completeness=0.90,
              wilson_low=0.82, wilson_high=0.95),
    ]
    f50, ci = interpolate_f50(levels)
    assert f50 == pytest.approx(0.15, abs=1e-6)
    assert ci is not None


def test_completeness_rises_with_flux():
    rng = np.random.default_rng(5)
    cube = rng.normal(0.0, 1.0, (5, 64, 64)).astype(np.float32)
    variance = np.ones_like(cube)
    curve = completeness(cube, variance, threshold=3.0,
                         fluxes=[0.5, 5.0], per_level=40, field="synthetic")
    low, high = curve.levels[0], curve.levels[1]
    assert high.completeness > low.completeness
    assert curve.status == "measured"
