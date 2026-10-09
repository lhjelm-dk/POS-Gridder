"""Surface import and export, one entry point for every format.

ZMAP+ goes through our own reader (see :mod:`posgridder.io.zmap`); the IRAP formats go through
xtgeo. CPS-3, GeoTIFF and XYZ point files follow in Phase 1.
"""
from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from posgridder.core.model import Surface
from posgridder.io import zmap
from posgridder.io.xtgeo_bridge import from_xtgeo, to_xtgeo


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    extensions: tuple[str, ...]
    binary: bool
    xtgeo_name: str | None = None      # None: handled by our own code


FORMATS: dict[str, Format] = {f.key: f for f in (
    Format("zmap", "ZMAP+ ASCII", (".dat", ".zmap", ".zmp", ".zmapplus"), binary=False),
    Format("irap_ascii", "IRAP classic ASCII", (".irapasc", ".fgr"), binary=False,
           xtgeo_name="irap_ascii"),
    Format("irap_binary", "IRAP binary", (".gri", ".irap", ".irapbin"), binary=True,
           xtgeo_name="irap_binary"),
)}


def guess_format(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    for fmt in FORMATS.values():
        if ext in fmt.extensions:
            return fmt.key
    return None


def _stem(filename: str | None) -> str | None:
    return Path(filename).stem if filename else None


def read_surface(source: str | Path | bytes, fmt: str | None = None, *,
                 filename: str | None = None, name: str | None = None) -> Surface:
    """Read a surface from a path or from the file's bytes (as an upload hands them over)."""
    if isinstance(source, (str, Path)):
        filename = filename or str(source)
    fmt = fmt or (guess_format(filename) if filename else None)
    if fmt not in FORMATS:
        raise ValueError(f"unknown surface format for {filename or 'the upload'!r}; "
                         f"choose one of: {', '.join(f.label for f in FORMATS.values())}")
    name = name or _stem(filename)
    spec = FORMATS[fmt]

    if spec.xtgeo_name is None:
        surface = zmap.read_zmap(source, name=name)
    else:
        import xtgeo

        if isinstance(source, bytes):
            # xtgeo reads from a path for every format, so an upload goes via a temporary file.
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "upload" + (spec.extensions[0]))
                Path(path).write_bytes(source)
                xsurf = xtgeo.surface_from_file(path, fformat=spec.xtgeo_name)
        else:
            xsurf = xtgeo.surface_from_file(str(source), fformat=spec.xtgeo_name)
        surface = from_xtgeo(xsurf, name=name, provenance=f"{spec.label} import")
    return surface


def write_surface(surface: Surface, fmt: str, target: str | Path | None = None) -> bytes:
    """Write ``surface`` in ``fmt``; return the file's bytes, and save them to ``target`` if given."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown surface format {fmt!r}")
    spec = FORMATS[fmt]
    if spec.xtgeo_name is None:
        data = zmap.write_zmap(surface).encode("utf-8")
    else:
        buffer = io.BytesIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "export" + spec.extensions[0])
            to_xtgeo(surface).to_file(path, fformat=spec.xtgeo_name)
            buffer.write(Path(path).read_bytes())
        data = buffer.getvalue()
    if target is not None:
        Path(target).write_bytes(data)
    return data
