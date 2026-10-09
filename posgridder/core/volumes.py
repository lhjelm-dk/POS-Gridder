"""Area–depth and gross rock volume for a confirmed closure (plan §5.6).

Three geometries, chosen explicitly:

- ``top_base``      — the base is a mapped depth surface;
- ``top_constant``  — base = top + a constant vertical thickness (the HCWC Builder and
                      SCOPE-HC "top surface and a thickness" rule);
- ``top_grid``      — base = top + a thickness surface (vertical, an isochore).

Areas are measured on polygons: the top surface (or base) is contoured at each depth, restricted
to the closure footprint and, if given, clipped by an outline. That is sub-cell and converges at
second order (feasibility F3); counting nodes does not.

Three GRV curves against the contact depth ``c``, in 10⁶ m³ (= km²·m):

- ``grv_trapezoid`` — ∫ (A_top − A_base) dz from the crest: what HCWC Builder and SCOPE-HC
  compute from an area–depth table;
- ``grv_direct``    — Σ over footprint nodes of [min(base, c) − top]⁺ · cell area: the same
  quantity integrated column by column, the check on the trapezoid;
- ``grv_single_fill`` — the direct sum over nodes the fill from the crest has reached at ``c``
  (``s ≤ c``). It differs from the other two only where a sub-culmination joins the crest below
  its own top, for contacts shallower than that saddle; the area–depth table cannot express a
  single fill point, so the difference is reported rather than hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

import contourpy
import numpy as np
import pandas as pd
import shapely

from posgridder.core.model import Derivation, hash_parts, read_only

GEOMETRIES = {
    "top_base": "Top and base surfaces",
    "top_constant": "Top surface and a constant thickness",
    "top_grid": "Top surface and a thickness surface",
}
AGREEMENT_TOLERANCE = 0.01          # F3: trapezoid vs direct, relative, at the spill
MIN_RADIUS_CELLS = 10               # F3: below this the area bias exceeds ~0.5 %


def polygon_area(x, y, z: np.ma.MaskedArray, level: float,
                 clip: shapely.Polygon | None = None) -> float:
    """Area (m²) where ``z ≤ level``, from linear contouring; masked nodes are excluded."""
    zc = np.ma.masked_invalid(z)
    if zc.count() == 0 or level <= float(zc.min()):
        return 0.0
    gen = contourpy.contour_generator(x, y, zc, fill_type=contourpy.FillType.OuterOffset)
    points, offsets = gen.filled(float(zc.min()) - 1.0, float(level))
    polys = []
    for pts, offs in zip(points, offsets):
        rings = [pts[offs[k]:offs[k + 1]] for k in range(len(offs) - 1)]
        if len(rings[0]) >= 3:
            polys.append(shapely.Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3]))
    if not polys:
        return 0.0
    if clip is None:
        return float(sum(p.area for p in polys))
    return float(shapely.union_all(polys).intersection(clip).area)


@dataclass(frozen=True)
class VolumeResult:
    kind: ClassVar[str] = "volumes"
    uid: str
    name: str
    derivation: Derivation
    geometry: str
    table: pd.DataFrame
    summary: dict
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        table = self.table.copy()
        for col in table.columns:
            arr = read_only(table[col].to_numpy(dtype=float))
            table[col] = arr
        object.__setattr__(self, "table", table)

    @property
    def content_hash(self) -> str:
        return hash_parts(self.geometry, list(self.table.columns),
                          self.table.to_numpy(dtype=float), self.summary, list(self.assumptions))

    def renamed(self, name: str) -> "VolumeResult":
        return replace(self, name=name)

    def to_record(self):
        meta = {"geometry": self.geometry, "columns": list(self.table.columns),
                "summary": self.summary, "assumptions": list(self.assumptions)}
        return meta, {"table": self.table.to_numpy(dtype=float)}

    @classmethod
    def from_record(cls, common: dict, meta: dict, arrays: dict) -> "VolumeResult":
        return cls(geometry=meta["geometry"], summary=meta["summary"],
                   table=pd.DataFrame(arrays["table"], columns=meta["columns"]),
                   assumptions=tuple(meta["assumptions"]), **common)

    def grv_at(self, contact: float, column: str = "grv_direct_1e6m3") -> float:
        """GRV at a contact depth: interpolated in the table, capped at the spill."""
        t = self.table
        c = min(max(contact, t["depth_m"].iloc[0]), t["depth_m"].iloc[-1])
        return float(np.interp(c, t["depth_m"], t[column]))

    def area_at(self, contact: float) -> float:
        t = self.table
        c = min(max(contact, t["depth_m"].iloc[0]), t["depth_m"].iloc[-1])
        return float(np.interp(c, t["depth_m"], t["top_area_km2"]))


def compute(closure, top, *, geometry: str, base=None, thickness_surface=None,
            thickness: float | None = None, outline=None, step: float = 1.0) -> dict:
    """Area–depth table and GRV curves from the crest to the confirmed spill."""
    if geometry not in GEOMETRIES:
        raise ValueError(f"unknown geometry {geometry!r}")
    warnings: list[str] = []
    assumptions = ["Thickness is vertical (isochore); no dip correction."]
    z_top = np.ma.getdata(top.values)
    valid_top = ~np.ma.getmaskarray(top.values)
    footprint = np.asarray(closure.footprint) & valid_top
    fill = np.asarray(closure.fill)

    if geometry == "top_base":
        if base is None or base.domain != "depth":
            raise ValueError("the top-and-base geometry needs a base depth surface")
        _aligned(top, base)
        z_base = np.ma.getdata(base.values)
        base_null = np.ma.getmaskarray(base.values)
        assumptions.append(f"Base surface: '{base.name}'.")
    elif geometry == "top_grid":
        if thickness_surface is None or thickness_surface.domain != "thickness":
            raise ValueError("the top-and-thickness-surface geometry needs a thickness surface")
        _aligned(top, thickness_surface)
        z_base = z_top + np.ma.getdata(thickness_surface.values)
        base_null = np.ma.getmaskarray(thickness_surface.values)
        assumptions.append(f"Base = top + thickness surface '{thickness_surface.name}'.")
    else:
        if thickness is None or not thickness > 0:
            raise ValueError("a constant thickness must be positive")
        z_base = z_top + float(thickness)
        base_null = np.zeros_like(valid_top)
        assumptions.append(f"Base = top + {thickness:g} m.")

    missing = footprint & base_null
    if missing.any():
        warnings.append(f"{int(missing.sum()):,} footprint nodes have no base; they are left out "
                        "of the volume.")
    negative = footprint & ~base_null & (z_base < z_top)
    if negative.any():
        warnings.append(f"{int(negative.sum()):,} footprint nodes have the base above the top "
                        "(negative thickness); they hold no rock in the direct sum, and the base "
                        "area is capped at the top area.")
    use = footprint & ~base_null

    clip = None
    if outline is not None:
        inside = outline.contains_nodes(top.x, top.y)
        cut = int((use & ~inside).sum())
        if cut:
            warnings.append(f"The outline '{outline.name}' leaves out {cut:,} footprint nodes.")
        use = use & inside
        clip = outline.polygon
        assumptions.append(f"Area and GRV clipped by the outline '{outline.name}'.")
    if not use.any():
        raise ValueError("no footprint nodes remain to measure")

    # Work on the bounding box of the footprint, one node wider, for speed.
    rows, cols = np.nonzero(use)
    r0, r1 = max(rows.min() - 1, 0), min(rows.max() + 2, top.nrow)
    c0, c1 = max(cols.min() - 1, 0), min(cols.max() + 2, top.ncol)
    box = (slice(r0, r1), slice(c0, c1))
    x, y = top.x[c0:c1], top.y[r0:r1]
    sub_use = use[box]
    # Areas: nodes outside the footprint are pushed to just deeper than the spill, so other
    # structures never count while the contour still interpolates across the closure's rim.
    # (Masking them instead would drop every boundary cell: half a cell lost all round.)
    spill_lift = closure.spill_depth + 1e-6
    sub_fp = footprint[box]
    t_sub = np.ma.MaskedArray(np.where(sub_fp, z_top[box], np.maximum(z_top[box], spill_lift)),
                              mask=~valid_top[box])
    b_sub = np.ma.MaskedArray(np.where(sub_fp, z_base[box], np.maximum(z_base[box], spill_lift)),
                              mask=~valid_top[box] | base_null[box])
    top_c, base_c = z_top[box][sub_use], z_base[box][sub_use]
    s_c = fill[box][sub_use]
    cell = top.xinc * top.yinc

    crest, spill = closure.crest_depth, closure.spill_depth
    n = int(np.ceil((spill - crest) / step))
    if n > 2000:
        n = 2000
        warnings.append(f"The depth step was widened to {(spill - crest) / n:.2f} m to keep the "
                        "table to 2,000 rows.")
    depths = np.linspace(crest, spill, n + 1)
    a_top = np.array([polygon_area(x, y, t_sub, d, clip) for d in depths]) / 1e6
    a_base = np.array([polygon_area(x, y, b_sub, d, clip) for d in depths]) / 1e6
    if np.any(a_base > a_top + 1e-12):
        a_base = np.minimum(a_base, a_top)
    gross = a_top - a_base
    trap = np.concatenate([[0.0], np.cumsum(np.diff(depths) * 0.5 * (gross[1:] + gross[:-1]))])
    direct = np.array([np.clip(np.minimum(base_c, d) - top_c, 0, None).sum() for d in depths])
    single = np.array([np.clip(np.minimum(base_c, d) - top_c, 0, None)[s_c <= d].sum()
                       for d in depths])
    direct *= cell / 1e6
    single *= cell / 1e6

    table = pd.DataFrame({
        "depth_m": depths, "top_area_km2": a_top, "base_area_km2": a_base,
        "grv_trapezoid_1e6m3": trap, "grv_direct_1e6m3": direct,
        "grv_single_fill_1e6m3": single,
    })
    rel = abs(trap[-1] - direct[-1]) / direct[-1] if direct[-1] > 0 else 0.0
    radius_cells = np.sqrt(a_top[-1] * 1e6 / np.pi) / min(top.xinc, top.yinc)
    if rel > AGREEMENT_TOLERANCE:
        hint = (" The footprint borders null nodes, where contoured areas stop at the last "
                "complete cell while the direct sum counts whole cells."
                if _borders_null(footprint, valid_top) else "")
        warnings.append(f"Area–depth and direct GRV differ by {rel:.1%} at the spill "
                        f"(tolerance {AGREEMENT_TOLERANCE:.0%}).{hint}")
    if radius_cells < MIN_RADIUS_CELLS:
        warnings.append(f"The closure spans about {radius_cells:.1f} cells in radius; areas "
                        "are resolved to within about 1 % only above 10.")
    split = np.max(np.abs(direct - single) / np.where(direct > 0, direct, 1))
    if split > 1e-3:
        warnings.append(f"Single-fill GRV is up to {split:.1%} below the area–depth GRV, for "
                        "contacts shallower than a sub-culmination's saddle.")
    summary = {
        "crest_depth_m": float(crest), "spill_depth_m": float(spill),
        "area_at_spill_km2": float(a_top[-1]), "grv_direct_at_spill_1e6m3": float(direct[-1]),
        "grv_trapezoid_at_spill_1e6m3": float(trap[-1]),
        "agreement_relative": float(rel), "radius_cells": float(radius_cells),
        "nodes": int(use.sum()), "step_m": float(depths[1] - depths[0]) if n else 0.0,
    }
    return dict(geometry=geometry, table=table, summary=summary,
                assumptions=tuple(assumptions), warnings=tuple(warnings))


def _borders_null(footprint: np.ndarray, valid: np.ndarray) -> bool:
    from scipy.ndimage import binary_dilation

    return bool((binary_dilation(footprint, structure=np.ones((3, 3))) & ~valid).any())


def _aligned(a, b) -> None:
    if not a.same_geometry(b):
        raise ValueError(f"'{b.name}' does not share the nodes of '{a.name}'; resample it first")


# --------------------------------------------------------------------------- exchange files
def builder_csv(result: VolumeResult, provenance: list[str]) -> str:
    """HCWC Builder area–depth table: depth_m, top_area_km2, base_area_km2, grv_1e6m3_cached.

    Builder rules (``hcwc/core/charge.py`` AreaDepthTable): depths strictly increasing from the
    apex, which has zero area; base ≤ top. ``grv_1e6m3_cached`` is the trapezoid of the table,
    which is what the Builder computes from it.
    """
    t = result.table
    lines = [f"# {line}" for line in provenance]
    lines.append("# Depth in m TVDSS (positive down); areas in km2; GRV in 1e6 m3 (km2*m).")
    lines.append("depth_m,top_area_km2,base_area_km2,grv_1e6m3_cached")
    for d, a, b, g in zip(t["depth_m"], t["top_area_km2"], t["base_area_km2"],
                          t["grv_trapezoid_1e6m3"]):
        lines.append(f"{d:.3f},{a:.6f},{min(b, a):.6f},{g:.6f}")
    return "\n".join(lines) + "\n"


def scope_csv(result: VolumeResult) -> str:
    """SCOPE-HC area–depth table: Depth, Top area (km2), Base area (km2)."""
    t = result.table
    out = pd.DataFrame({"Depth": t["depth_m"].round(3), "Top area (km2)": t["top_area_km2"].round(6),
                        "Base area (km2)": np.minimum(t["base_area_km2"], t["top_area_km2"]).round(6)})
    return out.to_csv(index=False, lineterminator="\n")
