"""The project file: one zip holding everything needed to reproduce every object.

Layout::

    manifest.json            format version, app version, sources, objects, layer order
    sources/<uid>            the imported files, byte for byte
    objects/<uid>.npz        each object's arrays (grid values and mask, fill field, tables …)

Loading checks every source against its SHA-256 and every object against its content hash, so
a damaged or edited file is refused rather than half-read. :func:`posgridder.core.operations.replay`
then recomputes every object from the sources as an independent check.
"""
from __future__ import annotations

import io
import json
import zipfile

import numpy as np

from posgridder import __version__
from posgridder.core.kinds import KINDS
from posgridder.core.model import Derivation, Project, ProjectError, Source

FORMAT = "pos-gridder-project"
FORMAT_VERSION = 2          # 2: any kind of object (surface, closure, outline, volumes)


def _jsonable(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def save(project: Project) -> bytes:
    objects, arrays = [], {}
    for o in project.objects.values():
        meta, arr = o.to_record()
        d = o.derivation
        objects.append({
            "kind": o.kind, "uid": o.uid, "name": o.name, "warnings": list(o.warnings),
            "content_hash": o.content_hash, "meta": meta,
            "derivation": {"operation": d.operation, "inputs": list(d.inputs),
                           "params_json": d.params_json, "supersedes": d.supersedes,
                           "app_version": d.app_version, "created": d.created},
        })
        arrays[o.uid] = arr
    manifest = {
        "format": FORMAT, "format_version": FORMAT_VERSION, "app_version": __version__,
        "layers": list(project.layers),
        "sources": [vars(s) for s in project.sources.values()],
        "objects": objects,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=_jsonable))
        for uid, data in project.source_bytes.items():
            zf.writestr(f"sources/{uid}", data)
        for uid, arr in arrays.items():
            blob = io.BytesIO()
            np.savez_compressed(blob, **arr)
            zf.writestr(f"objects/{uid}.npz", blob.getvalue())
    return buffer.getvalue()


def load(data: bytes) -> Project:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(zf.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ProjectError(f"not a POS-Gridder project file ({exc})") from exc
    if manifest.get("format") != FORMAT:
        raise ProjectError("not a POS-Gridder project file (wrong format tag)")
    version = manifest.get("format_version", 0)
    if version > FORMAT_VERSION:
        raise ProjectError(f"the project was written by a newer version "
                           f"({manifest.get('app_version')}); this is {__version__}")

    project = Project()
    for s in manifest["sources"]:
        source = Source(**s)
        project.add_source(source, zf.read(f"sources/{source.uid}"))   # checks the SHA-256
    for o in manifest["objects"]:
        if version < 2:                                  # version 1 held surfaces only
            o = dict(o, kind="surface",
                     meta={"domain": o["domain"], "crs": o["crs"], "geometry": o["geometry"]})
        cls = KINDS.get(o["kind"])
        if cls is None:
            raise ProjectError(f"unknown object kind {o['kind']!r} in the project file")
        with np.load(io.BytesIO(zf.read(f"objects/{o['uid']}.npz"))) as npz:
            arrays = {k: npz[k] for k in npz.files}
        d = o["derivation"]
        common = dict(uid=o["uid"], name=o["name"], warnings=tuple(o["warnings"]),
                      derivation=Derivation(operation=d["operation"], inputs=tuple(d["inputs"]),
                                            params_json=d["params_json"],
                                            supersedes=d["supersedes"],
                                            app_version=d["app_version"], created=d["created"]))
        item = cls.from_record(common, o["meta"], arrays)
        if item.content_hash != o["content_hash"]:
            raise ProjectError(f"'{o['name']}' does not match its recorded hash; "
                               "the project file is damaged")
        project.objects[item.uid] = item
    missing = [uid for uid in manifest["layers"] if uid not in project.objects]
    if missing:
        raise ProjectError(f"the layer list names {len(missing)} objects the file does not hold")
    project.layers = list(manifest["layers"])
    return project
