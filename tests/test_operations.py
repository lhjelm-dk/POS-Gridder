"""Arithmetic, domain rules, alignment, resampling (plan §5.1, T4)."""
import numpy as np
import pytest

from posgridder.core.operations import OperationError, apply, result_domain
from tests.conftest import add_grid, dome_values


@pytest.mark.parametrize("op, a, b, expected", [
    ("subtract", "depth", "depth", "thickness"),
    ("subtract", "depth", "thickness", "depth"),
    ("add", "depth", "thickness", "depth"),
    ("add", "thickness", "depth", "depth"),
    ("add", "thickness", "thickness", "thickness"),
    ("subtract", "other", "other", "other"),
])
def test_allowed_domains(op, a, b, expected):
    assert result_domain(op, a, b) == expected


@pytest.mark.parametrize("op, a, b", [
    ("add", "time", "depth"), ("subtract", "time", "time"), ("add", "depth", "depth"),
    ("subtract", "thickness", "depth"), ("add", "probability", "probability"),
    ("subtract", "velocity", "velocity"), ("add", "other", "depth"),
])
def test_refused_domains(op, a, b):
    with pytest.raises(OperationError, match="not a defined combination"):
        result_domain(op, a, b)


def test_thickness_is_base_minus_top_with_nulls(project):
    top = dome_values()
    mask = np.zeros_like(top, bool)
    mask[0, 0] = True
    t = add_grid(project, top, domain="depth", name="top", mask=mask)
    base_vals = top + 37.5
    base_mask = np.zeros_like(top, bool)
    base_mask[5, 5] = True
    b = add_grid(project, base_vals, domain="depth", name="base", mask=base_mask)
    thick = apply(project, "subtract", [b.uid, t.uid], name="thick")
    assert thick.domain == "thickness" and thick.unit == "m"
    assert thick.values.mask[0, 0] and thick.values.mask[5, 5]       # a null in either input
    np.testing.assert_allclose(thick.values.compressed(), 37.5, atol=1e-3)
    assert thick.warnings == ()


def test_negative_thickness_is_flagged(project, dome):
    deeper = apply(project, "offset", [dome.uid], {"constant": 10.0}, name="deeper")
    thick = apply(project, "subtract", [dome.uid, deeper.uid], name="inverted")
    assert any("negative thickness" in w for w in thick.warnings)


def test_time_plus_depth_refused(project, dome):
    t = add_grid(project, np.full((21, 31), 1500.0), domain="time", name="twt")
    with pytest.raises(OperationError, match="not a defined combination"):
        apply(project, "add", [dome.uid, t.uid], name="x")
    assert len(project.layers) == 2                                   # nothing added


def test_misaligned_grids_refused_with_resample_hint(project, dome):
    other = add_grid(project, dome_values(), domain="depth", name="shifted", xori=500_050.0)
    with pytest.raises(OperationError, match="Resample"):
        apply(project, "subtract", [dome.uid, other.uid], name="x")


def test_different_crs_refused(project, dome):
    other = add_grid(project, dome_values(), domain="depth", name="b", crs="ED50-UTM31")
    with pytest.raises(OperationError, match="coordinate systems"):
        apply(project, "subtract", [dome.uid, other.uid], name="x")


def test_missing_crs_warns(project, dome):
    other = add_grid(project, dome_values(), domain="depth", name="b", crs=None)
    out = apply(project, "subtract", [dome.uid, other.uid], name="x")
    assert out.crs == "ED50-UTM32"
    assert any("no coordinate system" in w for w in out.warnings)


def test_scalar_operations_and_probability_refusal(project, dome):
    assert apply(project, "scale", [dome.uid], {"factor": 2.0}, name="x2").stats()["max"] == \
        pytest.approx(2 * dome.stats()["max"], rel=1e-9)
    p = add_grid(project, np.full((21, 31), 0.3), domain="probability", name="pos")
    with pytest.raises(OperationError, match="probability"):
        apply(project, "scale", [p.uid], {"factor": 2.0}, name="bad")


def test_clip(project, dome):
    c = apply(project, "clip", [dome.uid], {"min": 1990.0, "max": 2000.0}, name="c")
    assert c.stats()["min"] >= 1990.0 and c.stats()["max"] <= 2000.0
    assert c.n_valid == dome.n_valid
    with pytest.raises(OperationError):
        apply(project, "clip", [dome.uid], {"min": 5.0, "max": 1.0}, name="bad")


def test_smooth_keeps_nulls_and_planes(project):
    x, y = np.meshgrid(np.arange(31.0), np.arange(21.0))
    plane = 1000 + 2 * x + 3 * y
    mask = np.zeros_like(plane, bool)
    mask[10, 10] = True
    s = add_grid(project, plane, domain="depth", name="plane", mask=mask)
    out = apply(project, "smooth", [s.uid], {"passes": 3}, name="sm")
    assert out.values.mask[10, 10] and out.n_valid == s.n_valid
    interior = (slice(4, -4), slice(4, -4))
    near_hole = np.zeros_like(plane, bool)
    near_hole[6:15, 6:15] = True                      # the hole biases its neighbours slightly
    sel = ~near_hole[interior]
    np.testing.assert_allclose(out.values[interior].filled(np.nan)[sel],
                               plane[interior][sel], atol=1e-3)


def test_resample_bilinear_reproduces_a_plane(project):
    """Bilinear interpolation is exact for a plane; nodes outside the source are null."""
    x, y = np.meshgrid(np.arange(31.0), np.arange(21.0))
    src = add_grid(project, 1000 + 2 * x + 3 * y, domain="depth", name="coarse", inc=100.0)
    xt, yt = np.meshgrid(np.arange(25.0), np.arange(20.0))
    target = add_grid(project, np.zeros_like(xt), domain="other", name="fine", inc=125.0,
                      xori=500_000.0 + 30.0, yori=6_100_000.0 + 10.0)
    out = apply(project, "resample", [src.uid, target.uid], {"method": "bilinear"}, name="r")
    assert out.same_geometry(target) and out.domain == "depth"
    tx = 30.0 + 125.0 * xt
    ty = 10.0 + 125.0 * yt
    inside = (tx <= 3000) & (ty <= 2000)
    expected = 1000 + 2 * tx / 100 + 3 * ty / 100
    np.testing.assert_allclose(out.values.filled(np.nan)[inside], expected[inside], atol=1e-3)
    assert out.values.mask[~inside].all()


def test_resample_nearest_and_null_spread(project):
    z = np.arange(21 * 31, dtype=float).reshape(21, 31)
    mask = np.zeros_like(z, bool)
    mask[10, 10] = True
    src = add_grid(project, z, domain="other", name="src", mask=mask)
    # Offset 30 m, not half a cell, so every target node has one unambiguous nearest node.
    target = add_grid(project, np.zeros((20, 30)), domain="other", name="t",
                      xori=500_030.0, yori=6_100_030.0)
    near = apply(project, "resample", [src.uid, target.uid], {"method": "nearest"}, name="n")
    bil = apply(project, "resample", [src.uid, target.uid], {"method": "bilinear"}, name="b")
    assert int(np.count_nonzero(bil.values.mask)) == 4          # four cells touch the null node
    assert any("surrounding source node is null" in w for w in bil.warnings)
    assert int(np.count_nonzero(near.values.mask)) <= 1
