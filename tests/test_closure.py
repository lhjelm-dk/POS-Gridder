"""Closure and spill interpretation (plan §5.5, T9–T13 and the hand-checked prospect)."""
import numpy as np
import pytest
from scipy import ndimage

from posgridder.core.closure import (DATA_LIMIT, EDGE, INTERIOR_NULL, SADDLE, crest_candidates,
                                     fill_depth, spill_events)
from posgridder.core.operations import OperationError, apply
from tests.conftest import add_grid

EIGHT = np.ones((3, 3))


def _brute_fill(z, mask, crest, structure=EIGHT):
    """Independent reference: s(x) = the lowest level at which x joins the crest's region."""
    s = np.full(z.shape, np.inf)
    for level in np.unique(z[~mask]):
        labels, _ = ndimage.label((z <= level) & ~mask, structure=structure)
        if labels[crest] == 0:                          # the crest is not under water yet
            continue
        region = labels == labels[crest]
        s[region & np.isinf(s)] = level
    return s


def _surface(project, z, mask=None, inc=100.0, name="top"):
    return add_grid(project, np.asarray(z, float), domain="depth", name=name, inc=inc, mask=mask)


# --------------------------------------------------------------------------- hand-checked prospect
HAND = np.array([            # row 0 is the south; 100 m cells
    [30, 30, 30, 30, 30, 30, 30],
    [30, 20, 18, 18, 20, 30, 30],
    [30, 18, 12, 10, 16, 30, 30],
    [30, 18, 11, 10, 15, 22, 21],
    [30, 20, 16, 14, 17, 30, 30],
    [30, 30, 30, 24, 30, 30, 30],
    [30, 30, 30, 30, 30, 30, 30],
], dtype=float)


def test_hand_checked_prospect(project):
    """Crest 10 m; the fill leaves over the 22 m node to the 21 m node on the east edge.

    By hand: the footprint at 22 m is 4 + 4 + 5 + 4 = 17 nodes. The 21 m edge node lies beyond
    the spill point (downhill on the far side) and is not in the trap. With a constant 5 m
    thickness the column at each node is min(5, 22 − z): rows 12 + 19 + 19 + 17 = 67
    node-metres, times 100 m × 100 m = 0.67 × 10⁶ m³.
    """
    top = _surface(project, HAND)
    (cand,) = crest_candidates(top, min_height=1.0)
    assert cand.crest_depth == 10.0 and cand.spill_depth == 22.0 and cand.spill_type == EDGE
    closure = apply(project, "closure", [top.uid],
                    {"crest": [3, 3], "choice": {"event": 0}}, name="hand closure")
    assert (closure.crest_depth, closure.spill_depth, closure.spill_type) == (10.0, 22.0, EDGE)
    assert closure.n_nodes == 17
    assert not closure.footprint[3, 6] and closure.footprint[3, 5]
    vol = apply(project, "volumes", [closure.uid, top.uid],
                {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 5.0},
                name="hand volumes")
    assert vol.summary["grv_direct_at_spill_1e6m3"] == pytest.approx(0.67, abs=1e-12)


def test_fill_depth_matches_brute_force(project):
    rng = np.random.default_rng(7)
    z = rng.uniform(1000, 1100, (15, 17))
    mask = rng.random((15, 17)) < 0.08
    mask[7, 8] = False
    top = _surface(project, z, mask=mask)
    zz = np.ma.getdata(top.values)          # as stored after the ZMAP round trip
    s = fill_depth(top, (7, 8), 8)
    ref = _brute_fill(zz, mask, (7, 8))
    reach = np.isfinite(ref)
    assert np.array_equal(~np.ma.getmaskarray(s), reach)
    np.testing.assert_array_equal(np.ma.getdata(s)[reach], ref[reach])
    s4 = fill_depth(top, (7, 8), 4)
    ref4 = _brute_fill(zz, mask, (7, 8), structure=ndimage.generate_binary_structure(2, 1))
    np.testing.assert_array_equal(np.ma.getdata(s4)[np.isfinite(ref4)], ref4[np.isfinite(ref4)])


