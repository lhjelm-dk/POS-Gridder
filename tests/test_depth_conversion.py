"""Depth conversion against closed-form answers (plan §5.2, T2, T3)."""
import numpy as np
import pytest

from posgridder.core.operations import OperationError, apply
from posgridder.io.surfaces import import_surface
from tests.conftest import add_grid


@pytest.fixture
def twt(project):
    return add_grid(project, np.linspace(800, 2400, 21 * 31).reshape(21, 31), domain="time",
                    name="twt")


def test_constant_velocity(project, twt):
    d = apply(project, "depth_convert", [twt.uid], {"method": "constant", "velocity": 2000.0},
              name="d")
    assert d.domain == "depth" and d.unit == "m"
    np.testing.assert_allclose(d.values, twt.values, rtol=1e-12)    # 2000 m/s: z = TWT in m


def test_v0k_closed_form(project):
    """T3: V0 = 1800 m/s, k = 0.5 /s, TWT = 1000 ms (t = 0.5 s) gives 3600(e^0.25 − 1) m."""
    t = add_grid(project, np.full((3, 3), 1000.0), domain="time", name="t")
    d = apply(project, "depth_convert", [t.uid], {"method": "v0k", "v0": 1800.0, "k": 0.5},
              name="d")
    np.testing.assert_allclose(d.values, 3600 * np.expm1(0.25), atol=1e-6)
    assert float(d.values[0, 0]) == pytest.approx(1022.4914, abs=1e-3)


def test_v0k_satisfies_its_ode(project, twt):
    """dz/dt = V0 + k z, checked by central differences in one-way time."""
    v0, k = 1700.0, 0.6
    d = apply(project, "depth_convert", [twt.uid], {"method": "v0k", "v0": v0, "k": k}, name="d")
    t = twt.values.filled(np.nan).ravel() / 2000
    z = d.values.filled(np.nan).ravel()
    dzdt = np.gradient(z, t)
    np.testing.assert_allclose(dzdt[1:-1], (v0 + k * z)[1:-1], rtol=1e-4)


def test_v0k_with_zero_k_is_constant(project, twt):
    a = apply(project, "depth_convert", [twt.uid], {"method": "v0k", "v0": 2100.0, "k": 0.0},
              name="a")
    b = apply(project, "depth_convert", [twt.uid], {"method": "constant", "velocity": 2100.0},
              name="b")
    assert a.content_hash == b.content_hash


def test_velocity_surface(project, twt):
    vel = add_grid(project, np.full((21, 31), 2500.0), domain="velocity", name="v")
    d = apply(project, "depth_convert", [twt.uid, vel.uid], {"method": "velocity_grid"}, name="d")
    np.testing.assert_allclose(d.values, 1.25 * twt.values, rtol=1e-12)


def test_refusals(project, twt, dome):
    with pytest.raises(OperationError, match="needs a time surface"):
        apply(project, "depth_convert", [dome.uid], {"method": "constant", "velocity": 2000.0},
              name="x")
    with pytest.raises(OperationError, match="positive"):
        apply(project, "depth_convert", [twt.uid], {"method": "constant", "velocity": 0.0},
              name="x")
    slow = add_grid(project, np.full((21, 31), -1.0), domain="velocity", name="neg")
    with pytest.raises(OperationError, match="negative velocity"):
        apply(project, "depth_convert", [twt.uid, slow.uid], {"method": "velocity_grid"}, name="x")
    negative = add_grid(project, -np.ones((3, 3)), domain="time", name="neg twt")
    with pytest.raises(OperationError, match="flip its sign"):
        apply(project, "depth_convert", [negative.uid], {"method": "constant", "velocity": 2000.0},
              name="x")


def test_geus_constant_velocity(project, geus_path):
    """T2: the GEUS grid, sign flipped on import, at 2500 m/s gives z = 1.25 · |TWT|."""
    t = import_surface(project, geus_path.name, geus_path.read_bytes(), domain="time",
                       flip_sign=True)
    assert t.warnings == ()
    d = apply(project, "depth_convert", [t.uid], {"method": "constant", "velocity": 2500.0},
              name="d")
    stats = d.stats()
    assert stats["valid"] == 23784
    assert stats["min"] == pytest.approx(1.25 * 945.1266, abs=1e-3)       # 1181.41 m
    assert stats["max"] == pytest.approx(1.25 * 1548.941, abs=1e-3)       # 1936.18 m
