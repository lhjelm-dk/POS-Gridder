"""ZMAP+ reading and writing, and the import step (T1)."""
import numpy as np
import pytest

from posgridder.io.surfaces import guess_format, import_surface, read_grid, write_surface
from posgridder.io.zmap import RawGrid, read_zmap, write_zmap
from tests.conftest import dome_values


def _raw(mask=None):
    z = dome_values()
    return RawGrid("dome", 500_000.0, 6_100_000.0, 100.0, 100.0,
                   np.ma.MaskedArray(z, mask=np.zeros_like(z, bool) if mask is None else mask),
                   crs="ED50-UTM32")


def test_zmap_round_trip(tmp_path):
    mask = np.zeros((21, 31), bool)
    mask[:4, :5] = True
    raw = _raw(mask)
    path = tmp_path / "dome.dat"
    write_zmap(raw, path)
    back = read_zmap(path)
    assert back.geometry == raw.geometry and back.values.shape == raw.values.shape
    assert (np.ma.getmaskarray(back.values) == mask).all()
    assert np.ma.max(np.abs(back.values - raw.values)) <= 1e-3     # 7 decimals in E format
    assert back.crs == "ED50-UTM32" and back.name == "dome"


def test_zmap_orientation():
    """The north-east and north-west corners come back where they were."""
    raw = _raw()
    back = read_zmap(write_zmap(raw).encode())
    assert back.values[-1, -1] == pytest.approx(raw.values[-1, -1], abs=1e-3)
    assert back.values[-1, 0] == pytest.approx(raw.values[-1, 0], abs=1e-3)
    assert back.values[0, -1] == pytest.approx(raw.values[0, -1], abs=1e-3)


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
    g = read_zmap(text.encode())
    # Column 0 holds north 1, south 2; column 1 holds north -999 (null), south 4.
    assert g.values.mask.tolist() == [[False, False, False], [False, True, False]]
    assert g.values[1, 0] == 1.0 and g.values[0, 0] == 2.0
    assert (g.xinc, g.yinc) == (10.0, 10.0)
    assert g.name == "G"


def test_zmap_refuses_garbage():
    with pytest.raises(ValueError):
        read_zmap(b"x y z\n1 2 3\n")


def test_guess_format():
    assert guess_format("a/b/top.dat") == "zmap"
    assert guess_format("top.ZMAP") == "zmap"
    assert guess_format("top.gri") is None                 # IRAP removed in v1 (D8)
    with pytest.raises(ValueError):
        read_grid(b"", None, filename="top.xyz")


def test_import_records_parameters(project):
    data = write_zmap(_raw()).encode()
    s = import_surface(project, "dome.dat", data, domain="depth", crs="EPSG:23032")
    assert s.crs == "EPSG:23032"                           # override wins over the file
    assert s.derivation.operation == "import"
    assert s.derivation.params == {"crs": "EPSG:23032", "domain": "depth", "flip_sign": False,
                                   "format": "zmap"}
    with pytest.raises(TypeError):
        import_surface(project, "dome.dat", data)          # no domain, no import


def test_failed_import_leaves_no_source(project):
    with pytest.raises(ValueError):
        import_surface(project, "bad.dat", b"not a grid", domain="depth")
    assert not project.sources and not project.layers


def test_write_surface_round_trip(project, dome):
    back = read_grid(write_surface(dome), "zmap")
    assert np.ma.max(np.abs(back.values - dome.values)) <= 1e-3


def test_geus_grid(project, geus_path):
    """T1: geometry from the header, 1E+30 read as null, the sign handled explicitly."""
    raw = read_grid(geus_path.read_bytes(), filename=geus_path.name)
    assert raw.values.shape == (238, 217)
    assert raw.geometry == pytest.approx((621373.0625, 6145533.4525, 250, 250))
    assert raw.crs == "ED50-UTM32"
    assert raw.values.count() == 23784

    as_is = import_surface(project, geus_path.name, geus_path.read_bytes(), domain="time")
    assert as_is.stats()["min"] == pytest.approx(-1548.941, abs=1e-3)
    assert any("sign probably needs flipping" in w for w in as_is.warnings)
    flipped = import_surface(project, geus_path.name, geus_path.read_bytes(), domain="time",
                             flip_sign=True)
    assert flipped.warnings == ()
    assert (flipped.stats()["min"], flipped.stats()["max"]) == pytest.approx((945.1266, 1548.941),
                                                                             abs=1e-3)
    assert flipped.unit == "ms"


def test_geus_grid_matches_xtgeo(geus_path):
    """Our reader and xtgeo agree on every node once xtgeo's missed nulls are masked."""
    xtgeo = pytest.importorskip("xtgeo")
    ours = read_grid(geus_path.read_bytes(), filename=geus_path.name)
    theirs = xtgeo.surface_from_file(str(geus_path), fformat="zmap_ascii")
    expected = np.ma.masked_greater(theirs.values, 1e29).T
    assert (np.ma.getmaskarray(ours.values) == np.ma.getmaskarray(expected)).all()
    assert np.ma.allclose(ours.values, expected)