def two_domes(depth_b=2010.0, inc=50.0, n=81):
    """A at 2000 m (west), B at ``depth_b`` (east), a saddle between them, the edge deeper."""
    x = inc * (np.arange(n) - n // 2)
    xx, yy = np.meshgrid(x, x)
    a = 2000 + 1e-4 * ((xx + 700) ** 2 + yy ** 2)
    b = depth_b + 1e-4 * ((xx - 700) ** 2 + yy ** 2)
    return np.minimum(a, b)


def test_saddle_between_two_domes(project):
    """T9: the first event from A is the saddle towards B, at the node level the brute force finds."""
    z = two_domes()
    top = _surface(project, z, inc=50.0)
    zz = np.ma.getdata(top.values)
    crest_a = np.unravel_index(np.argmin(zz), zz.shape)
    s = fill_depth(top, crest_a)
    events = spill_events(top, s, crest_a, min_height=5.0)
    assert events[0].type == SADDLE
    assert zz[events[0].node] == events[0].level        # the event's node is the saddle itself
    crest_b = (40, 54)                                  # x = +700 m
    assert zz[crest_b] == pytest.approx(2010.0, abs=1e-3)
    ref = _brute_fill(zz, np.zeros_like(zz, bool), crest_a)
    assert events[0].level == ref[crest_b]
    assert events[1].type == EDGE and events[1].level > events[0].level


def test_diagonal_saddle_needs_eight_connectivity(project):
    """T10: two basins touching only at a cell corner."""
    z = np.full((6, 6), 9.0)
    z[1:3, 1:3] = 1.0
    z[3:5, 3:5] = 4.0
    z[4, 4] = 2.0
    top = _surface(project, z)
    e8 = spill_events(top, fill_depth(top, (1, 1), 8), (1, 1), connectivity=8, min_height=1.0)
    e4 = spill_events(top, fill_depth(top, (1, 1), 4), (1, 1), connectivity=4, min_height=1.0)
    assert (e8[0].type, e8[0].level) == (SADDLE, 4.0)
    assert e4[0].level == 9.0                           # 4-connected: only over the rim


def test_edge_data_limit_and_interior_null(project):
    """T11: the three boundary kinds are told apart."""
    x = 100.0 * (np.arange(41) - 20)
    xx, yy = np.meshgrid(x, x)
    z = 2000 + 1e-4 * (xx ** 2 + yy ** 2)
    mask = np.zeros_like(z, bool)
    mask[:, :3] = True                                  # a null strip on the west: data limit
    mask[20, 24] = True                                 # a hole 400 m east of the crest
    top = _surface(project, z, mask=mask)
    s = fill_depth(top, (20, 20))
    kinds = {e.type: e.level for e in spill_events(top, s, (20, 20))}
    assert kinds[INTERIOR_NULL] == pytest.approx(2000 + 1e-4 * 300 ** 2, abs=1e-3)
    assert kinds[DATA_LIMIT] < kinds[EDGE]
    order = [e.type for e in spill_events(top, s, (20, 20))]
    assert order[0] == INTERIOR_NULL

    with pytest.raises(OperationError, match="accept that boundary"):
        apply(project, "closure", [top.uid], {"crest": [20, 20], "choice": {"event": 1}}, name="x")
    closure = apply(project, "closure", [top.uid],
                    {"crest": [20, 20], "choice": {"event": 1, "accept": [INTERIOR_NULL]}},
                    name="accepted")
    assert closure.spill_type == DATA_LIMIT
    assert any("interior null" in a for a in closure.assumptions)
    assert any("Null nodes lie inside" in w for w in closure.warnings)


def test_plateau_and_noise_give_one_candidate(project):
    """T12: a flat crest and ±0.5 m noise do not multiply the candidates."""
    x = 100.0 * (np.arange(41) - 20)
    xx, yy = np.meshgrid(x, x)
    z = 2000 + 1e-4 * (xx ** 2 + yy ** 2)
    z[18:23, 18:23] = 2000.0
    z += np.random.default_rng(3).uniform(-0.5, 0.5, z.shape)
    top = _surface(project, z)
    cands = crest_candidates(top, min_height=5.0)
    assert len(cands) == 1
    assert cands[0].spill_type == EDGE
    assert cands[0].height > 150


def test_sub_culmination(project):
    """T13: B joins A's closure at the saddle; the fill there is the saddle depth."""
    z = two_domes()
    top = _surface(project, z, inc=50.0)
    zz = np.ma.getdata(top.values)
    crest_a = tuple(int(v) for v in np.unravel_index(np.argmin(zz), zz.shape))
    closure = apply(project, "closure", [top.uid], {"crest": list(crest_a),
                                                    "choice": {"event": 1}}, name="combined")
    assert closure.spill_type == EDGE
    (sub,) = closure.sub_culminations
    assert closure.fill[40, 54] == pytest.approx(sub["saddle"])
    assert "2010.0" in sub["detail"]
    # The saddle node lies between the domes, at the saddle depth.
    i, j = sub["saddle_node"]
    assert 20 < j < 54 and closure.fill[i, j] == pytest.approx(sub["saddle"])
    assert np.ma.getdata(top.values)[i, j] == pytest.approx(sub["saddle"])


def test_time_surface_refused(project):
    t = add_grid(project, HAND, domain="time", name="twt")
    with pytest.raises(OperationError, match="needs depth"):
        apply(project, "closure", [t.uid], {"crest": [3, 3], "choice": {"event": 0}}, name="x")


def test_manual_spill_needs_a_reason(project):
    top = _surface(project, HAND)
    with pytest.raises(OperationError, match="reason"):
        apply(project, "closure", [top.uid], {"crest": [3, 3], "choice": {"manual": 18.0}},
              name="x")
    c = apply(project, "closure", [top.uid],
              {"crest": [3, 3], "choice": {"manual": 18.0, "reason": "fault seal at 18 m"}},
              name="manual")
    assert c.spill_type == "manual" and c.spill_depth == 18.0
    assert any("fault seal" in a for a in c.assumptions)


def test_leaking_neighbour_is_not_swept_in(project):
    """A neighbour that leaks to the edge before the saddle is beyond the spill, not in the trap.

    Dome B sits against the east edge, so its region reaches the edge shallower than the saddle
    to dome A. The fill from A spills at the saddle; B's nodes, reached only at that level and
    downhill of it, stay out of A's footprint.
    """
    x = 50.0 * np.arange(81)
    xx, yy = np.meshgrid(x, x)
    a = 2000 + 1e-4 * ((xx - 1000) ** 2 + (yy - 2000) ** 2)
    b = 2005 + 1e-4 * ((xx - 3900) ** 2 + (yy - 2000) ** 2)
    top = _surface(project, np.minimum(a, b), inc=50.0)
    zz = np.ma.getdata(top.values)
    crest = [int(v) for v in np.unravel_index(np.argmin(zz), zz.shape)]
    closure = apply(project, "closure", [top.uid], {"crest": crest, "choice": {"event": 0}},
                    name="A")
    assert closure.spill_type == EDGE
    assert not closure.footprint[40, 78]                # dome B's crest
    assert closure.footprint[40, 20]                    # dome A's crest
    assert not closure.sub_culminations
