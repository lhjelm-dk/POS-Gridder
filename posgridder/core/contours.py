"""Contour sets and the reconciliation of contours into a surface (plan §5.3, §5.4).

A :class:`ContourSet` is a set of polylines, each with one level. It is either *derived* from a
surface (and then never independent evidence: it records its source and turns stale when the
surface changes) or *imported*. Deleting lines makes a new version of the set; the source surface
is never touched. A surface is made from contours only by the explicit ``contours_to_surface``
operation, with a declared method:

- ``tin`` — linear interpolation on a Delaunay triangulation of the contour vertices. Honours the
  contours exactly and never overshoots; it is flat inside the innermost contour.
- ``tps`` — thin-plate spline (``scipy.interpolate.RBFInterpolator``), local with ``neighbors``
  points. Smooth between contours; it can overshoot and extrapolates a crest inside the
  innermost contour.

Vertices are resampled to about one cell along each line first (feasibility F4: denser
vertices along a line degrade a local thin-plate fit). Nodes outside the convex hull of the data
are null for both methods, so neither invents structure beyond the contours.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

import numpy as np
import shapely

from posgridder.core.model import Derivation, hash_parts, read_only

METHODS = {"tin": "Linear TIN (honours contours, no overshoot)",
           "tps": "Thin-plate spline (smooth, may overshoot)"}
TPS_NEIGHBOURS = 150                  # F4: fewer neighbours degrade the fit across contours
#: Chosen by the D9 benchmark (docs/BENCHMARK.md, posgridder/core/benchmark.py): the thin-plate
#: spline meets every threshold; TIN fails on the two-dome case (flat top, GRV −4.7 % at 10 m).
DEFAULT_METHOD = "tps"


@dataclass(frozen=True)
class ContourSet:
    kind: ClassVar[str] = "contours"
    uid: str
    name: str
    derivation: Derivation
    coords: np.ndarray                 # (N, 2) all vertices, line after line
    offsets: np.ndarray                # (L + 1,) start of each line in coords
    levels: np.ndarray                 # (L,)
    deleted: np.ndarray                # (L,) bool
    domain: str
    origin: str
    source_uid: str | None = None      # the surface it was derived from, if any
    crs: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        coords = np.asarray(self.coords, dtype=float).reshape(-1, 2)
        offsets = np.asarray(self.offsets, dtype=np.int64)
        levels = np.asarray(self.levels, dtype=float)
        deleted = np.asarray(self.deleted, dtype=bool)
        if offsets.size != levels.size + 1 or deleted.size != levels.size:
            raise ValueError("offsets, levels and deleted flags do not match")
        if offsets[0] != 0 or offsets[-1] != len(coords) or (np.diff(offsets) < 2).any():
            raise ValueError("every line needs at least two vertices")
        for name, arr in (("coords", coords), ("offsets", offsets), ("levels", levels),
                          ("deleted", deleted)):
            object.__setattr__(self, name, read_only(arr))

    # ------------------------------------------------------------------ lines
    @property
    def n_lines(self) -> int:
        return int(self.levels.size)

    def line(self, k: int) -> np.ndarray:
        return self.coords[self.offsets[k]:self.offsets[k + 1]]

    def closed(self, k: int) -> bool:
        pts = self.line(k)
        return len(pts) >= 4 and bool(np.allclose(pts[0], pts[-1]))

    def area_km2(self, k: int) -> float | None:
        """Area enclosed by a closed line; None for an open one."""
        if not self.closed(k):
            return None
        return float(shapely.Polygon(self.line(k)).area / 1e6)

    def active(self) -> list[int]:
        return [k for k in range(self.n_lines) if not self.deleted[k]]

    def with_deleted(self, delete=(), restore=()) -> np.ndarray:
        flags = np.array(self.deleted, copy=True)
        flags[list(delete)] = True
        flags[list(restore)] = False
        return flags

    # ------------------------------------------------------------------ interface
    @property
    def content_hash(self) -> str:
        return hash_parts(self.coords, self.offsets, self.levels, self.deleted, self.domain,
                          self.origin, self.source_uid, self.crs)

    def renamed(self, name: str) -> "ContourSet":
        return replace(self, name=name)

    def to_record(self):
        meta = {"domain": self.domain, "origin": self.origin, "source_uid": self.source_uid,
                "crs": self.crs}
        return meta, {"coords": self.coords, "offsets": self.offsets, "levels": self.levels,
                      "deleted": self.deleted}

    @classmethod
    def from_record(cls, common, meta, arrays) -> "ContourSet":
        return cls(coords=arrays["coords"], offsets=arrays["offsets"], levels=arrays["levels"],
                   deleted=arrays["deleted"], **meta, **common)


def pack(lines: list[np.ndarray], levels: list[float]) -> dict:
    lines = [np.asarray(ln, dtype=float) for ln in lines]
    offsets = np.concatenate([[0], np.cumsum([len(ln) for ln in lines])]).astype(np.int64)
    coords = np.vstack(lines) if lines else np.zeros((0, 2))
    return dict(coords=coords, offsets=offsets, levels=np.asarray(levels, dtype=float),
                deleted=np.zeros(len(lines), dtype=bool))


# --------------------------------------------------------------------------- contouring
def contour_levels(zmin: float, zmax: float, interval: float, start: float | None = None,
                   stop: float | None = None) -> np.ndarray:
    if not interval > 0:
        raise ValueError("the contour interval must be positive")
    first = start if start is not None else np.ceil(zmin / interval) * interval
    last = stop if stop is not None else zmax
    levels = np.arange(first, last + interval * 1e-9, interval)
    levels = levels[(levels > zmin) & (levels < zmax)]
    if levels.size > 2000:
        raise ValueError(f"{levels.size} levels is too many; widen the interval")
    return levels


def contour_surface(surface, levels) -> dict:
    """Lines of ``surface`` at each level (contourpy, linear between nodes)."""
    import contourpy

    gen = contourpy.contour_generator(surface.x, surface.y, surface.values.copy(),
                                      line_type=contourpy.LineType.Separate)
    lines, lv = [], []
    for level in levels:
        for line in gen.lines(float(level)):
            if len(line) >= 2:
                lines.append(line)
                lv.append(float(level))
    if not lines:
        raise ValueError("no contour lines at these levels")
    return pack(lines, lv)


# --------------------------------------------------------------------------- reconciliation
def _resample(line: np.ndarray, spacing: float) -> np.ndarray:
    seg = np.hypot(*np.diff(line, axis=0).T)
    dist = np.concatenate([[0.0], np.cumsum(seg)])
    if dist[-1] <= spacing:
        return line
    s = np.linspace(0.0, dist[-1], int(np.ceil(dist[-1] / spacing)) + 1)
    return np.column_stack([np.interp(s, dist, line[:, 0]), np.interp(s, dist, line[:, 1])])


def data_points(cs: ContourSet, spacing: float, crest_points=()) -> np.ndarray:
    """(x, y, z) from the active lines, resampled to ``spacing``, plus any crest points."""
    rows = []
    for k in cs.active():
        pts = _resample(cs.line(k), spacing)
        rows.append(np.column_stack([pts, np.full(len(pts), cs.levels[k])]))
    for p in crest_points:
        rows.append(np.asarray(p, dtype=float).reshape(1, 3))
    if not rows:
        raise ValueError("no active contour lines")
    pts = np.vstack(rows)
    # Duplicate positions (closed rings repeat their first vertex) break the triangulation.
    _, keep = np.unique(np.round(pts[:, :2], 6), axis=0, return_index=True)
    return pts[np.sort(keep)]


def grid_from_points(points: np.ndarray, geometry: dict, method: str,
                     neighbors: int = TPS_NEIGHBOURS) -> tuple[np.ma.MaskedArray, dict]:
    """Interpolate (x, y, z) onto a grid; nodes outside the data hull are null."""
    from scipy.interpolate import LinearNDInterpolator, RBFInterpolator
    from scipy.spatial import Delaunay

    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}")
    if len(points) < 3:
        raise ValueError("at least three points are needed")
    xori, yori, inc = geometry["xori"], geometry["yori"], geometry["inc"]
    ncol, nrow = int(geometry["ncol"]), int(geometry["nrow"])
    x = xori + inc * np.arange(ncol)
    y = yori + inc * np.arange(nrow)
    xx, yy = np.meshgrid(x, y)
    nodes = np.column_stack([xx.ravel(), yy.ravel()])
    centre = points[:, :2].mean(axis=0)            # local origin: TPS on 6e6 m coordinates
    xy = points[:, :2] - centre                    # loses precision otherwise
    tri = Delaunay(xy)
    inside = tri.find_simplex(nodes - centre) >= 0
    out = np.full(len(nodes), np.nan)
    if method == "tin":
        out[inside] = LinearNDInterpolator(tri, points[:, 2])(nodes[inside] - centre)
    else:
        k = int(min(neighbors, len(points)))
        rbf = RBFInterpolator(xy, points[:, 2], kernel="thin_plate_spline", neighbors=k)
        out[inside] = rbf(nodes[inside] - centre)
    z = out.reshape(nrow, ncol)
    vals = z[np.isfinite(z)]
    lo, hi = float(points[:, 2].min()), float(points[:, 2].max())
    report = {
        "points": int(len(points)), "nodes_valid": int(np.isfinite(z).sum()),
        "overshoot_shallow_m": float(max(0.0, lo - vals.min())) if vals.size else 0.0,
        "overshoot_deep_m": float(max(0.0, vals.max() - hi)) if vals.size else 0.0,
        "data_min": lo, "data_max": hi,
    }
    return np.ma.masked_invalid(z), report


def geometry_for(cs: ContourSet, inc: float, margin_cells: int = 1) -> dict:
    """A grid covering the active lines, at ``inc``, snapped to whole multiples of ``inc``."""
    pts = np.vstack([cs.line(k) for k in cs.active()])
    x0 = np.floor(pts[:, 0].min() / inc) * inc - margin_cells * inc
    y0 = np.floor(pts[:, 1].min() / inc) * inc - margin_cells * inc
    x1 = np.ceil(pts[:, 0].max() / inc) * inc + margin_cells * inc
    y1 = np.ceil(pts[:, 1].max() / inc) * inc + margin_cells * inc
    ncol, nrow = int(round((x1 - x0) / inc)) + 1, int(round((y1 - y0) / inc)) + 1
    if ncol * nrow > 4_000_000:
        raise ValueError(f"{ncol} × {nrow} nodes is too large; use a coarser cell size")
    return {"xori": float(x0), "yori": float(y0), "inc": float(inc), "ncol": ncol, "nrow": nrow}
