"""Unit tests for the detection limit. No network, no FITS files."""

import numpy as np
import pytest

from src.limit import (diagnose, effective_pixels, limit_from_arrays,
                       systematic_budget, variance_budget)


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
    flags = np.full((8, 8), 1 << 6, dtype=int)   # NONFUNC: unusable for any purpose
    with pytest.raises(ValueError):
        limit_from_arrays(var, flags, 1, 2.0, "synthetic")


def test_source_flag_does_not_remove_area():
    # Bit 21 SOURCE marks a position, not a defect: the pixel stays usable.
    var = np.full((64, 64), 1e-3)
    flags = np.full((64, 64), 1 << 21, dtype=int)
    lim = limit_from_arrays(var, flags, 1, 2.0, "synthetic")
    assert lim.usable_fraction == pytest.approx(1.0, abs=1e-6)


def test_transient_flag_does_not_remove_area():
    # Bit 0 TRANSIENT spoils one exposure, not the pixel.
    var = np.full((64, 64), 1e-3)
    flags = np.full((64, 64), 1 << 0, dtype=int)
    lim = limit_from_arrays(var, flags, 1, 2.0, "synthetic")
    assert lim.usable_fraction == pytest.approx(1.0, abs=1e-6)


def test_systematic_budget_brackets_the_central_value():
    var = np.full((64, 64), 1e-3)
    flags = np.zeros((64, 64), dtype=int)
    central = limit_from_arrays(var, flags, 4, 2.0, "synthetic")
    budget = systematic_budget(var, flags, 4, 2.0, "synthetic")
    assert budget["peak_min"] <= central.peak_limit_mjy_sr <= budget["peak_max"]
    assert budget["peak_max"] > budget["peak_min"]


def test_variance_budget_splits_background_and_read():
    rng = np.random.default_rng(7)
    zodi = rng.uniform(0.1, 0.3, (128, 128))
    variance = 0.01 * zodi + 1e-5
    flags = np.zeros((128, 128), dtype=int)
    budget = variance_budget(variance, zodi, flags)
    assert 0.0 <= budget["background_share"] <= 1.0
    assert 0.0 <= budget["read_share"] <= 1.0
    assert budget["background_share"] + budget["read_share"] == pytest.approx(1.0, abs=1e-6)
    assert budget["crowding_share"] == pytest.approx(0.0, abs=1e-6)


def test_diagnose_names_area_loss_when_most_of_the_field_is_dead():
    budget = {"crowding_share": 0.9, "background_share": 0.8, "read_share": 0.2}
    confusion = {"confusion_share": 0.1}
    assert diagnose(budget, confusion)["cause"] == "area loss"


def test_diagnose_names_confusion_when_fixed_pattern_dominates():
    budget = {"crowding_share": 0.01, "background_share": 0.8, "read_share": 0.2}
    confusion = {"confusion_share": 0.6}
    assert diagnose(budget, confusion)["cause"] == "confusion"


def test_diagnose_names_background_when_field_is_clean():
    budget = {"crowding_share": 0.01, "background_share": 0.8, "read_share": 0.2}
    confusion = {"confusion_share": 0.05}
    result = diagnose(budget, confusion)
    assert result["cause"] == "background"
    assert result["averages_down_with_visits"] is True
