"""Contour lines in vector files: GeoPackage, GeoJSON, zipped Shapefile, ASCII ``x y z id``.

GDAL reads from paths, so an uploaded file is written to a temporary directory that is removed
as soon as it has been read (the standing constraint on imported data). A line's level comes
from a chosen attribute or from its Z values; a line whose vertices disagree on Z is left out
and counted.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

VECTOR_EXTENSIONS = {".gpkg": "GeoPackage", ".geojson": "GeoJSON", ".json": "GeoJSON",
                     ".zip": "Shapefile (zipped)"}
ASCII_EXTENSIONS = {".txt", ".xyz", ".dat", ".csv", ".asc"}
Z_LEVEL = "(Z coordinate)"


def kind_of(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in VECTOR_EXTENSIONS:
        return "vector"
    if ext in ASCII_EXTENSIONS:
        return "ascii"
    raise ValueError(f"unsupported contour file {filename!r}; GeoPackage, GeoJSON, a zipped "
                     "Shapefile or ASCII x y z id")


def _read_frame(data: bytes, filename: str):
    import geopandas as gpd

    ext = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "upload" + ext)
        Path(path).write_bytes(data)
        target = f"/vsizip/{path}" if ext == ".zip" else path
        try:
            return gpd.read_file(target)
        except Exception as exc:                      # noqa: BLE001 — reported as a read error
            raise ValueError(f"{filename} could not be read as {VECTOR_EXTENSIONS[ext]} ({exc})") \
                from None


@dataclass
class Inspection:
    n_features: int
    geometry_types: list[str]
    numeric_fields: list[str]
    has_z: bool
    crs: str | None


def inspect(data: bytes, filename: str) -> Inspection:
    """What a vector file holds, so the level field can be chosen before import."""
    if kind_of(filename) == "ascii":
        return Inspection(0, ["ascii x y z id"], [], True, None)
    frame = _read_frame(data, filename)
    numeric = [c for c in frame.columns if c != "geometry"
               and np.issubdtype(frame[c].dtype, np.number)]
    return Inspection(len(frame), sorted(set(frame.geom_type.dropna())), numeric,
                      bool(frame.has_z.any()), frame.crs.to_string() if frame.crs else None)


def _lines_of(geom) -> list:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return list(geom.geoms)
    if geom.geom_type == "Polygon":
        return [geom.exterior, *geom.interiors]
    if geom.geom_type == "MultiPolygon":
        return [r for p in geom.geoms for r in (p.exterior, *p.interiors)]
    return []


def read_contours(data: bytes, filename: str, level_field: str | None = None,
                  z_tolerance: float = 1e-3) -> tuple[list[np.ndarray], list[float], list[str]]:
    """Lines (x, y arrays), their levels, and warnings about what was left out."""
    if kind_of(filename) == "ascii":
        return _read_ascii(data)
    frame = _read_frame(data, filename)
    if level_field is None or level_field == Z_LEVEL:
        level_field = None
    elif level_field not in frame.columns:
        raise ValueError(f"no field {level_field!r} in {filename}")
    lines, levels, warnings = [], [], []
    mixed = no_level = other = 0
    for _, row in frame.iterrows():
        parts = _lines_of(row.geometry)
        if not parts:
            other += 1
            continue
        for part in parts:
            coords = np.asarray(part.coords)
            if len(coords) < 2:
                continue
            if level_field is not None:
                value = row[level_field]
                if value is None or not np.isfinite(float(value)):
                    no_level += 1
                    continue
                level = float(value)
            else:
                if coords.shape[1] < 3:
                    no_level += 1
                    continue
                zs = coords[:, 2]
                if np.ptp(zs) > z_tolerance:
                    mixed += 1
                    continue
                level = float(zs.mean())
            lines.append(coords[:, :2])
            levels.append(level)
    if mixed:
        warnings.append(f"{mixed} lines left out: their vertices do not share one Z level.")
    if no_level:
        warnings.append(f"{no_level} lines left out: no level value.")
    if other:
        warnings.append(f"{other} features left out: not lines or polygons.")
    if not lines:
        raise ValueError("no contour lines with a level were found")
    return lines, levels, warnings


def _read_ascii(data: bytes) -> tuple[list[np.ndarray], list[float], list[str]]:
    """``x y z id`` per line; a new id starts a new contour line."""
    rows = []
    for n, raw in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        parts = re.split(r"[\t,; ]+", line)
        try:
            rows.append((float(parts[0]), float(parts[1]), float(parts[2]), parts[3]))
        except (IndexError, ValueError):
            if not rows:
                continue                                    # a header
            raise ValueError(f"line {n} is not 'x y z id': {line!r}") from None
    lines, levels, warnings = [], [], []
    mixed = 0
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j][3] == rows[i][3]:
            j += 1
        block = np.array([r[:3] for r in rows[i:j]])
        if len(block) >= 2:
            if np.ptp(block[:, 2]) > 1e-3:
                mixed += 1
            else:
                lines.append(block[:, :2])
                levels.append(float(block[:, 2].mean()))
        i = j
    if mixed:
        warnings.append(f"{mixed} lines left out: their points do not share one z level.")
    if not lines:
        raise ValueError("no contour lines found")
    return lines, levels, warnings


def to_geopackage(cs) -> bytes:
    """A contour set as a GeoPackage layer: level, closed, deleted, and the stated CRS as text."""
    import geopandas as gpd
    import shapely

    geoms = [shapely.LineString(cs.line(k)) for k in range(cs.n_lines)]
    frame = gpd.GeoDataFrame({
        "line_id": np.arange(cs.n_lines), "level": cs.levels,
        "closed": [cs.closed(k) for k in range(cs.n_lines)],
        "deleted": cs.deleted.astype(bool), "domain": cs.domain,
        "crs_stated": cs.crs or "",
    }, geometry=geoms, crs=None)
    import warnings

    with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings():
        # The CRS is stated as text in a column (grids carry free-text CRS names, not EPSG
        # codes), so GDAL's "no CRS" warning is expected here.
        warnings.filterwarnings("ignore", message=".*crs.*was not provided")
        path = os.path.join(tmp, "contours.gpkg")
        frame.to_file(path, layer="contours", driver="GPKG")
        return Path(path).read_bytes()
