"""Every way a surface can be made, behind one registry, so any layer can be replayed.

An operation is a pure function ``(context, inputs, params) -> Output``. :func:`apply` runs one
and records it as a :class:`~posgridder.core.model.Derivation`; :func:`replay` runs every
recorded derivation again, from the source files, and checks the results are identical.

Domain rules (plan §5.1). Surface ± surface is allowed only for:

    depth − depth          → thickness
    depth ± thickness      → depth          (thickness + depth → depth)
    thickness ± thickness  → thickness
    other ± other          → other

Scalar operations, clip and smooth keep the domain; probability surfaces take no arithmetic.
Everything else is refused with the reason. Inputs must share their nodes exactly; otherwise
the refusal points to an explicit resampling step, which makes a new surface of its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from posgridder.core.model import Derivation, Project, ProjectError, Surface, new_uid


class OperationError(ProjectError):
    """An operation refused its inputs or parameters; the message says why."""


@dataclass
class Output:
    values: np.ma.MaskedArray
    domain: str
    geometry: tuple[float, float, float, float]          # xori, yori, xinc, yinc
    crs: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Context:
    """What an operation may read besides its input surfaces: the project's source bytes."""
    project: Project


OpFn = Callable[[Context, list, dict], Output]
OPERATIONS: dict[str, OpFn] = {}
#: Operations that take one surface and may replace it as a new version of the same layer.
REPLACEABLE: set[str] = set()


def operation(name: str, *, replaceable: bool = False):
    def register(fn: OpFn) -> OpFn:
        OPERATIONS[name] = fn
        if replaceable:
            REPLACEABLE.add(name)
        return fn
    return register


# --------------------------------------------------------------------------- helpers
def _geometry(s: Surface) -> tuple[float, float, float, float]:
    return (s.xori, s.yori, s.xinc, s.yinc)


def _common_crs(surfaces: list[Surface], warnings: list[str]) -> str | None:
    stated = {s.crs for s in surfaces if s.crs}
    if len(stated) > 1:
        raise OperationError(f"the inputs state different coordinate systems ({', '.join(sorted(stated))}); "
                             "no reprojection is done in v1")
    if any(not s.crs for s in surfaces) and stated:
        warnings.append("one input states no coordinate system; the other's is assumed")
    return stated.pop() if stated else None


def _require_aligned(a: Surface, b: Surface) -> None:
    if not a.same_geometry(b):
        raise OperationError(
            f"'{a.name}' ({a.ncol} × {a.nrow} at {a.xinc:g} m) and '{b.name}' "
            f"({b.ncol} × {b.nrow} at {b.xinc:g} m) do not share their nodes. Resample one onto "
            "the other first (Prepare → Resample); that step is recorded as a surface of its own.")


_SUM_DOMAINS = {
    ("add", "depth", "thickness"): "depth",
    ("add", "thickness", "depth"): "depth",
    ("add", "thickness", "thickness"): "thickness",
    ("add", "other", "other"): "other",
    ("subtract", "depth", "depth"): "thickness",
    ("subtract", "depth", "thickness"): "depth",
    ("subtract", "thickness", "thickness"): "thickness",
    ("subtract", "other", "other"): "other",
}


def result_domain(op: str, a: str, b: str) -> str:
    """The domain of ``a op b``, or :class:`OperationError` with the reason it is refused."""
    try:
        return _SUM_DOMAINS[(op, a, b)]
    except KeyError:
        sign = "+" if op == "add" else "−"
        raise OperationError(f"{a} {sign} {b} is not a defined combination. Allowed: depth − depth "
                             "→ thickness, depth ± thickness → depth, thickness ± thickness → "
                             "thickness, other ± other → other") from None


def _refuse_probability(s: Surface, what: str) -> None:
    if s.domain == "probability":
        raise OperationError(f"'{s.name}' is a probability surface; {what} is not defined for it")


# --------------------------------------------------------------------------- import and copy
@operation("import")
def _import(ctx: Context, inputs: list, params: dict) -> Output:
    from posgridder.io.surfaces import read_grid

    (source_uid,) = inputs
    grid = read_grid(ctx.project.source_bytes[source_uid], params["format"],
                     filename=ctx.project.sources[source_uid].filename)
    values = -grid.values if params.get("flip_sign") else grid.values
    domain = params["domain"]
    warnings = []
    v = values.compressed()
    if domain in ("depth", "time", "thickness", "velocity") and v.size and np.mean(v < 0) > 0.5:
        warnings.append(f"most values are negative ({v.min():.6g} to {v.max():.6g}); {domain} is "
                        "stored positive down, so the sign probably needs flipping on import")
    return Output(values, domain, grid.geometry, params.get("crs") or grid.crs, warnings)


