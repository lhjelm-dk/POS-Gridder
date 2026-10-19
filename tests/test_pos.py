"""Spatial POS and area/GRV by percentile (plan §5.8, §5.9, T14, T18–T20, T25–T27)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from posgridder.core.operations import OperationError, apply, replay
from posgridder.core.volumes import builder_csv
from posgridder.io import project_file
from posgridder.io.hcwc_files import import_area_depth, import_hcwc
from tests.conftest import add_grid
from tests.test_hcwc import P, uniform_table

FIX = Path(__file__).parent / "fixtures" / "hcwc_builder"
A_PAR, L = 1e-4, 1500.0


def dome(project, crest=2000.0, inc=50.0):
    """A paraboloid with its crest at ``crest``; it spills at the edge, 225 m deeper."""
    x = np.arange(-L, L + inc / 2, inc)
    xx, yy = np.meshgrid(x, x)
    top = add_grid(project, crest + A_PAR * (xx ** 2 + yy ** 2), domain="depth", name="top",
                   inc=inc, xori=-L, yori=-L)
    mid = top.nrow // 2
    closure = apply(project, "closure", [top.uid], {"crest": [mid, mid], "choice": {"event": 0}},
                    name="closure")
    return top, closure


def table_dist(project, lo, hi, *, conditioning="unconditioned", **meta):
    p, d = uniform_table(lo, hi)
    return import_hcwc(project, name=f"U({lo:g},{hi:g}) {conditioning}", basis="geological",
                       conditioning=conditioning, tails="raw",
                       table={"percentiles": p, "depths": d}, **meta)


def pos_map(project, top, closure, src, *, event="a", anchoring="as_is", role="hcwc", **params):
    return apply(project, "pos_map", [closure.uid, top.uid, src.uid],
                 {"roles": ["closure", "top", role], "event": event, "anchoring": anchoring,
                  **params}, name=f"pos {event}")


def test_uniform_pos_map(project):
    """T14 on a map: P(G) 0.3, C ~ U(2100, 2200): POS = 0.3 · clip((2200 − s)/100, 0, 1)."""
    top, closure = dome(project)
    dist = table_dist(project, 2100, 2200, p_g=0.3, h_min=50.0, apex=2000.0)
    m = pos_map(project, top, closure, dist, event="b")
    s = closure.fill
    inside = closure.footprint
    expected = 0.3 * np.clip((2200 - s) / 100, 0, 1)
    got = np.where(m.category == 2, 0.0, m.pos)
    np.testing.assert_allclose(got[inside], expected[inside], atol=1e-12)
    assert (m.category[~inside] == 4).all()
    assert set(np.unique(m.category[inside])) == {1, 2}
    assert np.isnan(m.pos[~inside]).all()


def test_invariants(project):
    """T20: 0 ≤ POS ≤ multiplier, non-increasing in s, categories cover every node once."""
    top, closure = dome(project)
    dist = table_dist(project, 2050, 2180, p_g=0.42, h_min=60.0, apex=2000.0)
    m = pos_map(project, top, closure, dist, event="a")
    finite = np.isfinite(m.pos)
    assert (m.pos[finite] >= 0).all() and (m.pos[finite] <= m.summary["multiplier"] + 1e-12).all()
    order = np.argsort(closure.fill[finite])
    assert (np.diff(m.pos[finite][order]) <= 1e-12).all()
    assert m.category.size == sum((m.category == k).sum() for k in range(6))


def test_conditioned_and_unconditioned_agree(project):
    """T18/T27: H ~ U(0, 200) below a 2000 m apex, h_min = 100 m, so F(h_min) = 0.5.

    Event (a) is the same from either table everywhere. Event (b) from the conditioned table
    equals the unconditioned answer deeper than apex + h_min and is flagged above it.
    """
    top, closure = dome(project)
    uncond = table_dist(project, 2000, 2200, p_g=0.4, h_min=100.0, apex=2000.0)
    cond = table_dist(project, 2100, 2200, conditioning="h_min", p_g=0.4, f_hmin=0.5,
                      h_min=100.0, apex=2000.0)
    a_u = pos_map(project, top, closure, uncond, event="a")
    a_c = pos_map(project, top, closure, cond, event="a")
    np.testing.assert_allclose(a_u.pos, a_c.pos, atol=1e-12, equal_nan=True)
    assert a_u.summary["f_hmin_derived"] == pytest.approx(0.5, abs=1e-12)
    b_u = pos_map(project, top, closure, uncond, event="b")
    b_c = pos_map(project, top, closure, cond, event="b")
    deep = closure.footprint & (closure.fill > 2100)
    np.testing.assert_allclose(b_c.pos[deep], b_u.pos[deep], atol=1e-12)
    band = closure.footprint & (closure.fill <= 2100)
    assert (b_c.category[band] == 3).all() and np.isnan(b_c.pos[band]).all()
    assert (b_u.category[band] == 1).all()


def test_crest_value_equals_builder_prospect_pos(project):
    """On the real Builder export: POS at the crest = P(G) · F(h_min), the Prospect POS."""
    ref = pd.read_json(FIX / "builder_reference.json", typ="series")
    top, closure = dome(project, crest=2050.0)
    dist = import_hcwc(project, name="builder", basis="geological", conditioning="h_min",
                       tails="truncated",
                       csv=("hcwc_percentiles_geological.csv",
                            (FIX / "hcwc_percentiles_geological.csv").read_bytes()),
                       json=("example.hcwc.json",
                             (FIX / "example_prospect_spill.hcwc.json").read_bytes()),
                       h_min=float(ref["h_min_m"]), f_hmin=float(ref["F_h_min"]))
    m = pos_map(project, top, closure, dist, event="a")
    prospect = 0.40824 * float(ref["F_h_min"])
    assert m.summary["prospect_pos"] == pytest.approx(prospect, rel=1e-9)
    assert m.summary["pos_at_crest"] == pytest.approx(prospect, rel=1e-9)
    assert np.nanmax(m.pos) == pytest.approx(prospect, rel=1e-9)
    assert not any("crest" in w and "differs" in w for w in m.warnings)


def test_reanchoring(project):
    top, closure = dome(project, crest=2000.0)
    dist = table_dist(project, 2100, 2200, p_g=0.3, apex=2020.0)
    as_is = pos_map(project, top, closure, dist, event="b")
    moved = pos_map(project, top, closure, dist, event="b", anchoring="reanchor")
    assert any("differs from the Builder apex (2020.0 m) by -20.0 m" in w for w in as_is.warnings)
    assert moved.summary["shift_m"] == pytest.approx(-20.0)
    node = closure.footprint & np.isclose(closure.fill, 2150, atol=30)
    s = closure.fill[node]
    np.testing.assert_allclose(moved.pos[node], 0.3 * np.clip((2180 - s) / 100, 0, 1), atol=1e-12)


def test_missing_inputs_are_refused(project):
    top, closure = dome(project)
    cond = table_dist(project, 2100, 2200, conditioning="h_min", p_g=0.4)
    assert any("F(h_min) is not given" in w for w in cond.warnings)
    with pytest.raises(OperationError, match="F\\(h_min\\)"):
        pos_map(project, top, closure, cond, event="a")
    no_pg = table_dist(project, 2100, 2200)
    with pytest.raises(OperationError, match="P\\(G\\)"):
        pos_map(project, top, closure, no_pg, event="b")


def test_typed_curves(project):
    """D6: the user's example — 2300 m contour 24 %, 2400 m 13 % — shifted onto this dome."""
    top, closure = dome(project)
    total = apply(project, "pos_curve", [], {"depths": [2050, 2100], "values": [0.24, 0.13],
                                             "meaning": "total"}, name="typed total")
    m = pos_map(project, top, closure, total, role="curve")
    s = closure.fill
    def at(v):
        return float(np.interp(v, [2050, 2100, 2225], [0.24, 0.13, 0.0]))
    for node in np.argwhere(closure.footprint)[::97]:
        i, j = node
        expected = 0.24 if s[i, j] < 2050 else at(s[i, j])
        assert m.pos[i, j] == pytest.approx(expected, abs=1e-12) or (
            expected == 0 and m.category[i, j] == 2)
    cond = apply(project, "pos_curve", [], {"depths": [2050, 2100], "values": [0.24, 0.13],
                                            "meaning": "conditional"}, name="typed conditional")
    half = pos_map(project, top, closure, cond, role="curve", p_g=0.5)
    np.testing.assert_allclose(half.pos, 0.5 * m.pos, atol=1e-12, equal_nan=True)
    with pytest.raises(OperationError, match="fractions"):
        apply(project, "pos_curve", [], {"depths": [2300], "values": [24], "meaning": "total"},
              name="bad")


