"""Spatial POS and area/GRV across the contact percentiles (plan §5.8, §5.9).

POS at a node is a function of its *fill depth* ``s`` (the depth the fill from the crest must
reach before it reaches the node), so a sub-culmination is charged only once the contact passes
its saddle. With a contact distribution:

    event (a), HC with column ≥ h_min:   POS = P(G) · F(h_min) · E_min(s)
    event (b), any HC column:            POS = P(G) · E_all(s)

A conditioned table (the current Builder export) gives ``E_min`` directly; event (b) then equals
(a) wherever ``s`` is deeper than apex + h_min, and is not determinable above that. An
unconditioned table gives ``E_all``; event (a) is then P(G) · E_all(max(s, apex + h_min)) —
contacts shallower than apex + h_min are the columns short of the minimum.

With a typed curve the value is read at ``s`` and forced to 0 at the spill; a curve declared
conditional on G is multiplied by P(G).

Every node falls in exactly one category; nothing outside the trap is reported as POS 0.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

import numpy as np
import pandas as pd

from posgridder.core.hcwc import BASES as BASES_LABEL, ERROR_BOUND
from posgridder.core.model import Derivation, hash_parts, read_only

ERROR_BOUND_LABEL = f"±{ERROR_BOUND:.3f} (one percentile step plus tail truncation)"

CATEGORIES = {
    0: "Null data",
    1: "In the trap, POS > 0",
    2: "In the trap, deeper than every contact",
    3: "In the trap, not determinable from this table",
    4: "Outside the trap",
    5: "Outside the outline (not evaluated)",
}
EVENTS = {"a": "HC with a column of at least h_min", "b": "Any HC column"}
ANCHORINGS = {"as_is": "Contact depths as exported", "reanchor": "Re-anchored to the map crest"}
ANCHOR_WARNING_M = 5.0


@dataclass(frozen=True)
class PosMap:
    kind: ClassVar[str] = "posmap"
    uid: str
    name: str
    derivation: Derivation
    xori: float
    yori: float
    xinc: float
    yinc: float
    pos: np.ndarray                 # NaN outside categories 1 and 2
    category: np.ndarray            # int8, CATEGORIES
    summary: dict
    crs: str | None = None
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "pos", read_only(np.asarray(self.pos, dtype=float)))
        object.__setattr__(self, "category", read_only(np.asarray(self.category, dtype=np.int8)))

    @property
    def x(self) -> np.ndarray:
        return self.xori + self.xinc * np.arange(self.pos.shape[1])

    @property
    def y(self) -> np.ndarray:
        return self.yori + self.yinc * np.arange(self.pos.shape[0])

    @property
    def values(self) -> np.ma.MaskedArray:
        """POS as a masked grid (for ZMAP+ export): null wherever POS is not defined."""
        return np.ma.masked_invalid(self.pos)

    @property
    def content_hash(self) -> str:
        return hash_parts([self.xori, self.yori, self.xinc, self.yinc],
                          np.nan_to_num(self.pos, nan=-1.0), self.category, self.summary,
                          list(self.assumptions))

    def renamed(self, name: str) -> "PosMap":
        return replace(self, name=name)

    def to_record(self):
        meta = {"geometry": [self.xori, self.yori, self.xinc, self.yinc], "crs": self.crs,
                "summary": self.summary, "assumptions": list(self.assumptions)}
        return meta, {"pos": self.pos, "category": self.category}

    @classmethod
    def from_record(cls, common, meta, arrays) -> "PosMap":
        g = meta["geometry"]
        return cls(xori=g[0], yori=g[1], xinc=g[2], yinc=g[3], pos=arrays["pos"],
                   category=arrays["category"], summary=meta["summary"], crs=meta["crs"],
                   assumptions=tuple(meta["assumptions"]), **common)


@dataclass(frozen=True)
class PercentileVolumes:
    kind: ClassVar[str] = "pctvol"
    uid: str
    name: str
    derivation: Derivation
    table: pd.DataFrame
    summary: dict
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        table = self.table.copy()
        for col in table.columns:
            table[col] = read_only(table[col].to_numpy(dtype=float))
        object.__setattr__(self, "table", table)

    @property
    def content_hash(self) -> str:
        return hash_parts(list(self.table.columns), self.table.to_numpy(dtype=float),
                          self.summary, list(self.assumptions))

    def renamed(self, name: str) -> "PercentileVolumes":
        return replace(self, name=name)

    def to_record(self):
        return ({"columns": list(self.table.columns), "summary": self.summary,
                 "assumptions": list(self.assumptions)}, {"table": self.table.to_numpy(float)})

    @classmethod
    def from_record(cls, common, meta, arrays) -> "PercentileVolumes":
        return cls(table=pd.DataFrame(arrays["table"], columns=meta["columns"]),
                   summary=meta["summary"], assumptions=tuple(meta["assumptions"]), **common)


# --------------------------------------------------------------------------- anchoring
def anchoring_shift(dist, crest_depth: float, anchoring: str) -> tuple[float, list, list]:
    """Depth shift for the contacts, plus assumption and warning lines about it."""
    assumptions, warnings = [], []
    if anchoring not in ANCHORINGS:
        raise ValueError(f"unknown anchoring {anchoring!r}")
    if dist.apex is None:
        if anchoring == "reanchor":
            raise ValueError("re-anchoring needs the Builder apex (typed, or from the .hcwc.json)")
        warnings.append("The Builder apex is not known, so the map crest cannot be checked "
                        "against it.")
        return 0.0, ["Contact depths used as exported."], warnings
    offset = crest_depth - dist.apex
    if abs(offset) > ANCHOR_WARNING_M:
        warnings.append(f"The map crest ({crest_depth:.1f} m) differs from the Builder apex "
                        f"({dist.apex:.1f} m) by {offset:+.1f} m.")
    if anchoring == "reanchor":
        assumptions.append(f"Contacts re-anchored to the map crest: shifted {offset:+.1f} m "
                           f"(map crest {crest_depth:.1f} m − Builder apex {dist.apex:.1f} m).")
        return offset, assumptions, warnings
    assumptions.append(f"Contact depths used as exported; the map crest is {offset:+.1f} m from "
                       f"the Builder apex.")
    return 0.0, assumptions, warnings


def _band_top(dist, crest_depth: float, shift: float) -> float:
    """apex + h_min in map depths: contacts shallower than this are columns below the minimum."""
    apex = dist.apex + shift if dist.apex is not None else crest_depth
    return apex + dist.h_min


# --------------------------------------------------------------------------- POS map
def pos_map(closure, top, *, dist=None, curve=None, event: str = "a", anchoring: str = "as_is",
            outline=None, p_g_curve: float | None = None) -> dict:
    """The fields of a :class:`PosMap` for a confirmed closure (plan §5.8)."""
    if (dist is None) == (curve is None):
        raise ValueError("a POS map needs exactly one of a contact distribution or a typed curve")
    z = np.ma.getdata(top.values)
    valid = ~np.ma.getmaskarray(top.values)
    footprint = np.asarray(closure.footprint) & valid
    s = np.asarray(closure.fill)
    category = np.full(z.shape, 4, dtype=np.int8)
    category[~valid] = 0
    inside = footprint.copy()
    if outline is not None:
        within = outline.contains_nodes(top.x, top.y)
        category[footprint & ~within] = 5
        inside &= within
    pos = np.full(z.shape, np.nan)
    assumptions = [f"POS is read at the fill depth from the crest at {closure.crest_depth:.1f} m; "
                   "a sub-culmination counts only once the contact passes its saddle.",
                   f"Outside the trap (spill {closure.spill_depth:.1f} m, {closure.spill_type}) "
                   "no POS is mapped."]
    warnings: list[str] = []
    summary: dict = {"crest_depth_m": closure.crest_depth, "spill_depth_m": closure.spill_depth}

    if curve is not None:
        if curve.meaning == "conditional":
            if p_g_curve is None or not 0 <= p_g_curve <= 1:
                raise ValueError("a curve conditional on G needs P(G) between 0 and 1")
            factor = float(p_g_curve)
            assumptions.append(f"Typed curve conditional on G, multiplied by P(G) = {factor:g}.")
        else:
            factor = 1.0
            assumptions.append("Typed curve read as total POS (P(G) included).")
        values = factor * curve.at(s[inside], closure.spill_depth)
        if np.any(np.diff(curve.values) > 0):
            warnings.append("The typed curve rises with depth somewhere; POS usually falls with "
                            "depth.")
        pos[inside] = values
        summary.update(source="typed curve", meaning=curve.meaning, multiplier=factor)
    else:
        if event not in EVENTS:
            raise ValueError(f"unknown event {event!r}")
        if dist.p_g is None:
            raise ValueError("P(G) is needed: typed, or from a .hcwc.json on the geological basis")
        shift, a_lines, w_lines = anchoring_shift(dist, closure.crest_depth, anchoring)
        assumptions += a_lines
        warnings += w_lines
        e = dist.exceedance(shift)
        sv = s[inside]
        if dist.conditioning == "h_min":
            if event == "a":
                if dist.f_hmin is None:
                    raise ValueError("event (a) from a table conditioned on h_min needs F(h_min)")
                multiplier = dist.p_g * dist.f_hmin
                values = multiplier * e(sv)
            else:
                if dist.h_min is None or dist.f_hmin is None:
                    raise ValueError("event (b) from a conditioned table needs h_min and F(h_min)")
                multiplier = dist.p_g * dist.f_hmin
                band = _band_top(dist, closure.crest_depth, shift)
                values = multiplier * e(sv)
                undetermined = sv <= band
                values[undetermined] = np.nan
                assumptions.append(f"Event (b) equals event (a) deeper than apex + h_min "
                                   f"({band:.1f} m); shallower it is not determinable from a "
                                   "table conditioned on h_min.")
        else:                                              # unconditioned
            if event == "a":
                if dist.h_min is None:
                    raise ValueError("event (a) from an unconditioned table needs h_min")
                band = _band_top(dist, closure.crest_depth, shift)
                multiplier = dist.p_g
                values = multiplier * e(np.maximum(sv, band))
                f_derived = float(e(band))
                summary["f_hmin_derived"] = f_derived
                assumptions.append(f"Event (a) from the unconditioned table: contacts shallower "
                                   f"than apex + h_min ({band:.1f} m) are columns short of the "
                                   f"minimum; F(h_min) = {f_derived:.4f}.")
            else:
                multiplier = dist.p_g
                values = multiplier * e(sv)
        pos[inside] = values
        crest_pos = float(multiplier * e(closure.crest_depth)) if event == "a" or \
            dist.conditioning == "unconditioned" else None
        summary.update(source="contact distribution", event=event, basis=dist.basis,
                       conditioning=dist.conditioning, multiplier=float(multiplier),
                       p_g=dist.p_g, f_hmin=dist.f_hmin, shift_m=shift, anchoring=anchoring)
        if event == "a":
            prospect = dist.p_g * (dist.f_hmin if dist.conditioning == "h_min"
                                   else summary.get("f_hmin_derived", 1.0))
            summary["prospect_pos"] = float(prospect)
            summary["pos_at_crest"] = float(crest_pos) if crest_pos is not None else None
            if crest_pos is not None and crest_pos < prospect - 1e-9:
                warnings.append(f"POS at the crest ({crest_pos:.4f}) is below the Prospect POS "
                                f"({prospect:.4f}): some contacts lie above the map crest.")
        assumptions.append(f"Basis: {BASES_LABEL.get(dist.basis, dist.basis)}; "
                           f"{dist.conditioning.replace('_', ' ')} table; tails "
                           f"{dist.tails}. Exceedance read to within {ERROR_BOUND_LABEL}.")

    cat_inside = np.where(np.isnan(pos[inside]), 3, np.where(pos[inside] > 0, 1, 2))
    category[inside] = cat_inside
    pos[category != 1] = np.where(category[category != 1] == 2, 0.0, np.nan)
    cell = top.xinc * top.yinc / 1e6
    summary["area_km2_by_category"] = {CATEGORIES[k]: float((category == k).sum() * cell)
                                       for k in CATEGORIES}
    finite = pos[np.isfinite(pos)]
    summary["max_pos"] = float(finite.max()) if finite.size else 0.0
    return dict(xori=top.xori, yori=top.yori, xinc=top.xinc, yinc=top.yinc, pos=pos,
                category=category, summary=summary, crs=top.crs,
                assumptions=tuple(assumptions), warnings=tuple(warnings))


# --------------------------------------------------------------------------- percentile volumes
def percentile_volumes(volumes, dist, *, anchoring: str = "as_is") -> dict:
    """Area and GRV at each contact percentile (plan §5.9): exact, because both rise with depth."""
    crest = volumes.summary["crest_depth_m"]
    spill = volumes.summary["spill_depth_m"]
    shift, assumptions, warnings = anchoring_shift(dist, crest, anchoring)
    contacts = np.asarray(dist.depths) + shift
    used = np.minimum(contacts, spill)
    table = pd.DataFrame({
        "percentile": np.asarray(dist.percentiles, dtype=float),
        "contact_m": contacts,
        "contact_used_m": used,
        "area_km2": [volumes.area_at(c) if c > crest else 0.0 for c in used],
        "grv_1e6m3": [volumes.grv_at(c) if c > crest else 0.0 for c in used],
        "grv_single_fill_1e6m3": [volumes.grv_at(c, "grv_single_fill_1e6m3") if c > crest else 0.0
                                  for c in used],
    })
    e = dist.exceedance(shift)
    p_below_spill = float(e(spill))
    p_above_crest = float(1.0 - e(crest))
    if p_below_spill > 0:
        warnings.append(f"{p_below_spill:.1%} of the contacts lie deeper than the map spill "
                        f"({spill:.1f} m); they are taken at the spill (fill to spill).")
    if p_above_crest > 0:
        warnings.append(f"{p_above_crest:.1%} of the contacts lie above the map crest; they "
                        "give no rock volume.")
    assumptions = list(assumptions) + [
        f"Conditioning: {dist.conditioning.replace('_', ' ')} — the volumes are conditional on "
        "geological success" + (" and on a column of at least h_min." if dist.conditioning == "h_min"
                                else "."),
        "GRV at each percentile is GRV at that percentile's contact: exact, because GRV rises "
        "with contact depth.",
    ]

    def at(p: float, col: str) -> float:
        return float(np.interp(p, table["percentile"][::-1], table[col][::-1]))

    summary = {
        "p_contact_below_spill": p_below_spill, "p_contact_above_crest": p_above_crest,
        "crest_depth_m": crest, "spill_depth_m": spill, "shift_m": shift,
        "conditioning": dist.conditioning, "basis": dist.basis,
        **{f"grv_P{p}_1e6m3": at(p, "grv_1e6m3") for p in (90, 50, 10)},
        **{f"area_P{p}_km2": at(p, "area_km2") for p in (90, 50, 10)},
    }
    return dict(table=table, summary=summary, assumptions=tuple(assumptions),
                warnings=tuple(warnings))