@operation("copy")
def _copy(ctx, inputs: list[Surface], params) -> Output:
    (s,) = inputs
    return Output(s.values, s.domain, _geometry(s), s.crs)


# --------------------------------------------------------------------------- arithmetic
def _binary(op: str, inputs: list[Surface]) -> Output:
    a, b = inputs
    domain = result_domain(op, a.domain, b.domain)
    _require_aligned(a, b)
    warnings: list[str] = []
    crs = _common_crs([a, b], warnings)
    values = a.values + b.values if op == "add" else a.values - b.values
    if domain == "thickness":
        neg = int(np.ma.sum(values < 0))
        if neg:
            warnings.append(f"{neg:,} nodes have negative thickness (base above top)")
    return Output(values, domain, _geometry(a), crs, warnings)


@operation("add")
def _add(ctx, inputs, params) -> Output:
    return _binary("add", inputs)


@operation("subtract")
def _subtract(ctx, inputs, params) -> Output:
    return _binary("subtract", inputs)


@operation("scale", replaceable=True)
def _scale(ctx, inputs, params) -> Output:
    (s,) = inputs
    _refuse_probability(s, "scaling")
    return Output(s.values * float(params["factor"]), s.domain, _geometry(s), s.crs)


@operation("offset", replaceable=True)
def _offset(ctx, inputs, params) -> Output:
    (s,) = inputs
    _refuse_probability(s, "an offset")
    return Output(s.values + float(params["constant"]), s.domain, _geometry(s), s.crs)


@operation("clip", replaceable=True)
def _clip(ctx, inputs, params) -> Output:
    (s,) = inputs
    lo, hi = params.get("min"), params.get("max")
    if lo is None and hi is None:
        raise OperationError("clip needs a minimum, a maximum or both")
    if lo is not None and hi is not None and lo > hi:
        raise OperationError(f"clip minimum {lo} is above the maximum {hi}")
    return Output(np.ma.clip(s.values, lo, hi), s.domain, _geometry(s), s.crs)


@operation("smooth", replaceable=True)
def _smooth(ctx, inputs, params) -> Output:
    """``passes`` of a 3 × 3 mean over valid nodes. Null nodes stay null and contribute nothing."""
    from scipy.ndimage import uniform_filter

    (s,) = inputs
    passes = int(params["passes"])
    if not 1 <= passes <= 50:
        raise OperationError("smoothing takes 1 to 50 passes")
    mask = np.ma.getmaskarray(s.values)
    z = np.where(mask, 0.0, np.ma.getdata(s.values))
    w = (~mask).astype(float)
    for _ in range(passes):
        num = uniform_filter(z * w, size=3, mode="nearest")
        den = uniform_filter(w, size=3, mode="nearest")
        z = np.where(mask, 0.0, num / np.where(den > 0, den, 1.0))
    return Output(np.ma.MaskedArray(z, mask=mask), s.domain, _geometry(s), s.crs)


# --------------------------------------------------------------------------- resampling
@operation("resample")
def _resample(ctx, inputs: list[Surface], params) -> Output:
    """Values of ``inputs[0]`` at the nodes of ``inputs[1]`` (whose values are not used).

    ``nearest`` takes the nearest node; ``bilinear`` needs all four surrounding nodes valid.
    Target nodes outside the source extent are null.
    """
    src, target = inputs
    method = params["method"]
    if method not in ("nearest", "bilinear"):
        raise OperationError(f"unknown resampling method {method!r}")
    warnings: list[str] = []
    crs = _common_crs([src, target], warnings)
    tx, ty = np.meshgrid(target.x, target.y)
    fi = (ty - src.yori) / src.yinc                       # fractional row
    fj = (tx - src.xori) / src.xinc                       # fractional column
    eps = 1e-9
    inside = (fi >= -eps) & (fi <= src.nrow - 1 + eps) & (fj >= -eps) & (fj <= src.ncol - 1 + eps)
    data = np.ma.getdata(src.values)
    smask = np.ma.getmaskarray(src.values)
    out = np.full(tx.shape, np.nan)
    omask = ~inside
    fi_c = np.clip(fi, 0, src.nrow - 1)
    fj_c = np.clip(fj, 0, src.ncol - 1)
    if method == "nearest":
        i = np.rint(fi_c).astype(int)
        j = np.rint(fj_c).astype(int)
        out = data[i, j]
        omask |= smask[i, j]
    else:
        i0 = np.minimum(np.floor(fi_c).astype(int), src.nrow - 2)
        j0 = np.minimum(np.floor(fj_c).astype(int), src.ncol - 2)
        di, dj = fi_c - i0, fj_c - j0
        corners = [(i0, j0, (1 - di) * (1 - dj)), (i0 + 1, j0, di * (1 - dj)),
                   (i0, j0 + 1, (1 - di) * dj), (i0 + 1, j0 + 1, di * dj)]
        out = sum(w * np.where(smask[i, j], 0.0, data[i, j]) for i, j, w in corners)
        for i, j, _ in corners:
            omask |= smask[i, j]
    lost = int(np.count_nonzero(omask & inside)) if method == "bilinear" else 0
    if lost:
        warnings.append(f"{lost:,} target nodes are null because a surrounding source node is null")
    return Output(np.ma.MaskedArray(out, mask=omask), src.domain, _geometry(target), crs, warnings)


