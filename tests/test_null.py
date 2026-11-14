"""Unit tests for the null calibration. No network, no FITS files."""

import numpy as np
import pytest

from src.null import calibrate, noise_scale, subtract_background, track_statistic


def synthetic_cube(visits=5, ny=64, nx=64, sigma=1.0, seed=3):
    rng = np.random.default_rng(seed)
    cube = rng.normal(0.0, sigma, (visits, ny, nx)).astype(np.float32)
    variance = np.full_like(cube, sigma ** 2)
    return cube, variance


def test_track_statistic_is_zero_for_a_flat_track():
    cube = np.zeros((4, 32, 32), dtype=np.float32)
    variance = np.ones_like(cube)
    assert track_statistic(cube, variance, 10.0, 10.0, 0.0, 0.0) == pytest.approx(0.0)


def test_track_statistic_recovers_a_psf_shaped_signal():
    from src.inject import inject

    cube = np.zeros((4, 32, 32), dtype=np.float32)
    variance = np.ones_like(cube)
    # A source drawn with the PSF, total flux 5 per visit over four visits. A
    # matched filter spreads the flux over the effective pixels under the PSF, so
    # the signal-to-noise is F * sqrt(N) / sqrt(N_eff), not F * sqrt(N).
    from src.limit import effective_pixels

    filled, filled_var = inject(cube, variance, 16.0, 16.0, 0.0, 0.0, flux=5.0)
    value = track_statistic(filled, filled_var, 16.0, 16.0, 0.0, 0.0)
    expected = 5.0 * np.sqrt(4) / np.sqrt(effective_pixels(2.0))
    assert value == pytest.approx(expected, rel=0.05)


def test_track_statistic_returns_nan_outside_the_grid():
    cube = np.zeros((4, 32, 32), dtype=np.float32)
    variance = np.ones_like(cube)
    assert np.isnan(track_statistic(cube, variance, 31.0, 31.0, 5.0, 0.0))


def test_subtract_background_removes_a_constant_offset():
    cube = np.full((3, 32, 32), 0.1, dtype=np.float32)
    flat = subtract_background(cube, box=9)
    assert np.nanmax(np.abs(flat)) < 1e-6


def test_noise_scale_is_one_when_variance_matches_the_data():
    cube, variance = synthetic_cube(sigma=1.0)
    scale = noise_scale(cube, variance)
    assert scale["scale"] == pytest.approx(1.0, abs=0.15)


def test_noise_scale_detects_an_underestimated_variance():
    cube, variance = synthetic_cube(sigma=3.0)
    variance = variance / 9.0          # archive claims sigma = 1
    scale = noise_scale(cube, variance)
    assert scale["scale"] == pytest.approx(3.0, abs=0.4)


def test_calibrate_measures_a_threshold_for_white_noise():
    cube, variance = synthetic_cube(sigma=1.0, visits=6)
    result = calibrate(cube, variance, "synthetic", tracks=400)
    assert result.tracks > 100
    assert result.status == "measured"
    # White noise gives a threshold of the same order as the Gaussian one.
    assert 0.5 < result.s_p95 < 3.0


def test_calibrate_exceeds_the_gaussian_value_for_heavy_tails():
    # Real survey noise has heavier tails than a normal distribution, and that is
    # the case the empirical calibration exists for.
    rng = np.random.default_rng(11)
    cube = rng.standard_t(df=3, size=(6, 64, 64)).astype(np.float32)
    variance = np.ones_like(cube)
    result = calibrate(cube, variance, "synthetic", tracks=600)
    assert result.s_p95 > result.gaussian_p95
