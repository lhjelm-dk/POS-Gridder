"""The objects a POS-Gridder project holds.

A :class:`Surface` is a regular, unrotated grid. Its ``values`` are a masked array of shape
``(nrow, ncol)`` with **row 0 at the southern edge** (``yori``) and column 0 at the western edge
(``xori``), so ``values[i, j]`` sits at ``(x[j], y[i])``. That is the orientation contourpy and
Plotly expect, and it is the transpose of xtgeo's ``(ncol, nrow)``; the bridge in
:mod:`posgridder.io.xtgeo_bridge` does the conversion in one place.

Depth is stored positive down. Files that store it negative are flipped on import, and the
flip is recorded in ``provenance``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

#: What a surface's values measure. ``other`` covers anything the tool has no rules for.
DOMAINS: tuple[str, ...] = ("depth", "time", "thickness", "velocity", "pos", "other")


@dataclass
class Surface:
    name: str
    xori: float
    yori: float
    xinc: float
    yinc: float
    values: np.ma.MaskedArray
    domain: str = "other"
    unit: str = ""
    crs: str | None = None
    provenance: str = ""

    def __post_init__(self) -> None:
        values = np.ma.masked_invalid(np.ma.asarray(self.values, dtype=float))
        if values.ndim != 2 or min(values.shape) < 2:
            raise ValueError(f"a surface needs a 2-D grid of at least 2 x 2 nodes, got {values.shape}")
        if not (self.xinc > 0 and self.yinc > 0):
            raise ValueError("grid increments must be positive")
        if self.domain not in DOMAINS:
            raise ValueError(f"unknown domain {self.domain!r}; expected one of {DOMAINS}")
        # A full mask array, never the scalar `nomask`, so callers can index it freely.
        self.values = np.ma.MaskedArray(values.filled(np.nan), mask=np.ma.getmaskarray(values))

    # ------------------------------------------------------------------ geometry
    @property
    def nrow(self) -> int:
        return int(self.values.shape[0])

    @property
    def ncol(self) -> int:
        return int(self.values.shape[1])

    @property
    def xmax(self) -> float:
        return self.xori + (self.ncol - 1) * self.xinc

    @property
    def ymax(self) -> float:
        return self.yori + (self.nrow - 1) * self.yinc

    @property
    def x(self) -> np.ndarray:
        return self.xori + self.xinc * np.arange(self.ncol)

    @property
    def y(self) -> np.ndarray:
        return self.yori + self.yinc * np.arange(self.nrow)

    def same_geometry(self, other: "Surface", rtol: float = 1e-9) -> bool:
        """True when both grids have the same nodes, so arithmetic needs no resampling."""
        return (self.values.shape == other.values.shape
                and np.allclose([self.xori, self.yori, self.xinc, self.yinc],
                                [other.xori, other.yori, other.xinc, other.yinc], rtol=rtol))

    # ------------------------------------------------------------------ statistics
    @property
    def n_valid(self) -> int:
        return int(self.values.count())

    def stats(self) -> dict[str, float | int]:
        v = self.values.compressed()
        return {
            "nodes": self.nrow * self.ncol,
            "valid": int(v.size),
            "min": float(v.min()) if v.size else float("nan"),
            "max": float(v.max()) if v.size else float("nan"),
            "mean": float(v.mean()) if v.size else float("nan"),
        }

    # ------------------------------------------------------------------ copies
    def copy(self, name: str | None = None) -> "Surface":
        """An independent copy; editing one never changes the other."""
        return replace(self, name=name or self.name, values=self.values.copy(),
                       provenance=self.provenance)


@dataclass
class Project:
    """Every object in the session, keyed by a unique name."""
    surfaces: dict[str, Surface] = field(default_factory=dict)

    def unique_name(self, name: str) -> str:
        """``name``, or ``name (2)``, ``name (3)``… if it is taken."""
        base = name.strip() or "surface"
        if base not in self.surfaces:
            return base
        n = 2
        while f"{base} ({n})" in self.surfaces:
            n += 1
        return f"{base} ({n})"

    def add(self, surface: Surface) -> str:
        """Add under a unique name and return the name used."""
        surface.name = self.unique_name(surface.name)
        self.surfaces[surface.name] = surface
        return surface.name

    def copy_surface(self, name: str, new_name: str | None = None) -> str:
        return self.add(self.surfaces[name].copy(new_name or f"{name} copy"))

    def rename(self, old: str, new: str) -> str:
        if old == new:
            return old
        surface = self.surfaces[old]
        others = {k: v for k, v in self.surfaces.items() if k != old}
        surface.name = Project(others).unique_name(new)
        # Rebuilt rather than popped and re-added, so the layer keeps its place in the list.
        self.surfaces = {(surface.name if k == old else k): v for k, v in self.surfaces.items()}
        return surface.name

    def remove(self, name: str) -> None:
        self.surfaces.pop(name)
