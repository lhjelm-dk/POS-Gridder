"""Surface import and export.

v1 reads and writes ZMAP+ only (plan §4, decision D8). Importing a file records it as a
:class:`~posgridder.core.model.Source` — bytes and SHA-256 kept — and makes the layer through the
``import`` operation, so the domain, the sign flip and the CRS are parameters of a recorded step,
never edits of the file.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from posgridder.core.model import Project, Source, Surface
from posgridder.io import zmap
from posgridder.io.zmap import RawGrid


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    extensions: tuple[str, ...]


FORMATS: dict[str, Format] = {f.key: f for f in (
    Format("zmap", "ZMAP+ ASCII", (".dat", ".zmap", ".zmp", ".zmapplus")),
)}


def guess_format(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    for fmt in FORMATS.values():
        if ext in fmt.extensions:
            return fmt.key
    return None


def read_grid(data: bytes, fmt: str | None = None, *, filename: str | None = None) -> RawGrid:
    """Parse a grid file's bytes. The name defaults to the file's stem."""
    fmt = fmt or (guess_format(filename) if filename else None)
    if fmt not in FORMATS:
        raise ValueError(f"unknown surface format for {filename or 'the upload'!r}; "
                         f"v1 reads {', '.join(f.label for f in FORMATS.values())}")
    return zmap.read_zmap(data, name=Path(filename).stem if filename else None)


def import_surface(project: Project, filename: str, data: bytes, *, domain: str,
                   flip_sign: bool = False, crs: str | None = None, fmt: str | None = None,
                   name: str | None = None) -> Surface:
    """Add ``data`` to the project as a source and make a layer from it.

    ``domain`` has no default: a TWT grid read as depth gives numbers that look plausible and
    mean nothing, so the caller must say what the values are.
    """
    from posgridder.core.operations import apply

    fmt = fmt or guess_format(filename)
    grid = read_grid(data, fmt, filename=filename)          # fail before anything is added
    source = Source.from_bytes(filename, data)
    project.add_source(source, data)
    params = {"format": fmt, "domain": domain, "flip_sign": bool(flip_sign)}
    if crs:
        params["crs"] = crs
    try:
        return apply(project, "import", [source.uid], params, name=name or grid.name)
    except Exception:
        project.sources.pop(source.uid, None)
        project.source_bytes.pop(source.uid, None)
        raise


def write_surface(surface, fmt: str = "zmap", target: str | Path | None = None) -> bytes:
    """Write ``surface`` in ``fmt``; return the bytes, and save them to ``target`` if given."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown surface format {fmt!r}")
    data = zmap.write_zmap(surface).encode("utf-8")
    if target is not None:
        Path(target).write_bytes(data)
    return data
