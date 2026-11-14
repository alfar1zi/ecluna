"""Unit tests for the epoch acquisition helpers. No network, no FITS downloads."""

import importlib.util
import pathlib
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "acquire_epochs.py"
spec = importlib.util.spec_from_file_location("acquire_epochs", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules["acquire_epochs"] = module
spec.loader.exec_module(module)


def test_select_visits_spreads_across_the_series():
    picks = module.select_visits(52, 6)
    assert picks[0] == 0
    assert picks[-1] == 51
    assert len(picks) == 6
    gaps = [picks[i + 1] - picks[i] for i in range(len(picks) - 1)]
    assert max(gaps) - min(gaps) <= 2


def test_select_visits_caps_at_what_exists():
    assert module.select_visits(3, 12) == [0, 1, 2]


def test_select_visits_handles_no_rows():
    assert module.select_visits(0, 6) == []
    assert module.select_visits(10, 0) == []


def test_s3_url_reads_the_cloud_access_field():
    payload = ('{"aws": {"bucket_name": "nasa-irsa-spherex", '
               '"key": "dr1/level2/x.fits"}}')
    assert module.s3_url(payload) == (
        "https://nasa-irsa-spherex.s3.amazonaws.com/dr1/level2/x.fits")


def test_s3_url_rejects_a_missing_field():
    assert module.s3_url("") is None
    assert module.s3_url("not json") is None


def test_targets_have_sane_coordinates():
    for name, (ra, dec) in module.TARGETS.items():
        assert 0 <= ra < 360, name
        assert -90 <= dec <= 90, name
