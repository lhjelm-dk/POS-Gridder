import numpy as np
import pytest

from posgridder.io.surfaces import FORMATS, guess_format, read_surface, write_surface
from posgridder.io.zmap import read_zmap, write_zmap


def _same(a, b, atol):
    assert (a.nrow, a.ncol) == (b.nrow, b.ncol)
    assert np.allclose([a.xori, a.yori, a.xinc, a.yinc], [b.xori, b.yori, b.xinc, b.yinc], atol=0.5)
    assert (np.ma.getmaskarray(a.values) == np.ma.getmaskarray(b.values)).all()
    assert np.ma.max(np.abs(a.values - b.values)) <= atol


def test_zmap_round_trip(dome, tmp_path):
    path = tmp_path / "dome.dat"
    write_zmap(dome, path)
    back = read_zmap(path)
    _same(dome, back, atol=1e-3)          # 7 decimals in E format: ~1e-4 m at 2000 m
    assert back.crs == "ED50-UTM32"
    assert back.name == "dome"


def test_zmap_orientation(dome):
    """The north-east corner must come back in the north-east, not mirrored or transposed."""
    back = read_zmap(write_zmap(dome).encode())
    assert back.values[-1, -1] == pytest.approx(dome.values[-1, -1], abs=1e-3)
    assert back.values[-1, 0] == pytest.approx(dome.values[-1, 0], abs=1e-3)
    assert back.values.mask[0, 0] and not back.values.mask[-1, -1]


def test_zmap_honours_header_null():
    text = (
        "!\n"
        "@G HEADER, GRID, 3\n"
        " 15, -999.0, , 7, 1\n"
        " 2, 3, 0.0, 20.0, 0.0, 10.0\n"
        " 0.0, 0.0, 0.0\n"
        "@\n"
        "  1.0  2.0\n"
        "  -999.0  4.0\n"
        "  5.0  6.0\n"
    )
    s = read_zmap(text.encode())
    # Column 0 holds north 1, south 2; column 1 holds north -999 (null), south 4.
    assert s.values.mask.tolist() == [[False, False, False], [False, True, False]]
    assert s.values[1, 0] == 1.0 and s.values[0, 0] == 2.0
    assert (s.xinc, s.yinc) == (10.0, 10.0)
    assert s.name == "G"


def test_zmap_refuses_garbage():
    with pytest.raises(ValueError):
        read_zmap(b"x y z\n1 2 3\n")


@pytest.mark.parametrize("fmt", [k for k in FORMATS if k != "zmap"])
def test_xtgeo_formats_round_trip(dome, fmt):
    back = read_surface(write_surface(dome, fmt), fmt)
    _same(dome, back, atol=1e-3)          # IRAP binary is float32


def test_guess_format():
    assert guess_format("a/b/top.dat") == "zmap"
    assert guess_format("top.GRI") == "irap_binary"
    assert guess_format("top.xyz") is None
    with pytest.raises(ValueError):
        read_surface(b"", None, filename="top.xyz")


def test_geus_grid(geus_path):
    """The real file: geometry from the header, 1E+30 read as null, values as measured."""
    s = read_surface(geus_path)
    assert (s.ncol, s.nrow) == (217, 238)
    assert (s.xori, s.yori, s.xinc, s.yinc) == pytest.approx((621373.0625, 6145533.4525, 250, 250))
    assert s.crs == "ED50-UTM32"
    stats = s.stats()
    assert stats["valid"] == 23784
    assert stats["min"] == pytest.approx(-1548.941, abs=1e-3)
    assert stats["max"] == pytest.approx(-945.1266, abs=1e-3)


def test_geus_grid_matches_xtgeo(geus_path):
    """Our reader and xtgeo agree on every node once xtgeo's missed nulls are masked."""
    xtgeo = pytest.importorskip("xtgeo")
    ours = read_surface(geus_path)
    theirs = xtgeo.surface_from_file(str(geus_path), fformat="zmap_ascii")
    expected = np.ma.masked_greater(theirs.values, 1e29).T
    assert (np.ma.getmaskarray(ours.values) == np.ma.getmaskarray(expected)).all()
    assert np.ma.allclose(ours.values, expected)