# --------------------------------------------------------------------------- depth conversion
@operation("depth_convert")
def _depth_convert(ctx, inputs: list[Surface], params) -> Output:
    """Time (TWT in ms, positive down, datum MSL) to depth (m, positive down). Plan §5.2.

    With one-way time ``t = TWT / 2000`` s:

    - ``constant``: ``z = V · t``
    - ``velocity_grid``: ``z = V(x, y) · t``, V an average-velocity surface on the same nodes
    - ``v0k``: ``z = (V0 / k)(exp(k t) − 1)``, the solution of ``dz/dt = V0 + k z``; ``k → 0``
      gives ``V0 · t``
    """
    method = params["method"]
    time = inputs[0]
    if time.domain != "time":
        raise OperationError(f"'{time.name}' is a {time.domain} surface; depth conversion needs a "
                             "time surface (TWT in ms)")
    warnings: list[str] = []
    if np.ma.min(time.values) < 0:
        raise OperationError(f"'{time.name}' has negative times; flip its sign on import so time "
                             "is positive down")
    t = time.values / 2000.0
    if method == "constant":
        v = float(params["velocity"])
        if v <= 0:
            raise OperationError("the velocity must be positive")
        z = v * t
        crs = time.crs
    elif method == "velocity_grid":
        vel = inputs[1]
        if vel.domain != "velocity":
            raise OperationError(f"'{vel.name}' is a {vel.domain} surface, not a velocity surface")
        _require_aligned(time, vel)
        crs = _common_crs([time, vel], warnings)
        bad = int(np.ma.sum(vel.values <= 0))
        if bad:
            raise OperationError(f"'{vel.name}' has {bad:,} nodes with zero or negative velocity")
        lost = int(np.count_nonzero(np.ma.getmaskarray(vel.values) & ~np.ma.getmaskarray(time.values)))
        if lost:
            warnings.append(f"{lost:,} nodes are null because the velocity surface is null there")
        z = vel.values * t
    elif method == "v0k":
        v0, k = float(params["v0"]), float(params["k"])
        if v0 <= 0:
            raise OperationError("V0 must be positive")
        if k < 0:
            raise OperationError("k must not be negative")
        # expm1 keeps full precision for small k·t, where exp(k t) − 1 would cancel.
        z = v0 * t if k == 0 else (v0 / k) * np.expm1(k * t)
        crs = time.crs
    else:
        raise OperationError(f"unknown depth-conversion method {method!r}")
    return Output(z, "depth", _geometry(time), crs, warnings)


# --------------------------------------------------------------------------- closures, outlines, volumes
@dataclass
class Fields:
    """The result of an operation that makes something other than a surface."""
    cls: type
    fields: dict


@operation("closure")
def _closure(ctx, inputs: list, params) -> Fields:
    """A confirmed closure: crest, chosen spill and boundary acceptance are the parameters."""
    from posgridder.core.closure import Closure, interpret

    (surface,) = inputs
    try:
        fields = interpret(surface, crest=tuple(params["crest"]),
                           connectivity=int(params.get("connectivity", 8)),
                           min_height=float(params.get("min_height", 5.0)),
                           choice=params["choice"])
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    return Fields(Closure, dict(surface_uid=surface.uid, **fields))


@operation("outline_points")
def _outline_points(ctx, inputs, params) -> Fields:
    from posgridder.core.outline import Outline

    try:
        coords = np.asarray(params["coords"], dtype=float)
        Outline(uid="check", name="check", derivation=Derivation.make("check", []), coords=coords)
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    return Fields(Outline, dict(coords=coords, crs=params.get("crs")))


