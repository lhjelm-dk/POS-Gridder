"""Project save, load and replay (plan §6.2, T22)."""
import io
import json
import zipfile

import numpy as np
import pytest

from posgridder.core.model import ProjectError
from posgridder.core.operations import apply, replay
from posgridder.io import project_file
from tests.conftest import add_grid


def _build(project, dome):
    t = add_grid(project, np.linspace(900, 1600, 21 * 31).reshape(21, 31), domain="time",
                 name="twt")
    d = apply(project, "depth_convert", [t.uid], {"method": "v0k", "v0": 1750.0, "k": 0.45},
              name="depth")
    base = apply(project, "offset", [d.uid], {"constant": 80.0}, name="base")
    apply(project, "subtract", [base.uid, d.uid], name="thickness")
    apply(project, "smooth", [dome.uid], {"passes": 2}, name="dome", replace=True)
    project.rename(base.uid, "base renamed")
    return project


def test_save_load_replay_identical(project, dome):
    """T22: save → load → recompute gives identical layers, hashes and history."""
    _build(project, dome)
    loaded = project_file.load(project_file.save(project))
    assert loaded.layers == project.layers
    assert set(loaded.objects) == set(project.objects)
    for uid, obj in project.objects.items():
        assert loaded.objects[uid].content_hash == obj.content_hash
        assert loaded.objects[uid].derivation == obj.derivation
        assert loaded.objects[uid].name == obj.name
    rows = replay(loaded)
    assert len(rows) == len(project.objects)
    assert all(r.identical for r in rows), [(r.name, r.max_abs_diff) for r in rows]
    assert {s.sha256 for s in loaded.sources.values()} == \
        {s.sha256 for s in project.sources.values()}


def test_staleness_survives_a_round_trip(project, dome):
    thick = apply(project, "subtract", [dome.uid, dome.uid], name="zero")
    apply(project, "scale", [dome.uid], {"factor": 1.01}, name="dome", replace=True)
    loaded = project_file.load(project_file.save(project))
    assert loaded.is_stale(thick.uid)


def _rewrite(blob: bytes, edit) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(blob))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, edit(item.filename, src.read(item.filename)))
    return out.getvalue()


def test_tampered_source_is_refused(project, dome):
    blob = project_file.save(project)
    bad = _rewrite(blob, lambda n, d: d.replace(b"E+03", b"E+04", 1) if n.startswith("sources/") else d)
    with pytest.raises(ProjectError, match="SHA-256"):
        project_file.load(bad)


def test_tampered_grid_is_refused(project, dome):
    blob = project_file.save(project)

    def edit(name, data):
        if not name.startswith("objects/"):
            return data
        with np.load(io.BytesIO(data)) as a:
            values, mask = a["values"].copy(), a["mask"]
        values[10, 10] += 1.0            # a valid node: nulls do not enter the hash
        buf = io.BytesIO()
        np.savez_compressed(buf, values=values, mask=mask)
        return buf.getvalue()

    with pytest.raises(ProjectError, match="hash"):
        project_file.load(_rewrite(blob, edit))


def test_not_a_project():
    with pytest.raises(ProjectError):
        project_file.load(b"hello")
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "something else"}))
    with pytest.raises(ProjectError, match="format"):
        project_file.load(blob.getvalue())


def test_all_kinds_round_trip_and_replay(project):
    """T22 for every kind: closure, outline and volume result reproduce from the source file."""
    from posgridder.io.examples import load_example

    top_uid = load_example(project)
    top = project.objects[top_uid]
    zz = np.ma.getdata(top.values)
    crest = [int(v) for v in np.unravel_index(np.nanargmin(np.where(top.values.mask, np.inf, zz)),
                                              zz.shape)]
    closure = apply(project, "closure", [top_uid], {"crest": crest, "choice": {"event": 0}},
                    name="closure")
    outline = apply(project, "outline_from_closure", [closure.uid], name="outline")
    vol = apply(project, "volumes", [closure.uid, top_uid, outline.uid],
                {"roles": ["closure", "top", "outline"], "geometry": "top_constant",
                 "thickness": 40.0}, name="volumes")
    loaded = project_file.load(project_file.save(project))
    assert {o.kind for o in loaded.objects.values()} == {"surface", "closure", "outline", "volumes"}
    assert loaded.objects[vol.uid].content_hash == vol.content_hash
    assert loaded.objects[closure.uid].spill_depth == closure.spill_depth
    rows = replay(loaded)
    assert all(r.identical for r in rows), [(r.name, r.operation) for r in rows if not r.identical]


def test_project_file_from_version_0_1_loads():
    """A project saved by version 0.1 (Phase 4) still opens: every hash checks out."""
    from pathlib import Path

    blob = (Path(__file__).parent / "fixtures" / "project_v0_1_phase4.posgrid.zip").read_bytes()
    loaded = project_file.load(blob)
    kinds = {o.kind for o in loaded.objects.values()}
    assert {"surface", "closure", "hcwc", "posmap", "contours"} <= kinds
    rows = replay(loaded)
    assert all(r.made_by == "0.1.0" for r in rows)
    # Surfaces, contours and the distribution recompute exactly; the closure's recorded
    # assumptions gained a line in 0.2 (faults), so it and the map made from it differ.
    same = {r.operation: r.identical for r in rows}
    assert same["import"] and same["contour"] and same["hcwc"]
