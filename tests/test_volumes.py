"""Area–depth and GRV against analytic answers (plan §5.6, T5–T8, T24; tolerances from F3)."""
import io

import numpy as np
import pandas as pd
import pytest

from posgridder.core.operations import OperationError, apply
from posgridder.core.volumes import builder_csv, scope_csv
from tests.conftest import add_grid
from tests.test_closure import two_domes

Z0, A_PAR, S_CONE, L = 2000.0, 1e-4, 0.1, 1500.0


def _shape(kind: str, inc: float):
    x = np.arange(-L, L + inc / 2, inc)
    xx, yy = np.meshgrid(x, x)
    r = np.hypot(xx, yy)
    return Z0 + (A_PAR * r ** 2 if kind == "paraboloid" else S_CONE * r)


def _volumes(project, kind, inc, **params):
    top = add_grid(project, _shape(kind, inc), domain="depth", name=f"{kind} {inc}", inc=inc,
                   xori=-L, yori=-L)
    mid = top.nrow // 2
    closure = apply(project, "closure", [top.uid],
                    {"crest": [mid, mid], "choice": {"event": 0}}, name=f"c {kind} {inc}")
    params = {"geometry": "top_constant", "thickness": 1e5, **params}
    return apply(project, "volumes", [closure.uid, top.uid],
                 {"roles": ["closure", "top"], **params}, name=f"v {kind} {inc}")


def _area(u, kind):
    return np.pi * u / A_PAR if kind == "paraboloid" else np.pi * (u / S_CONE) ** 2


def _grv(u, kind, t=None):
    if kind == "paraboloid":
        f = lambda v: np.pi * v ** 2 / (2 * A_PAR)          # noqa: E731
    else:
        f = lambda v: np.pi * v ** 3 / (3 * S_CONE ** 2)    # noqa: E731
    return f(u) - (f(u - t) if t is not None and u > t else 0.0)


@pytest.mark.parametrize("kind", ["paraboloid", "cone"])
def test_area_and_grv_top_only(project, kind):
    """T5, T6, T8: contact 100 m below the crest; 25 m cells (n = 40 cells across the radius)."""
    v = _volumes(project, kind, 25.0)
    c = Z0 + 100.0
    assert v.area_at(c) * 1e6 == pytest.approx(_area(100.0, kind), rel=1e-3)
    assert v.grv_at(c) * 1e6 == pytest.approx(_grv(100.0, kind), rel=2e-3)
    assert v.grv_at(c, "grv_trapezoid_1e6m3") * 1e6 == pytest.approx(_grv(100.0, kind), rel=5e-3)
    assert v.summary["agreement_relative"] < 0.01


def test_constant_thickness(project):
    """T7: paraboloid, 50 m thickness: (π/a)(5000 − 1250) m³ = 117.81 × 10⁶ m³ at 100 m."""
    v = _volumes(project, "paraboloid", 25.0, thickness=50.0)
    expected = np.pi / A_PAR * (100 ** 2 / 2 - 50 ** 2 / 2)
    assert v.grv_at(Z0 + 100) * 1e6 == pytest.approx(expected, rel=2e-3)
    assert v.grv_at(Z0 + 100, "grv_trapezoid_1e6m3") * 1e6 == pytest.approx(expected, rel=5e-3)


def test_area_converges_at_second_order(project):
    errors = []
    for inc in (100.0, 50.0, 25.0):
        v = _volumes(project, "paraboloid", inc)
        errors.append(abs(v.area_at(Z0 + 100) * 1e6 / _area(100.0, "paraboloid") - 1))
    assert errors[0] / errors[1] >= 3 and errors[1] / errors[2] >= 3


def test_top_and_base_surfaces_match_constant_thickness(project):
    top = add_grid(project, _shape("paraboloid", 50.0), domain="depth", name="top", inc=50.0,
                   xori=-L, yori=-L)
    base = apply(project, "offset", [top.uid], {"constant": 50.0}, name="base")
    thick = apply(project, "subtract", [base.uid, top.uid], name="isochore")
    closure = apply(project, "closure", [top.uid], {"crest": [30, 30], "choice": {"event": 0}},
                    name="c")
    a = apply(project, "volumes", [closure.uid, top.uid, base.uid],
              {"roles": ["closure", "top", "base"], "geometry": "top_base"}, name="a")
    b = apply(project, "volumes", [closure.uid, top.uid, thick.uid],
              {"roles": ["closure", "top", "thickness"], "geometry": "top_grid"}, name="b")
    c = apply(project, "volumes", [closure.uid, top.uid],
              {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 50.0},
              name="c")
    for col in ("top_area_km2", "base_area_km2", "grv_direct_1e6m3"):
        np.testing.assert_allclose(a.table[col], c.table[col], atol=1e-6)
        np.testing.assert_allclose(b.table[col], c.table[col], atol=1e-6)