@operation("outline_from_closure")
def _outline_from_closure(ctx, inputs, params) -> Fields:
    """The closure's footprint at the spill as an outline: the largest polygon of s ≤ spill."""
    import contourpy
    import shapely

    from posgridder.core.outline import Outline

    (closure,) = inputs
    surface = ctx.project.objects[closure.surface_uid]
    fill = np.ma.masked_invalid(closure.fill)
    gen = contourpy.contour_generator(surface.x, surface.y, fill,
                                      fill_type=contourpy.FillType.OuterOffset)
    points, offsets = gen.filled(float(fill.min()) - 1.0, closure.spill_depth + 1e-6)
    polys = [shapely.Polygon(p[o[0]:o[1]]) for p, o in zip(points, offsets) if o[1] - o[0] >= 3]
    if not polys:
        raise OperationError("the footprint is too small to outline")
    best = max(polys, key=lambda q: q.area)
    coords = np.asarray(best.exterior.coords)[:-1]
    return Fields(Outline, dict(coords=coords, crs=surface.crs))


@operation("volumes")
def _volumes(ctx, inputs: list, params) -> Fields:
    """Area–depth and GRV. ``params['roles']`` names each input: closure, top, base,
    thickness or outline."""
    from posgridder.core.volumes import VolumeResult, compute

    roles = dict(zip(params["roles"], inputs))
    closure, top = roles["closure"], roles["top"]
    if closure.surface_uid != top.uid:
        raise OperationError("the closure was interpreted on another surface than the top given")
    try:
        fields = compute(closure, top, geometry=params["geometry"], base=roles.get("base"),
                         thickness_surface=roles.get("thickness"),
                         thickness=params.get("thickness"), outline=roles.get("outline"),
                         step=float(params.get("step", 1.0)))
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    return Fields(VolumeResult, fields)


# --------------------------------------------------------------------------- running
def _run(project: Project, op: str, input_uids: list[str], params: dict):
    if op not in OPERATIONS:
        raise OperationError(f"unknown operation {op!r}")
    ctx = Context(project)
    inputs = (list(input_uids) if op == "import"
              else [project.objects[uid] for uid in input_uids])
    return OPERATIONS[op](ctx, inputs, dict(params))


def _build(out, *, uid: str, name: str, derivation: Derivation):
    if isinstance(out, Fields):
        return out.cls(uid=uid, name=name, derivation=derivation, **out.fields)
    xori, yori, xinc, yinc = out.geometry
    return Surface(uid=uid, name=name, xori=xori, yori=yori, xinc=xinc, yinc=yinc,
                   values=out.values, domain=out.domain, crs=out.crs, derivation=derivation,
                   warnings=tuple(out.warnings))


def apply(project: Project, op: str, input_uids: list[str], params: dict | None = None, *,
          name: str, replace: bool = False):
    """Run ``op`` and add its result to the project.

    With ``replace`` (single-input operations only) the result becomes a new version of the
    input layer: it takes the layer's place, and the input stays in the history.
    """
    params = dict(params or {})
    if replace and (op not in REPLACEABLE or len(input_uids) != 1):
        raise OperationError(f"'{op}' cannot replace its input; it makes a new layer")
    out = _run(project, op, input_uids, params)
    supersedes = input_uids[0] if replace else None
    item = _build(out, uid=new_uid(), name=name,
                  derivation=Derivation.make(op, input_uids, params, supersedes=supersedes))
    if isinstance(item, Surface) and item.n_valid == 0:
        raise OperationError(f"the result of {op} has no valid nodes")
    return project.add(item)


def recalculate(project: Project, uid: str):
    """Recompute a stale object from the newest versions of its inputs, as a new version."""
    obj = project.objects[uid]
    d = obj.derivation
    if d.operation == "import":
        raise OperationError("an import has no inputs to update")
    inputs = [project.current_input(i, uid) if i in project.objects else i for i in d.inputs]
    for i in inputs:
        if i in project.objects and project.is_stale(i):
            raise OperationError(f"input '{project.objects[i].name}' is itself stale; "
                                 "recalculate it first")
    out = _run(project, d.operation, inputs, d.params)
    item = _build(out, uid=new_uid(), name=obj.name,
                  derivation=Derivation.make(d.operation, inputs, d.params, supersedes=uid))
    return project.add(item)


@dataclass
class ReplayRow:
    uid: str
    name: str
    operation: str
    identical: bool


def replay(project: Project) -> list[ReplayRow]:
    """Recompute every object from the source files and compare its content hash.

    Objects are visited in creation order, which is dependency order, and each recomputation
    reads its inputs from the stored objects — so a mismatch is pinned to the step that made it.
    """
    rows = []
    for uid, obj in project.objects.items():
        d = obj.derivation
        fresh = _build(_run(project, d.operation, list(d.inputs), d.params),
                       uid=uid, name=obj.name, derivation=d)
        rows.append(ReplayRow(uid, obj.name, d.operation, fresh.content_hash == obj.content_hash))
    return rows
