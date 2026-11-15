"""Unit tests for the known-object recovery. No network, no FITS files."""

import numpy as np
import pytest

from src.controls import local_noise, peak_near, recover


class FlatWcs:
    """Minimal WCS: one pixel per unit, origin at the grid centre."""

    def __init__(self, nx, ny):
        self.nx, self.ny = nx, ny

    def world_to_pixel_values(self, ra, dec):
        return np.array([ra]), np.array([dec])


def test_local_noise_reads_the_median_variance():
    variance = np.full((32, 32), 4.0)
    assert local_noise(variance, 16, 16, box=9) == pytest.approx(2.0)


def test_local_noise_returns_none_when_the_patch_is_empty():
    variance = np.full((32, 32), np.nan)
    assert local_noise(variance, 16, 16, box=9) is None


def test_peak_near_finds_the_brightest_pixel():
    cube = np.zeros((3, 32, 32), dtype=np.float32)
    cube[:, 16, 17] = 5.0
    peak, x, y = peak_near(cube, 16, 16, radius=3)
    assert peak == pytest.approx(5.0)
    assert (x, y) == (17, 16)


def test_recover_reports_not_in_field_outside_the_grid():
    cube = np.zeros((3, 32, 32), dtype=np.float32)
    variance = np.ones_like(cube)
    result = recover(cube, variance, FlatWcs(32, 32), "outside", 100.0, 100.0,
                     threshold=5.0)
    assert result.verdict == "not in field"
    assert result.in_field is False


def test_recover_finds_a_bright_source():
    cube = np.zeros((4, 32, 32), dtype=np.float32)
    cube[:, 16, 16] = 10.0
    variance = np.ones_like(cube)
    result = recover(cube, variance, FlatWcs(32, 32), "bright", 16.0, 16.0,
                     threshold=5.0)
    assert result.verdict == "recovered"
    assert result.snr > 5.0


def test_recover_reports_below_limit_for_a_faint_source():
    cube = np.zeros((4, 32, 32), dtype=np.float32)
    cube[:, 16, 16] = 0.5
    variance = np.ones_like(cube)
    result = recover(cube, variance, FlatWcs(32, 32), "faint", 16.0, 16.0,
                     threshold=5.0)
    assert result.verdict == "below limit"
