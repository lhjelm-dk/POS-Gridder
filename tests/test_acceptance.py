"""Phase 5 acceptance: the whole workflow on real data, saved, reopened and reproduced.

The GEUS Top Gassum TWT grid (data/private, untracked) and the real HCWC Builder export
(tests/fixtures). The Builder prospect sits at about 2050 m and the GEUS closure near 960 m, so
the contacts are re-anchored to the map crest; the Builder's own spill then disagrees with the
map spill, and the app must say so.
"""
from pathlib import Path

import numpy as np
import pytest

from posgridder.core.closure import crest_candidates
from posgridder.core.contours import DEFAULT_METHOD
from posgridder.core.operations import apply, replay
from posgridder.io import project_file
from posgridder.io.hcwc_files import import_hcwc
from posgridder.io.surfaces import import_surface

FIX = Path(__file__).parent / "fixtures" / "hcwc_builder"


def test_geus_workflow_reproduces_from_the_saved_project(project, geus_path):
    p = project
    twt = import_surface(p, geus_path.name, geus_path.read_bytes(), domain="time", flip_sign=True)
    depth = apply(p, "depth_convert", [twt.uid], {"method": "v0k", "v0": 1800.0, "k": 0.5},
                  name="Top Gassum depth")
    cand = crest_candidates(depth, min_height=10.0)[0]
    closure = apply(p, "closure", [depth.uid], {"crest": list(cand.node), "min_height": 10.0,
                                                "choice": {"event": 0}}, name="Top Gassum closure")
    vol = apply(p, "volumes", [closure.uid, depth.uid],
                {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 50.0},
                name="GRV 50 m")
    dist = import_hcwc(p, name="Builder contacts", basis="geological", conditioning="h_min",
                       tails="truncated", f_hmin=0.8891, h_min=120.0,
                       csv=("hcwc_percentiles_geological.csv",
                            (FIX / "hcwc_percentiles_geological.csv").read_bytes()),
                       json=("example.hcwc.json",
                             (FIX / "example_prospect_spill.hcwc.json").read_bytes()))
    pos_a = apply(p, "pos_map", [closure.uid, depth.uid, dist.uid],
                  {"roles": ["closure", "top", "hcwc"], "event": "a", "anchoring": "reanchor"},
                  name="POS (a)")
    pos_b = apply(p, "pos_map", [closure.uid, depth.uid, dist.uid],
                  {"roles": ["closure", "top", "hcwc"], "event": "b", "anchoring": "reanchor"},
                  name="POS (b)")
    pct = apply(p, "percentile_volumes", [vol.uid, dist.uid], {"anchoring": "reanchor"},
                name="GRV by percentile")
    cs = apply(p, "contour", [depth.uid], {"interval": 10.0}, name="contours 10 m")
    cs2 = apply(p, "contour_edit", [cs.uid], {"delete": [0]}, name=cs.name, replace=True)
    apply(p, "contours_to_surface", [cs2.uid, depth.uid],
          {"roles": ["contours", "template"], "method": DEFAULT_METHOD}, name="regridded")

    # The geology the app reports.
    prospect = 0.40824 * 0.8891
    assert pos_a.summary["pos_at_crest"] == pytest.approx(prospect, rel=1e-9)
    assert pos_a.summary["shift_m"] == pytest.approx(closure.crest_depth - 2050.0)
    assert any("Builder prospect" in w for w in pos_a.warnings)      # C5: spills disagree
    assert np.nanmax(pos_b.pos) <= prospect + 1e-12
    assert (pos_b.category == 3).any()                               # band above apex + h_min
    s = pct.summary
    assert 0 < s["grv_P90_1e6m3"] <= s["grv_P50_1e6m3"] <= s["grv_P10_1e6m3"]
    assert s["grv_P10_1e6m3"] <= vol.summary["grv_direct_at_spill_1e6m3"] + 1e-9

    # Saved, reopened, recomputed from the source files: identical.
    loaded = project_file.load(project_file.save(p))
    assert loaded.layers == p.layers and set(loaded.objects) == set(p.objects)
    rows = replay(loaded)
    assert all(r.identical for r in rows), [(r.name, r.operation) for r in rows if not r.identical]
    assert len(rows) == len(p.objects)
