"""Importing HCWC Builder files: the percentile CSV, the prospect .hcwc.json, area–depth CSVs.

Each file is kept as a :class:`~posgridder.core.model.Source` (bytes and SHA-256) and the object
is made by a recorded operation, so a distribution or an imported table can be recomputed from
the files exactly as they were read.
"""
from __future__ import annotations

from posgridder.core.model import Project, Source
from posgridder.core.operations import apply


def _add_source(project: Project, filename: str, data: bytes) -> str:
    source = Source.from_bytes(filename, data)
    project.add_source(source, data)
    return source.uid


def _drop(project: Project, uids: list[str]) -> None:
    for uid in uids:
        project.sources.pop(uid, None)
        project.source_bytes.pop(uid, None)


def import_hcwc(project: Project, *, name: str, basis: str, conditioning: str, tails: str,
                csv: tuple[str, bytes] | None = None, json: tuple[str, bytes] | None = None,
                table: dict | None = None, origin: str | None = None, flip_sign: bool = False,
                p_g: float | None = None, f_hmin: float | None = None,
                h_min: float | None = None, apex: float | None = None,
                defaulted: list[str] | tuple[str, ...] = (), supersedes: str | None = None):
    """A contact distribution from a Builder CSV, or from a typed ``table``
    (``{"percentiles": [...], "depths": [...]}``), with an optional .hcwc.json."""
    if (csv is None) == (table is None):
        raise ValueError("give either a percentile CSV or a typed table")
    added, roles, inputs = [], [], []
    try:
        if csv is not None:
            inputs.append(_add_source(project, *csv))
            roles.append("csv")
            added.append(inputs[-1])
        if json is not None:
            inputs.append(_add_source(project, *json))
            roles.append("json")
            added.append(inputs[-1])
        params = {"roles": roles, "basis": basis, "conditioning": conditioning, "tails": tails,
                  "flip_sign": bool(flip_sign), "p_g": p_g, "f_hmin": f_hmin, "h_min": h_min,
                  "apex": apex}
        if defaulted:
            params["defaulted"] = sorted(defaulted)
        if table is not None:
            params["table"] = {"percentiles": [float(v) for v in table["percentiles"]],
                               "depths": [float(v) for v in table["depths"]]}
            params["origin"] = origin or "typed or pasted table"
        return apply(project, "hcwc", inputs, params, name=name, supersedes=supersedes)
    except Exception:
        _drop(project, added)
        raise


def import_area_depth(project: Project, filename: str, data: bytes, *, name: str | None = None):
    """An area–depth table (Builder format) as a volume result, for map-free evaluation."""
    uid = _add_source(project, filename, data)
    try:
        return apply(project, "area_depth_import", [uid], {},
                     name=name or f"{filename} (imported table)")
    except Exception:
        _drop(project, [uid])
        raise
