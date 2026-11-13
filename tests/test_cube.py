"""Unit tests for the cube reader. No network access."""

import pytest

from src.cube import tile_index, tile_path


def test_tile_path_uses_ten_thousand_buckets():
    assert tile_path(0).endswith("/Dir0/Npix0_cube.fits")
    assert tile_path(9999).endswith("/Dir0/Npix9999_cube.fits")
    assert tile_path(10000).endswith("/Dir10000/Npix10000_cube.fits")
    assert tile_path(10226).endswith("/Dir10000/Npix10226_cube.fits")


def test_tile_index_is_stable_for_known_positions():
    # Values computed with astropy_healpix, nside 32, nested ordering.
    assert tile_index(133.795129, -7.245147) == 10226   # WISE 0855
    assert tile_index(269.454, 4.693) == 7945           # Barnard's Star
    assert tile_index(270.3415, 66.6023) == 4010        # C2 field


def test_tile_index_stays_inside_the_tile_count():
    for ra, dec in [(0.0, 0.0), (359.9, -89.0), (180.0, 89.0), (400.0, 0.0)]:
        assert 0 <= tile_index(ra, dec) < 12288
