"""Time the workflow on the GEUS grid (51 646 nodes), step by step and as app reruns.

    python scripts/profile_geus.py

Needs data/private/HVN_Top Gassum_TWTgrd250m_3xsm_geus2023.dat. Prints a table; the numbers go
into docs/PERFORMANCE.md by hand.
"""
from __future__ import annotations

import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# The app run below must not write into the user's autosave folder.
os.environ["POSGRIDDER_AUTOSAVE"] = "off"
warnings.filterwarnings("ignore")

from posgridder.core.closure import crest_candidates  # noqa: E402
from posgridder.core.model import Project  # noqa: E402
from posgridder.core.operations import apply, replay  # noqa: E402
from posgridder.io import project_file  # noqa: E402
from posgridder.io.hcwc_files import import_hcwc  # noqa: E402
from posgridder.io.surfaces import import_surface  # noqa: E402

GEUS = ROOT / "data" / "private" / "HVN_Top Gassum_TWTgrd250m_3xsm_geus2023.dat"


def timed(label, fn, rows):
    t = time.perf_counter()
    out = fn()
    rows.append((label, time.perf_counter() - t))
    return out


def build(rows) -> Project:
    p = Project()
    t = timed("import ZMAP+", lambda: import_surface(p, GEUS.name, GEUS.read_bytes(),
                                                     domain="time", flip_sign=True), rows)
    d = timed("depth conversion (V0+kZ)", lambda: apply(
        p, "depth_convert", [t.uid], {"method": "v0k", "v0": 1800.0, "k": 0.5},
        name="Top Gassum depth"), rows)
    cands = timed("crest candidates", lambda: crest_candidates(d, min_height=10.0), rows)
    c = timed("closure (fill, events, footprint)", lambda: apply(
        p, "closure", [d.uid], {"crest": list(cands[0].node), "min_height": 10.0,
                                "choice": {"event": 0}}, name="main closure"), rows)
    v = timed("volumes (area-depth, 3 GRV curves)", lambda: apply(
        p, "volumes", [c.uid, d.uid], {"roles": ["closure", "top"], "geometry": "top_constant",
                                       "thickness": 50.0}, name="volumes"), rows)
    lo, hi = c.crest_depth + 20, c.spill_depth + 10
    pct = np.arange(100, -1, -1.0)
    dist = timed("contact distribution (typed table)", lambda: import_hcwc(
        p, name="contacts", basis="geological", conditioning="unconditioned", tails="raw",
        table={"percentiles": pct, "depths": lo + (hi - lo) * (100 - pct) / 100},
        p_g=0.35, h_min=20.0, apex=c.crest_depth), rows)
    timed("POS map (event a)", lambda: apply(
        p, "pos_map", [c.uid, d.uid, dist.uid], {"roles": ["closure", "top", "hcwc"],
                                                  "event": "a", "anchoring": "as_is"},
        name="POS a"), rows)
    timed("area/GRV by percentile", lambda: apply(
        p, "percentile_volumes", [v.uid, dist.uid], {}, name="by percentile"), rows)
    cs = timed("contours at 10 m", lambda: apply(p, "contour", [d.uid], {"interval": 10.0},
                                                 name="contours 10"), rows)
    timed("contours -> surface (TPS)", lambda: apply(
        p, "contours_to_surface", [cs.uid, d.uid], {"roles": ["contours", "template"],
                                                    "method": "tps"}, name="regrid"), rows)
    return p


def main() -> None:
    if not GEUS.exists():
        sys.exit(f"missing {GEUS}")
    rows: list[tuple[str, float]] = []
    p = build(rows)
    blob = timed("project save", lambda: project_file.save(p), rows)
    loaded = timed("project load (hash checks)", lambda: project_file.load(blob), rows)
    timed("replay check (every object)", lambda: replay(loaded), rows)

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.session_state["project"] = p
    timed("app: first run, full project", lambda: at.run(), rows)
    timed("app: rerun (no change)", lambda: at.run(), rows)

    width = max(len(r[0]) for r in rows)
    print(f"{'step':<{width}}  seconds")
    for label, sec in rows:
        print(f"{label:<{width}}  {sec:7.2f}")
    print(f"project file: {len(blob) / 1e6:.1f} MB, {len(p.objects)} objects")


if __name__ == "__main__":
    main()
