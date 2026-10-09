"""The project file: one zip holding everything needed to reproduce every layer.

Layout::

    manifest.json            format version, app version, sources, objects, layer order
    sources/<uid>            the imported files, byte for byte
    objects/<uid>.npz        each surface version's values and mask

Loading checks every source against its SHA-256 and every grid against its content hash, so a
damaged or edited file is refused rather than half-read. :func:`posgridder.core.operations.replay`
then recomputes every layer from the sources as an independent check.
"""
from __future__ import annotations

import io
import json
import zipfile

import numpy as np

from posgridder import __version__
from posgridder.core.model import Derivation, Project, ProjectError, Source, Surface

FORMAT = "pos-gridder-project"
FORMAT_VERSION = 1


def save(project: Project) -> bytes:
    manifest = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "app_version": __version__,
        "layers": list(project.layers),
        "sources": [vars(s) for s in project.sources.values()],
        "objects": [{
            "uid": o.uid, "name": o.name, "domain": o.domain, "crs": o.crs,
            "geometry": [o.xori, o.yori, o.xinc, o.yinc],
            "warnings": list(o.warnings),
            "content_hash": o.content_hash,
            "derivation": {
                "operation": o.derivation.operation,
                "inputs": list(o.derivation.inputs),
                "params_json": o.derivation.params_json,
                "supersedes": o.derivation.supersedes,
                "app_version": o.derivation.app_version,
                "created": o.derivation.created,
            },
        } for o in project.objects.values()],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for uid, data in project.source_bytes.items():
            zf.writestr(f"sources/{uid}", data)
        for o in project.objects.values():
            arrays = io.BytesIO()
            np.savez_compressed(arrays, values=np.ma.getdata(o.values),
                                mask=np.ma.getmaskarray(o.values))
            zf.writestr(f"objects/{o.uid}.npz", arrays.getvalue())
    return buffer.getvalue()


def load(data: bytes) -> Project:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(zf.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ProjectError(f"not a POS-Gridder project file ({exc})") from exc
    if manifest.get("format") != FORMAT:
        raise ProjectError("not a POS-Gridder project file (wrong format tag)")
    if manifest.get("format_version", 0) > FORMAT_VERSION:
        raise ProjectError(f"the project was written by a newer version "
                           f"({manifest.get('app_version')}); this is {__version__}")

    project = Project()
    for s in manifest["sources"]:
        source = Source(**s)
        project.add_source(source, zf.read(f"sources/{source.uid}"))   # checks the SHA-256
    for o in manifest["objects"]:
        with np.load(io.BytesIO(zf.read(f"objects/{o['uid']}.npz"))) as arrays:
            values = np.ma.MaskedArray(arrays["values"], mask=arrays["mask"])
        d = o["derivation"]
        surface = Surface(
            uid=o["uid"], name=o["name"], xori=o["geometry"][0], yori=o["geometry"][1],
            xinc=o["geometry"][2], yinc=o["geometry"][3], values=values, domain=o["domain"],
            crs=o["crs"], warnings=tuple(o["warnings"]),
            derivation=Derivation(operation=d["operation"], inputs=tuple(d["inputs"]),
                                  params_json=d["params_json"], supersedes=d["supersedes"],
                                  app_version=d["app_version"], created=d["created"]))
        if surface.content_hash != o["content_hash"]:
            raise ProjectError(f"layer '{o['name']}' does not match its recorded hash; "
                               "the project file is damaged")
        project.objects[surface.uid] = surface
    missing = [uid for uid in manifest["layers"] if uid not in project.objects]
    if missing:
        raise ProjectError(f"the layer list names {len(missing)} objects the file does not hold")
    project.layers = list(manifest["layers"])
    return project
