"""Closure and spill interpretation on a depth surface (plan §5.5).

Three steps, each exact at node resolution:

1. :func:`crest_candidates` — one pass over the nodes in order of depth, merging them into
   connected regions (union–find). Each local culmination's region grows until it meets a
   shallower culmination's region (a saddle) or a boundary (the model edge, the data limit, or
   an interior null hole). That level is the candidate's conservative spill, and its depth below
   the crest the closure height. Small ones are filtered by a minimum height.
2. :func:`fill_depth` — priority-flood from one crest. ``s(x)`` is the depth an accumulation
   filling from the crest must reach before it reaches node ``x``: the smallest achievable
   maximum depth along any path from the crest. ``s ≥ z``, with ``s = z`` on a simple dome.
3. :func:`spill_events` — read off ``s``: the level at which the fill first reaches the model
   edge, the data limit, an interior null, and the saddle towards each other significant
   culmination. These are *candidates*. The interpreter confirms one (or a manual depth), and
   that confirmation is what :class:`Closure` records.

Depth is positive down, so a crest is a local *minimum* of depth. Connectivity is 8 by default:
with 4, a saddle through a cell corner is missed and a closure can be reported where the fill
would in fact leak diagonally.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field, replace
from typing import ClassVar

import numpy as np
from scipy import ndimage

from posgridder.core.model import Derivation, Surface, hash_parts, read_only

EDGE, DATA_LIMIT, INTERIOR_NULL, SADDLE, MANUAL = (
    "model edge", "data limit", "interior null", "saddle", "manual")
BOUNDARY_TYPES = (EDGE, DATA_LIMIT, INTERIOR_NULL)

_N4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
_N8 = _N4 + ((-1, -1), (-1, 1), (1, -1), (1, 1))


def _neighbours(connectivity: int):
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    return _N8 if connectivity == 8 else _N4


def boundary_types(mask: np.ndarray, connectivity: int = 8) -> np.ndarray:
    """Per valid node: '' or the boundary it touches (edge first, then data limit, then hole).

    Null regions that reach the grid border are the *data limit*; enclosed null regions are
    *interior nulls*. The two are told apart because a hole inside a structure is missing data,
    not the end of the structure.
    """
    nrow, ncol = mask.shape
    out = np.full(mask.shape, "", dtype=object)
    structure = np.ones((3, 3)) if connectivity == 8 else None
    labels, n = ndimage.label(mask, structure=structure)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    exterior = np.isin(labels, [lab for lab in border if lab != 0])
    interior = mask & ~exterior
    near_ext = ndimage.binary_dilation(exterior, structure=np.ones((3, 3)) if connectivity == 8
                                       else ndimage.generate_binary_structure(2, 1))
    near_int = ndimage.binary_dilation(interior, structure=np.ones((3, 3)) if connectivity == 8
                                       else ndimage.generate_binary_structure(2, 1))
    valid = ~mask
    out[valid & near_int] = INTERIOR_NULL
    out[valid & near_ext] = DATA_LIMIT
    edge = np.zeros_like(mask)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    out[valid & edge] = EDGE
    return out


# --------------------------------------------------------------------------- candidates
@dataclass(frozen=True)
class Candidate:
    """A culmination with its conservative spill (every boundary treated as a leak)."""
    node: tuple[int, int]
    crest_depth: float
    spill_depth: float
    spill_type: str
    nodes_at_spill: int

    @property
    def height(self) -> float:
        return self.spill_depth - self.crest_depth


def crest_candidates(surface: Surface, *, connectivity: int = 8, min_height: float = 5.0,
                     min_nodes: int = 4) -> list[Candidate]:
    """Culminations whose conservative closure is at least ``min_height`` deep and
    ``min_nodes`` nodes large, tallest first."""
    z = np.ma.getdata(surface.values)
    mask = np.ma.getmaskarray(surface.values)
    nrow, ncol = z.shape
    btype = boundary_types(mask, connectivity)
    nbrs = _neighbours(connectivity)

    order = np.argsort(np.where(mask, np.inf, z), axis=None, kind="stable")
    n_valid = int((~mask).sum())
    parent = np.full(nrow * ncol, -1, dtype=np.int64)      # -1: not yet active
    size = np.zeros(nrow * ncol, dtype=np.int64)
    low = np.zeros(nrow * ncol, dtype=np.int64)              # each root's shallowest node
    dead = np.zeros(nrow * ncol, dtype=bool)                 # root has spilled already
    exit_type = np.full(nrow * ncol, "", dtype=object)       # where a spilled region leaks to
    found: list[Candidate] = []

    def find(a: int) -> int:
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    def die(root: int, level: float, kind: str) -> None:
        if not dead[root]:
            dead[root] = True
            exit_type[root] = kind
            node = int(low[root])
            found.append(Candidate(divmod(node, ncol), float(z.flat[node]), float(level), kind,
                                   int(size[root])))

    for flat in order[:n_valid]:
        flat = int(flat)
        i, j = divmod(flat, ncol)
        level = z[i, j]
        parent[flat], size[flat], low[flat] = flat, 1, flat
        for di, dj in nbrs:
            a, b = i + di, j + dj
            if not (0 <= a < nrow and 0 <= b < ncol) or parent[a * ncol + b] < 0:
                continue
            r1, r2 = find(flat), find(a * ncol + b)
            if r1 == r2:
                continue
            # r1 holds the shallower culmination (the older region), r2 the deeper one.
            if (z.flat[low[r1]], low[r1]) > (z.flat[low[r2]], low[r2]):
                r1, r2 = r2, r1
            d1, d2 = bool(dead[r1]), bool(dead[r2])
            if not d1 and not d2:
                die(r2, level, SADDLE)          # the deeper culmination spills into the older
            elif d1 and not d2:
                # Spills into a region that already leaks: labelled by where that region leaks.
                die(r2, level, exit_type[r1])
            elif d2 and not d1:
                die(r1, level, exit_type[r2])
            leak = exit_type[r1] if d1 else exit_type[r2] if d2 else ""
            parent[r2] = r1
            exit_type[r1] = leak
            size[r1] += size[r2]
            dead[r1] = d1 or d2                 # still open only if both were open
        if btype[i, j]:
            die(find(flat), level, btype[i, j])

    out = [c for c in found if c.height >= min_height and c.nodes_at_spill >= min_nodes]
    return sorted(out, key=lambda c: (-c.height, c.crest_depth))


# --------------------------------------------------------------------------- fill depth
def fill_depth(surface: Surface, crest: tuple[int, int], connectivity: int = 8,
               *, return_peak: bool = False):
    """Priority-flood from ``crest``: the depth the fill reaches before it reaches each node.

    With ``return_peak`` also the flat index of the deepest node on the path the fill takes to
    each node: for a node beyond a saddle, that is the saddle (the spill point) itself.
    """
    z = np.ma.getdata(surface.values)
    mask = np.ma.getmaskarray(surface.values)
    i0, j0 = crest
    if mask[i0, j0]:
        raise ValueError("the crest node is null")
    nrow, ncol = z.shape
    nbrs = _neighbours(connectivity)
    s = np.full(z.shape, np.inf)
    s[i0, j0] = z[i0, j0]
    peak = np.full(z.shape, -1, dtype=np.int64)
    peak[i0, j0] = i0 * ncol + j0
    done = np.zeros(z.shape, dtype=bool)
    heap = [(float(z[i0, j0]), i0, j0)]
    while heap:
        level, i, j = heapq.heappop(heap)
        if done[i, j]:
            continue
        done[i, j] = True
        for di, dj in nbrs:
            a, b = i + di, j + dj
            if 0 <= a < nrow and 0 <= b < ncol and not mask[a, b] and not done[a, b]:
                new = max(level, z[a, b])
                if new < s[a, b]:
                    s[a, b] = new
                    peak[a, b] = a * ncol + b if z[a, b] >= level else peak[i, j]
                    heapq.heappush(heap, (new, a, b))
    out = np.ma.MaskedArray(s, mask=mask | ~np.isfinite(s))
    return (out, peak) if return_peak else out


@dataclass(frozen=True)
class SpillEvent:
    """A candidate spill: the fill level, what it reaches, and ``node`` — the spill point
    (the deepest node on the fill's path there; for a saddle, the saddle node)."""
    level: float
    type: str
    node: tuple[int, int]
    detail: str = ""


def spill_events(surface: Surface, fill: np.ma.MaskedArray, crest: tuple[int, int], *,
                 connectivity: int = 8, min_height: float = 5.0) -> list[SpillEvent]:
    """Where and at what depth the fill from ``crest`` first reaches each kind of boundary,
    and the saddle towards every other culmination at least ``min_height`` high. Shallowest first.
    """
    z = np.ma.getdata(surface.values)
    mask = np.ma.getmaskarray(surface.values)
    s = np.ma.getdata(fill)
    reached = ~np.ma.getmaskarray(fill)
    btype = boundary_types(mask, connectivity)
    _, peak = fill_depth(surface, crest, connectivity, return_peak=True)
    ncol = z.shape[1]

    def spill_point(node) -> tuple[int, int]:
        flat = int(peak[node])
        return divmod(flat, ncol) if flat >= 0 else node

    events: list[SpillEvent] = []
    for kind in BOUNDARY_TYPES:
        sel = reached & (btype == kind)
        if sel.any():
            flat = int(np.argmin(np.where(sel, s, np.inf)))
            node = divmod(flat, ncol)
            events.append(SpillEvent(float(s[node]), kind, spill_point(node)))
    # Other culminations: local minima of depth, grouped across plateaus.
    zz = np.where(mask, np.inf, z)
    footprint = np.ones((3, 3)) if connectivity == 8 else ndimage.generate_binary_structure(2, 1)
    is_min = (zz == ndimage.minimum_filter(zz, footprint=footprint, mode="constant",
                                           cval=np.inf)) & ~mask
    labels, n = ndimage.label(is_min, structure=np.ones((3, 3)))
    crest_label = labels[crest]
    saddles: dict[float, list[tuple[float, tuple[int, int]]]] = {}
    for lab in range(1, n + 1):
        if lab == crest_label:
            continue
        nodes = np.argwhere(labels == lab)
        a, b = (int(v) for v in nodes[0])
        if not reached[a, b]:
            continue
        if s[a, b] - z[a, b] >= min_height:
            saddles.setdefault(float(s[a, b]), []).append((float(z[a, b]), (a, b)))
    # Culminations reached at the same level lie behind the same saddle: one event each level,
    # named after the shallowest of them.
    for level, found in saddles.items():
        depth, node = min(found)
        more = f" and {len(found) - 1} more behind the same saddle" if len(found) > 1 else ""
        events.append(SpillEvent(level, SADDLE, spill_point(node),
                                 f"towards a culmination at {depth:.1f} m, "
                                 f"{level - depth:.1f} m high above the saddle{more}"))
    return sorted(events, key=lambda e: (e.level, BOUNDARY_TYPES.index(e.type)
                                         if e.type in BOUNDARY_TYPES else 3))


def spill_resolution(surface: Surface, node: tuple[int, int]) -> float:
    """How finely the grid resolves a spill at ``node``: the largest depth step to a neighbour."""
    z = np.ma.getdata(surface.values)
    mask = np.ma.getmaskarray(surface.values)
    i, j = node
    steps = [abs(z[a, b] - z[i, j]) for a in range(i - 1, i + 2) for b in range(j - 1, j + 2)
             if (a, b) != (i, j) and 0 <= a < z.shape[0] and 0 <= b < z.shape[1] and not mask[a, b]]
    return float(max(steps)) if steps else 0.0


def footprint_at(surface: Surface, fill: np.ma.MaskedArray, spill: float) -> np.ndarray:
    """The nodes in the trap when it is filled to ``spill``.

    The footprint stops at the spill point. Nodes the fill reaches only at the spill level
    itself lie beyond it, downhill on the far side (s == spill > z), and are left out; nodes
    standing at the spill depth themselves (the rim, the saddle node) are kept.
    """
    z = np.ma.getdata(surface.values)
    s_val = np.ma.getdata(fill)
    reached = ~np.ma.getmaskarray(fill)
    tol = 1e-9 * max(1.0, abs(spill))
    return reached & ((s_val < spill - tol) | (np.abs(z - spill) <= tol))


def nearest_node(surface: Surface, x: float, y: float) -> tuple[int, int]:
    j = int(round((x - surface.xori) / surface.xinc))
    i = int(round((y - surface.yori) / surface.yinc))
    if not (0 <= i < surface.nrow and 0 <= j < surface.ncol):
        raise ValueError(f"({x:.0f}, {y:.0f}) lies outside the grid")
    return i, j


# --------------------------------------------------------------------------- the confirmed closure
@dataclass(frozen=True)
class Closure:
    """A confirmed closure: crest, spill and footprint on one depth surface.

    ``fill`` is the fill-depth field ``s`` and ``footprint`` the nodes with ``s ≤ spill``. The
    crest, the chosen spill and the boundary treatment are the interpreter's; the derivation
    records them, and ``assumptions`` states them in words.
    """
    kind: ClassVar[str] = "closure"
    uid: str
    name: str
    derivation: Derivation
    surface_uid: str
    crest: tuple[int, int]
    crest_depth: float
    spill_depth: float
    spill_type: str
    connectivity: int
    fill: np.ndarray                    # s, NaN where unreached or null
    footprint: np.ndarray               # bool
    events: tuple[dict, ...] = ()
    sub_culminations: tuple[dict, ...] = ()
    assumptions: tuple[str, ...] = ()
    spill_resolution_m: float = 0.0
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill", read_only(np.asarray(self.fill, dtype=float)))
        object.__setattr__(self, "footprint", read_only(np.asarray(self.footprint, dtype=bool)))
        object.__setattr__(self, "crest", tuple(int(v) for v in self.crest))

    @property
    def height(self) -> float:
        return self.spill_depth - self.crest_depth

    @property
    def n_nodes(self) -> int:
        return int(self.footprint.sum())

    @property
    def content_hash(self) -> str:
        return hash_parts(self.surface_uid, list(self.crest), self.crest_depth, self.spill_depth,
                          self.spill_type, self.connectivity, np.nan_to_num(self.fill, nan=-1.0),
                          self.footprint, list(self.events), list(self.sub_culminations),
                          list(self.assumptions))

    def renamed(self, name: str) -> "Closure":
        return replace(self, name=name)

    def to_record(self):
        meta = {k: getattr(self, k) for k in (
            "surface_uid", "crest_depth", "spill_depth", "spill_type", "connectivity",
            "spill_resolution_m")}
        meta.update(crest=list(self.crest), events=list(self.events),
                    sub_culminations=list(self.sub_culminations),
                    assumptions=list(self.assumptions))
        return meta, {"fill": self.fill, "footprint": self.footprint}

    @classmethod
    def from_record(cls, common: dict, meta: dict, arrays: dict) -> "Closure":
        return cls(fill=arrays["fill"], footprint=arrays["footprint"],
                   crest=tuple(meta["crest"]), events=tuple(meta["events"]),
                   sub_culminations=tuple(meta["sub_culminations"]),
                   assumptions=tuple(meta["assumptions"]),
                   **{k: meta[k] for k in ("surface_uid", "crest_depth", "spill_depth",
                                           "spill_type", "connectivity", "spill_resolution_m")},
                   **common)


def interpret(surface: Surface, *, crest: tuple[int, int], connectivity: int = 8,
              min_height: float = 5.0, choice: dict) -> dict:
    """Everything a :class:`Closure` holds, for a crest and a confirmed spill choice.

    ``choice`` is ``{"event": k}`` (the k-th candidate from :func:`spill_events`, shallowest
    first) or ``{"manual": depth, "reason": text}``. ``{"accept": [...]}`` lists the boundary
    types the interpreter accepts the fill passing (closed beyond, unverified); a chosen spill
    deeper than an unaccepted boundary event is refused.
    """
    if surface.domain != "depth":
        raise ValueError(f"'{surface.name}' is a {surface.domain} surface; closure needs depth "
                         "(convert time to depth first)")
    z = np.ma.getdata(surface.values)
    if np.ma.getmaskarray(surface.values)[crest]:
        raise ValueError("the crest node is null")
    fill = fill_depth(surface, crest, connectivity)
    events = spill_events(surface, fill, crest, connectivity=connectivity, min_height=min_height)
    accepted = set(choice.get("accept", []))
    assumptions = [f"Single fill point at the crest ({z[crest]:.1f} m); a sub-culmination fills "
                   "only through its connection to the crest.",
                   f"{connectivity}-connected grid nodes."]
    if "manual" in choice:
        spill = float(choice["manual"])
        reason = str(choice.get("reason", "")).strip()
        if not reason:
            raise ValueError("a manual spill depth needs a stated reason")
        spill_type, spill_node = MANUAL, None
        assumptions.append(f"Spill depth {spill:.1f} m set manually: {reason}")
    else:
        k = int(choice["event"])
        if not 0 <= k < len(events):
            raise ValueError(f"no candidate spill number {k}")
        spill, spill_type, spill_node = events[k].level, events[k].type, events[k].node
    if spill <= z[crest]:
        raise ValueError(f"the spill depth {spill:.1f} m is not below the crest ({z[crest]:.1f} m)")

    warnings: list[str] = []
    for e in events:
        if e.level < spill and e.type in BOUNDARY_TYPES:
            if e.type not in accepted:
                raise ValueError(f"the fill reaches the {e.type} at {e.level:.1f} m, above the "
                                 f"chosen spill at {spill:.1f} m; accept that boundary as closed "
                                 "(unverified) or choose a shallower spill")
            assumptions.append(f"The fill passes the {e.type} at {e.level:.1f} m: the closure is "
                               f"assumed to continue there (unverified).")
            warnings.append(f"The footprint reaches the {e.type}; its area beyond the data is "
                            "not counted.")
    footprint = footprint_at(surface, fill, spill)
    tol = 1e-9 * max(1.0, abs(spill))
    sub = [{"saddle_node": list(e.node), "saddle": e.level, "detail": e.detail}
           for e in events if e.type == SADDLE and e.level < spill - tol]
    if sub:
        warnings.append(f"{len(sub)} sub-culmination(s) inside the closure join the crest at a "
                        "saddle; contacts shallower than that saddle do not reach them.")
    resolution = spill_resolution(surface, spill_node) if spill_node else 0.0
    height = spill - z[crest]
    if height < min_height:
        warnings.append(f"Closure height {height:.1f} m is below the {min_height:g} m minimum.")
    if resolution > 0:
        warnings.append(f"The grid resolves the spill to about ±{resolution:.1f} m (the depth step "
                        "between neighbouring nodes at the spill).")
    holes = boundary_types(np.ma.getmaskarray(surface.values), connectivity)
    if np.any(footprint & (holes == INTERIOR_NULL)):
        warnings.append("Null nodes lie inside the footprint; their area is not counted.")
    return dict(
        crest=crest, crest_depth=float(z[crest]), spill_depth=float(spill),
        spill_type=spill_type, connectivity=connectivity,
        fill=np.ma.filled(fill, np.nan), footprint=footprint,
        events=tuple({"level": e.level, "type": e.type, "node": list(e.node), "detail": e.detail}
                     for e in events),
        sub_culminations=tuple(sub), assumptions=tuple(assumptions),
        spill_resolution_m=resolution, warnings=tuple(warnings))