def test_percentile_volumes(project):
    """T19: C ~ U(2150, 2250) on a paraboloid that spills at 2225 m."""
    top, closure = dome(project)
    vol = apply(project, "volumes", [closure.uid, top.uid],
                {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 1e5},
                name="volumes")
    dist = table_dist(project, 2150, 2250)
    pv = apply(project, "percentile_volumes", [vol.uid, dist.uid], {"anchoring": "as_is"},
               name="by percentile")
    t = pv.table
    spill = closure.spill_depth
    for p in (90, 50, 30):
        row = t[t["percentile"] == p].iloc[0]
        c = 2150 + (100 - p)
        assert row["grv_1e6m3"] * 1e6 == pytest.approx(np.pi * (c - 2000) ** 2 / (2 * A_PAR),
                                                       rel=3e-3)
    capped = t[t["contact_m"] > spill]
    assert (capped["contact_used_m"] == spill).all()
    assert pv.summary["p_contact_below_spill"] == pytest.approx(0.25, abs=1e-9)
    assert any("deeper than the map spill" in w for w in pv.warnings)
    assert pv.summary["grv_P10_1e6m3"] >= pv.summary["grv_P50_1e6m3"] >= pv.summary["grv_P90_1e6m3"]


def test_area_depth_round_trip(project):
    """T25: export to the Builder format, import again: the same table and GRV."""
    top, closure = dome(project, inc=100.0)
    vol = apply(project, "volumes", [closure.uid, top.uid],
                {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 40.0},
                name="volumes")
    text = builder_csv(vol, ["round trip"])
    back = import_area_depth(project, "area_depth.csv", text.encode())
    np.testing.assert_allclose(back.table["depth_m"], vol.table["depth_m"], atol=1e-3)
    np.testing.assert_allclose(back.table["top_area_km2"], vol.table["top_area_km2"], atol=1e-6)
    np.testing.assert_allclose(back.table["grv_trapezoid_1e6m3"],
                               vol.table["grv_trapezoid_1e6m3"], atol=1e-3)
    dist = table_dist(project, 2100, 2200)
    pv = apply(project, "percentile_volumes", [back.uid, dist.uid], {}, name="map-free")
    assert pv.summary["grv_P50_1e6m3"] == pytest.approx(
        vol.grv_at(2150, "grv_trapezoid_1e6m3"), rel=1e-3)


