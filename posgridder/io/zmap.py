"""ZMAP+ ASCII grids, read and written by our own code.

xtgeo reads the geometry of a ZMAP+ file correctly but treats only its own undefined value
(1E+33) as null, so a file whose header declares 1E+30 — the ZIMS and Petrel default — comes in
with its nulls as real numbers. This reader takes the null value from the header.

The layout::

    ! comment lines, optionally "COORDINATE REFERENCE SYSTEM: ED50-UTM32"
    @name HEADER, GRID, 5                       <- nodes per line
     15, 0.1E+31, , 7, 1                        <- field width, null value, null text, decimals, start column
     238, 217, xmin, xmax, ymin, ymax           <- rows, columns, extent
     0.0, 0.0, 0.0                              <- unused here (ZIMS writes 0, dx, dy)
    @
    values, column by column from the west, each column from north to south,
    each column starting on a new line

The grid is node-registered: ``xmin`` and ``xmax`` are the first and last node.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np

from posgridder.core.model import Surface

DEFAULT_NULL = 1.0e30


def _text(source: str | Path | bytes | io.IOBase) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8", errors="replace")
    if isinstance(source, io.IOBase):
        data = source.read()
        return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    return Path(source).read_text(encoding="utf-8", errors="replace")


def _fields(line: str) -> list[str]:
    return [f.strip() for f in line.split(",")]


def read_zmap(source: str | Path | bytes | io.IOBase, name: str | None = None) -> Surface:
    """Read a ZMAP+ grid. ``source`` is a path, the file's bytes, or an open file."""
    lines = _text(source).splitlines()

    crs = None
    header: list[str] = []
    data_start = None
    in_header = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("!"):
            m = re.search(r"COORDINATE REFERENCE SYSTEM\s*:\s*(.+)$", line, re.I)
            if m:
                crs = m.group(1).strip()
            continue
        if line.startswith("@"):
            if in_header:          # the closing "@"
                data_start = i + 1
                break
            in_header = True
            header.append(line[1:])
            continue
        if in_header:
            header.append(line)
    if data_start is None or len(header) < 3:
        raise ValueError("not a ZMAP+ grid: no '@ ... @' header block found")

    first = _fields(header[0])
    if len(first) < 2 or first[1].upper() != "GRID":
        raise ValueError(f"not a ZMAP+ GRID file (header says {header[0]!r})")
    grid_name = re.sub(r"\s*HEADER\s*$", "", first[0], flags=re.I).strip()

    # The header's numeric lines may wrap; read them as one stream of comma fields.
    nums = [f for line in header[1:] for f in _fields(line)]
    null_value = DEFAULT_NULL
    for candidate in (nums[1], nums[2]):
        try:
            null_value = float(candidate)
            break
        except ValueError:
            continue
    try:
        nrow, ncol = int(float(nums[5])), int(float(nums[6]))
        xmin, xmax, ymin, ymax = (float(v) for v in nums[7:11])
    except (IndexError, ValueError) as exc:
        raise ValueError("ZMAP+ header is missing rows, columns or the extent") from exc
    if nrow < 2 or ncol < 2:
        raise ValueError(f"ZMAP+ grid of {nrow} x {ncol} nodes is too small")

    tokens = " ".join(lines[data_start:]).split()
    if len(tokens) < nrow * ncol:
        raise ValueError(f"ZMAP+ data block has {len(tokens)} values; the header promises "
                         f"{nrow} x {ncol} = {nrow * ncol}")
    flat = np.array(tokens[: nrow * ncol], dtype=float)

    # Column-major from the north-west corner: reshape to (ncol, nrow), transpose to
    # (nrow, ncol) with row 0 in the north, then flip so row 0 is in the south.
    grid = flat.reshape(ncol, nrow).T[::-1, :]
    mask = np.isclose(grid, null_value, rtol=1e-6) | ~np.isfinite(grid)

    return Surface(
        name=name or grid_name or "zmap grid",
        xori=xmin,
        yori=ymin,
        xinc=(xmax - xmin) / (ncol - 1),
        yinc=(ymax - ymin) / (nrow - 1),
        values=np.ma.MaskedArray(grid, mask=mask),
        crs=crs,
        provenance="ZMAP+ import",
    )


def write_zmap(surface: Surface, target: str | Path | None = None, *,
               nodes_per_line: int = 5, null_value: float = DEFAULT_NULL) -> str:
    """Write ``surface`` as ZMAP+ and return the text; also saved to ``target`` if given."""
    width, decimals = 15, 7
    name = re.sub(r"[,@!]", "_", surface.name)
    out = ["!", f"!     GRID NAME : {name}", "!     WRITTEN BY POS-Gridder"]
    if surface.crs:
        out.append(f"!     COORDINATE REFERENCE SYSTEM: {surface.crs}")
    out += [
        "!",
        f"@{name} HEADER, GRID, {nodes_per_line}",
        f" {width}, {null_value:.7E}, , {decimals}, 1",
        f" {surface.nrow}, {surface.ncol}, {surface.xori:.4f}, {surface.xmax:.4f}, "
        f"{surface.yori:.4f}, {surface.ymax:.4f}",
        f" 0.0000, {surface.xinc:.4f}, {surface.yinc:.4f}",
        "@",
    ]
    values = surface.values.filled(null_value)[::-1, :]      # row 0 back to the north
    for j in range(surface.ncol):
        column = values[:, j]
        for k in range(0, column.size, nodes_per_line):
            out.append("".join(f"{v:{width}.{decimals}E}" for v in column[k:k + nodes_per_line]))
    text = "\n".join(out) + "\n"
    if target is not None:
        Path(target).write_text(text, encoding="utf-8", newline="\n")
    return text