def test_negative_thickness_and_missing_base_flagged(project):
    top = add_grid(project, _shape("paraboloid", 100.0), domain="depth", name="top", inc=100.0,
                   xori=-L, yori=-L)
    z = _shape("paraboloid", 100.0) + 30.0
    z[15, 15] = 1990.0                                   # base above top at the crest
    mask = np.zeros_like(z, bool)
    mask[14, 16] = True
    base = add_grid(project, z, domain="depth", name="base", inc=100.0, xori=-L, yori=-L,
                    mask=mask)
    closure = apply(project, "closure", [top.uid], {"crest": [15, 15], "choice": {"event": 0}},
                    name="c")
    v = apply(project, "volumes", [closure.uid, top.uid, base.uid],
              {"roles": ["closure", "top", "base"], "geometry": "top_base"}, name="v")
    assert any("negative thickness" in w for w in v.warnings)
    assert any("have no base" in w for w in v.warnings)
    assert (v.table["base_area_km2"] <= v.table["top_area_km2"] + 1e-12).all()


def test_outline_clips_area_and_grv(project):
    """A half-plane outline through the crest halves area and GRV of a symmetric dome."""
    top = add_grid(project, _shape("paraboloid", 25.0), domain="depth", name="top", inc=25.0,
                   xori=-L, yori=-L)
    closure = apply(project, "closure", [top.uid], {"crest": [60, 60], "choice": {"event": 0}},
                    name="c")
    half = apply(project, "outline_points", [],
                 {"coords": [[0, -2000], [2000, -2000], [2000, 2000], [0, 2000]]}, name="east")
    full = apply(project, "volumes", [closure.uid, top.uid],
                 {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 1e5},
                 name="full")
    clipped = apply(project, "volumes", [closure.uid, top.uid, half.uid],
                    {"roles": ["closure", "top", "outline"], "geometry": "top_constant",
                     "thickness": 1e5}, name="clipped")
    assert clipped.area_at(Z0 + 100) == pytest.approx(full.area_at(Z0 + 100) / 2, rel=1e-3)
    # Node-based GRV counts the column on the dividing line in full: about one cell row extra.
    assert clipped.grv_at(Z0 + 100) == pytest.approx(full.grv_at(Z0 + 100) / 2, rel=0.03)
    assert any("outline" in a for a in clipped.assumptions)


def test_single_fill_differs_only_above_the_saddle(project):
    top = add_grid(project, two_domes(), domain="depth", name="two", inc=50.0)
    zz = np.ma.getdata(top.values)
    crest = [int(v) for v in np.unravel_index(np.argmin(zz), zz.shape)]
    closure = apply(project, "closure", [top.uid], {"crest": crest, "choice": {"event": 1}},
                    name="c")
    v = apply(project, "volumes", [closure.uid, top.uid],
              {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 1e5},
              name="v")
    saddle = closure.sub_culminations[0]["saddle"]
    t = v.table
    above = (t["depth_m"] > 2011) & (t["depth_m"] < saddle - 1)
    below = t["depth_m"] >= saddle
    assert (t.loc[above, "grv_single_fill_1e6m3"] < t.loc[above, "grv_direct_1e6m3"]).all()
    np.testing.assert_allclose(t.loc[below, "grv_single_fill_1e6m3"],
                               t.loc[below, "grv_direct_1e6m3"], rtol=1e-12)
    assert any("Single-fill" in w for w in v.warnings)


def test_builder_and_scope_exports(project):
    """T24: the Builder's AreaDepthTable rules hold on the exported file."""
    v = _volumes(project, "paraboloid", 100.0, thickness=40.0)
    text = builder_csv(v, ["POS-Gridder test"])
    frame = pd.read_csv(io.StringIO(text), comment="#")
    assert list(frame.columns) == ["depth_m", "top_area_km2", "base_area_km2", "grv_1e6m3_cached"]
    assert (np.diff(frame["depth_m"]) > 0).all()
    assert frame["top_area_km2"].iloc[0] == 0.0
    assert (frame["base_area_km2"] <= frame["top_area_km2"]).all()
    net = frame["top_area_km2"] - frame["base_area_km2"]
    trap = np.concatenate([[0], np.cumsum(np.diff(frame["depth_m"]) * 0.5 * (net[1:].to_numpy()
                                                                              + net[:-1].to_numpy()))])
    np.testing.assert_allclose(frame["grv_1e6m3_cached"], trap, atol=1e-4)
    scope = pd.read_csv(io.StringIO(scope_csv(v)))
    assert list(scope.columns) == ["Depth", "Top area (km2)", "Base area (km2)"]


def test_volume_input_checks(project):
    top = add_grid(project, _shape("paraboloid", 100.0), domain="depth", name="top", inc=100.0,
                   xori=-L, yori=-L)
    other = add_grid(project, _shape("paraboloid", 100.0), domain="depth", name="other",
                     inc=100.0, xori=-L, yori=-L)
    closure = apply(project, "closure", [top.uid], {"crest": [15, 15], "choice": {"event": 0}},
                    name="c")
    with pytest.raises(OperationError, match="another surface"):
        apply(project, "volumes", [closure.uid, other.uid],
              {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 10.0},
              name="x")
    with pytest.raises(OperationError, match="positive"):
        apply(project, "volumes", [closure.uid, top.uid],
              {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 0.0},
              name="x")