def test_edited_table_makes_maps_stale(project):
    """T26: an edited table is a new version; the map made from the old one turns stale."""
    top, closure = dome(project)
    dist = table_dist(project, 2100, 2200, p_g=0.3)
    m = pos_map(project, top, closure, dist, event="b")
    p, d = uniform_table(2100, 2200)
    d = d.copy()
    d[50] += 0.5                                         # still between P51 and P49
    edited = import_hcwc(project, name=dist.name, basis="geological", conditioning="unconditioned",
                         tails="raw", table={"percentiles": p, "depths": d}, p_g=0.3,
                         origin=f"edited from {dist.name}: row P50", supersedes=dist.uid)
    assert edited.derivation.supersedes == dist.uid
    assert project.is_stale(m.uid)
    assert "row P50" in edited.origin


def test_round_trip_and_replay_of_every_new_kind(project):
    top, closure = dome(project, inc=100.0)
    vol = apply(project, "volumes", [closure.uid, top.uid],
                {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 40.0},
                name="volumes")
    dist = import_hcwc(project, name="builder", basis="geological", conditioning="h_min",
                       tails="truncated", f_hmin=0.8891, h_min=120.0,
                       csv=("hcwc_percentiles_geological.csv",
                            (FIX / "hcwc_percentiles_geological.csv").read_bytes()),
                       json=("example.hcwc.json",
                             (FIX / "example_prospect_spill.hcwc.json").read_bytes()))
    curve = apply(project, "pos_curve", [], {"depths": [2050, 2100], "values": [0.24, 0.13],
                                             "meaning": "total"}, name="curve")
    pos_map(project, top, closure, dist, event="a")
    pos_map(project, top, closure, curve, role="curve")
    apply(project, "percentile_volumes", [vol.uid, dist.uid], {}, name="pv")
    loaded = project_file.load(project_file.save(project))
    kinds = {o.kind for o in loaded.objects.values()}
    assert {"hcwc", "poscurve", "posmap", "pctvol"} <= kinds
    rows = replay(loaded)
    assert all(r.identical for r in rows), [(r.name, r.operation) for r in rows if not r.identical]



@pytest.mark.parametrize("scale", ["Blues", "Greens", "Purples", "Oranges", "Greys", "Viridis",
                                   "Cividis", "Plasma", "Magma", "YlGnBu"])
def test_pos_figure_scales_and_histogram(project, scale):
    from posgridder.plotting.maps import POS_SCALES, pos_figure

    assert len(POS_SCALES) == 10
    top, closure = dome(project)
    dist = table_dist(project, 2100, 2200, p_g=0.3, h_min=50.0, apex=2000.0)
    m = pos_map(project, top, closure, dist, event="b")
    fig = pos_figure(m, scale=scale, reverse=True, histogram=True)
    bars = [t for t in fig.data if t.type == "bar"]
    assert len(bars) == 1
    cell = top.xinc * top.yinc / 1e6
    assert sum(bars[0].x) == pytest.approx((m.category == 1).sum() * cell)
    assert pos_figure(m, scale=scale, histogram=False).data[-1].type == "heatmap"



def test_spill_line_is_a_depth_contour(project):
    """The drawn spill outline lies on the spill depth, not on the node-mask edge."""
    import contourpy

    from posgridder.plotting.maps import spill_field

    top, closure = dome(project)
    z = spill_field(top, closure.footprint, closure.spill_depth)
    gen = contourpy.contour_generator(top.x, top.y, z)
    lines = gen.lines(closure.spill_depth)
    assert lines
    longest = max(lines, key=len)
    # On a paraboloid the spill contour is a circle of radius sqrt((spill - crest) / a).
    r = np.hypot(longest[:, 0], longest[:, 1])
    expected = np.sqrt((closure.spill_depth - closure.crest_depth) / A_PAR)
    inner = r < 0.97 * L                          # away from where it meets the grid edge
    np.testing.assert_allclose(r[inner], expected, rtol=0.01)
