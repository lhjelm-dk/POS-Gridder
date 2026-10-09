"""Outline polygons: boundaries that limit area and GRV (decision 22: never spill barriers)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

import numpy as np
import shapely

from posgridder.core.model import Derivation, hash_parts, read_only


@dataclass(frozen=True)
class Outline:
    kind: ClassVar[str] = "outline"
    uid: str
    name: str
    derivation: Derivation
    coords: np.ndarray                  # (n, 2) exterior ring, not repeated at the end
    crs: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        coords = np.asarray(self.coords, dtype=float)
        if coords.ndim != 2 or coords.shape[1] != 2:
            raise ValueError("an outline needs x, y vertex pairs")
        if len(coords) > 1 and np.allclose(coords[0], coords[-1]):
            coords = coords[:-1]
        if len(coords) < 3:
            raise ValueError("an outline needs at least three vertices")
        poly = shapely.Polygon(coords)
        if not poly.is_valid:
            raise ValueError(f"the outline is not a valid polygon ({shapely.is_valid_reason(poly)})")
        if poly.area <= 0:
            raise ValueError("the outline encloses no area")
        object.__setattr__(self, "coords", read_only(coords))

    @property
    def polygon(self) -> shapely.Polygon:
        return shapely.Polygon(self.coords)

    @property
    def area_km2(self) -> float:
        return self.polygon.area / 1e6

    def contains_nodes(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Which grid nodes lie inside (or on) the outline."""
        xx, yy = np.meshgrid(x, y)
        poly = self.polygon
        return shapely.contains_xy(poly, xx, yy) | shapely.intersects_xy(poly.boundary, xx, yy)

    @property
    def content_hash(self) -> str:
        return hash_parts(self.coords, self.crs)

    def renamed(self, name: str) -> "Outline":
        return replace(self, name=name)

    def to_record(self):
        return {"crs": self.crs}, {"coords": self.coords}

    @classmethod
    def from_record(cls, common: dict, meta: dict, arrays: dict) -> "Outline":
        return cls(coords=arrays["coords"], crs=meta["crs"], **common)


def parse_xy(text: str) -> np.ndarray:
    """Vertices from text: one 'x y' or 'x,y' pair per line; '#' starts a comment."""
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split("#")[0].replace(",", " ").replace(";", " ").strip()
        if not line:
            continue
        parts = line.split()
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except (IndexError, ValueError):
            raise ValueError(f"line {n} is not an x y pair: {line!r}") from None
    if len(rows) < 3:
        raise ValueError("an outline needs at least three vertices")
    return np.array(rows)
