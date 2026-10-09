"""The results report: everything needed to read a result and to reproduce it (plan §5.10).

One JSON document per result: its summary, assumptions and warnings, the chain of operations
with their parameters back to the source files, and each source's SHA-256.
"""
from __future__ import annotations

import json

import numpy as np

from posgridder import __version__
from posgridder.core.model import Project


def _ancestry(project: Project, uid: str, seen: set) -> list[dict]:
    if uid in seen:
        return []
    seen.add(uid)
    if uid in project.sources:
        s = project.sources[uid]
        return [{"source": s.filename, "sha256": s.sha256, "bytes": s.size,
                 "imported": s.imported}]
    obj = project.objects[uid]
    steps = []
    for inp in obj.derivation.inputs:
        steps += _ancestry(project, inp, seen)
    steps.append({"name": obj.name, "kind": obj.kind, "uid": obj.uid,
                  "operation": obj.derivation.operation, "parameters": obj.derivation.params,
                  "inputs": list(obj.derivation.inputs), "content_hash": obj.content_hash,
                  "created": obj.derivation.created, "app_version": obj.derivation.app_version})
    return steps


def _plain(value):
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def results_json(project: Project, uid: str) -> str:
    obj = project.objects[uid]
    doc = {
        "report": "POS-Gridder result", "app_version": __version__,
        "name": obj.name, "kind": obj.kind, "uid": obj.uid,
        "stale": project.stale_reasons(uid),
        "summary": getattr(obj, "summary", {}),
        "assumptions": list(getattr(obj, "assumptions", ())),
        "warnings": list(obj.warnings),
        "lineage": _ancestry(project, uid, set()),
    }
    table = getattr(obj, "table", None)
    if table is not None:
        doc["table"] = {"columns": list(table.columns), "rows": table.to_numpy(float).tolist()}
    return json.dumps(doc, indent=2, default=_plain)
