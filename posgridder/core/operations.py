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


# --------------------------------------------------------------------------- HCWC and POS
def _source(ctx: Context, uid: str) -> tuple[bytes, str]:
    return ctx.project.source_bytes[uid], ctx.project.sources[uid].filename


@operation("hcwc")
def _hcwc(ctx, inputs: list, params) -> Fields:
    """A contact distribution: from a Builder CSV or a typed table, with the multiplier inputs.

    ``params['roles']`` names the source inputs: ``csv`` and/or ``json``. Typed values in
    ``params`` take precedence over the .hcwc.json; where each value came from is recorded.
    """
    from posgridder.core.hcwc import ContactDistribution, TableError, parse_csv, parse_hcwc_json

    roles = dict(zip(params.get("roles", []), inputs))
    sources: list[str] = []
    warnings: list[str] = []
    try:
        if "csv" in roles:
            data, filename = _source(ctx, roles["csv"])
            p, d, header = parse_csv(data)
            origin = f"file {filename} (depth column '{header}')"
        else:
            p = np.asarray(params["table"]["percentiles"], dtype=float)
            d = np.asarray(params["table"]["depths"], dtype=float)
            origin = params.get("origin", "typed or pasted table")
        if params.get("flip_sign"):
            d = -d
            origin += ", sign flipped"
        values = {k: params.get(k) for k in ("p_g", "f_hmin", "h_min", "apex")}
        typed = list(values)
        values["builder_spill"] = None
        # h_min = 0 m with F(h_min) = 1 is the default pair: every successful column counts,
        # so every success passes the minimum. Recorded as a default, not as a typed value.
        defaulted = set(params.get("defaulted", []))
        for k in typed:
            if values[k] is not None:
                # Typed values keep the 0.1 wording, so older distributions replay identically.
                if k in defaulted:
                    unit = " m" if k == "h_min" else ""
                    sources.append(f"{k} = {values[k]:g}{unit} default (every successful "
                                   "column counts)")
                else:
                    sources.append(f"{k} = {values[k]:g} typed")
        if "json" in roles:
            data, filename = _source(ctx, roles["json"])
            info = parse_hcwc_json(data)
            if values["p_g"] is None and "p_g" in info:
                if params["basis"] == "given_dhi":
                    raise OperationError(
                        f"{filename} gives the prior P(G); a given-the-DHI table needs P(G | DHI), "
                        "which is typed")
                values["p_g"] = info["p_g"]
                parts = " × ".join(f"{e} {v:.3g}" for e, v in info["elements"].items())
                sources.append(f"p_g = {info['p_g']:.4f} from {filename} inputs ({parts})")
            if values["h_min"] is None and "h_min" in info:
                values["h_min"] = info["h_min"]
                sources.append(f"h_min = {info['h_min']:g} m from {filename} inputs")
            elif ("h_min" in defaulted and info.get("h_min", 0) > 0
                  and values["h_min"] != info["h_min"]):
                warnings.append(
                    f"{filename} sets h_min = {info['h_min']:g} m, but the table is taken with "
                    f"the default h_min = {values['h_min']:g} m and F(h_min) = "
                    f"{values['f_hmin']:g}. If the export was made with {info['h_min']:g} m, "
                    "F(h_min) is below 1 and POS is overstated: type F(h_min) and h_min from the "
                    "Builder results.")
            if values["apex"] is None and "apex" in info:
                values["apex"] = info["apex"]
                sources.append(f"apex = {info['apex']:.1f} m from {filename} inputs "
                               "(midpoint of its P1 and P99)")
            if "spill" in info:
                values["builder_spill"] = info["spill"]
                sources.append(f"Builder spill = {info['spill']:g} m from {filename} inputs")
            if info.get("dhi") and params["basis"] == "geological":
                warnings.append(f"{filename} has a DHI switched on; this table is declared "
                                "geological.")
        if params["conditioning"] == "h_min" and values["f_hmin"] is None:
            warnings.append("F(h_min) is not given; event (a) cannot be mapped from this "
                            "conditioned table until it is.")
        if values["h_min"] is None:
            warnings.append("h_min is not given; the band shallower than apex + h_min cannot be "
                            "placed.")
        if params["tails"] == "unknown":
            warnings.append("The tail treatment is not known; P100 and P0 may be single samples.")
        fields = dict(percentiles=p, depths=d, basis=params["basis"],
                      conditioning=params["conditioning"], tails=params["tails"],
                      origin=origin, sources=tuple(sources), warnings=tuple(warnings), **values)
        ContactDistribution(uid="check", name="check", derivation=Derivation.make("check", []),
                            **fields)
    except OperationError:
        raise
    except (TableError, ValueError, KeyError) as exc:
        raise OperationError(str(exc).strip("'")) from None
    return Fields(ContactDistribution, fields)


@operation("pos_curve")
def _pos_curve(ctx, inputs, params) -> Fields:
    from posgridder.core.hcwc import PosCurve

    fields = dict(depths=np.asarray(params["depths"], dtype=float),
                  values=np.asarray(params["values"], dtype=float), meaning=params["meaning"])
    try:
        PosCurve(uid="check", name="check", derivation=Derivation.make("check", []), **fields)
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    return Fields(PosCurve, fields)


@operation("pos_map")
def _pos_map(ctx, inputs, params) -> Fields:
    from posgridder.core.pos import PosMap, pos_map

    roles = dict(zip(params["roles"], inputs))
    closure, top = roles["closure"], roles["top"]
    if closure.surface_uid != top.uid:
        raise OperationError("the closure was interpreted on another surface than the top given")
    try:
        fields = pos_map(closure, top, dist=roles.get("hcwc"), curve=roles.get("curve"),
                         event=params.get("event", "a"), anchoring=params.get("anchoring", "as_is"),
                         outline=roles.get("outline"), p_g_curve=params.get("p_g"))
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    return Fields(PosMap, fields)


@operation("percentile_volumes")
def _percentile_volumes(ctx, inputs, params) -> Fields:
    from posgridder.core.pos import PercentileVolumes, percentile_volumes

    volumes, dist = inputs
    try:
        fields = percentile_volumes(volumes, dist, anchoring=params.get("anchoring", "as_is"))
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    return Fields(PercentileVolumes, fields)


@operation("area_depth_import")
def _area_depth_import(ctx, inputs, params) -> Fields:
    from posgridder.core.volumes import VolumeResult, from_area_depth, parse_area_depth

    (source,) = inputs
    data, filename = _source(ctx, source)
    try:
        return Fields(VolumeResult, from_area_depth(parse_area_depth(data), filename))
    except ValueError as exc:
        raise OperationError(str(exc)) from None


# --------------------------------------------------------------------------- contours
@operation("contour")
def _contour(ctx, inputs, params) -> Fields:
    """Contour lines of a surface at a regular interval (contourpy, linear between nodes)."""
    from posgridder.core.contours import ContourSet, contour_levels, contour_surface

    (surface,) = inputs
    st = surface.stats()
    try:
        levels = contour_levels(st["min"], st["max"], float(params["interval"]),
                                params.get("start"), params.get("stop"))
        fields = contour_surface(surface, levels)
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    unit = f" {surface.unit}" if surface.unit else ""
    origin = (f"derived from '{surface.name}' every {params['interval']:g}{unit}"
              f" ({len(levels)} levels, {levels[0]:g} to {levels[-1]:g}{unit})")
    return Fields(ContourSet, dict(domain=surface.domain, origin=origin, source_uid=surface.uid,
                                   crs=surface.crs, **fields))


@operation("contour_import")
def _contour_import(ctx, inputs, params) -> Fields:
    """Contour lines from a vector or ASCII file; the level from an attribute or from Z."""
    from posgridder.core.contours import ContourSet, pack
    from posgridder.io.vectors import read_contours

    (source,) = inputs
    data, filename = _source(ctx, source)
    try:
        lines, levels, warnings = read_contours(data, filename, params.get("level_field"))
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    if params.get("flip_sign"):
        levels = [-v for v in levels]
    if params["domain"] in ("depth", "time") and np.mean(np.asarray(levels) < 0) > 0.5:
        warnings.append("most levels are negative; depth and time are stored positive down, so "
                        "the sign probably needs flipping on import")
    field = params.get("level_field") or "Z"
    origin = f"imported from {filename} (level from {field})" + \
        (", sign flipped" if params.get("flip_sign") else "")
    return Fields(ContourSet, dict(domain=params["domain"], origin=origin, source_uid=None,
                                   crs=params.get("crs"), warnings=tuple(warnings),
                                   **pack(lines, levels)))


@operation("contour_edit", replaceable=True)
def _contour_edit(ctx, inputs, params) -> Fields:
    """Lines marked deleted or restored. The lines stay in the set; nothing is removed."""
    from posgridder.core.contours import ContourSet

    (cs,) = inputs
    ids = [int(k) for k in params.get("delete", [])] + [int(k) for k in params.get("restore", [])]
    if any(not 0 <= k < cs.n_lines for k in ids):
        raise OperationError("a line number is outside the set")
    flags = cs.with_deleted(params.get("delete", []), params.get("restore", []))
    if not (~flags).any():
        raise OperationError("deleting every line leaves nothing to grid")
    return Fields(ContourSet, dict(coords=cs.coords, offsets=cs.offsets, levels=cs.levels,
                                   deleted=flags, domain=cs.domain, origin=cs.origin,
                                   source_uid=cs.source_uid, crs=cs.crs, warnings=cs.warnings))


@operation("contours_to_surface")
def _contours_to_surface(ctx, inputs, params) -> Output:
    """A surface from the active lines of a contour set, by a declared method (plan §5.4).

    The grid is the nodes of a template surface (``roles`` names it ``template``) or
    ``params['geometry']``. Crest points, (x, y, z), are added to the data if given.
    """
    from posgridder.core.contours import TPS_NEIGHBOURS, data_points, grid_from_points

    roles = dict(zip(params.get("roles", ["contours"]), inputs))
    cs = roles["contours"]
    if "template" in roles:
        t = roles["template"]
        if cs.crs and t.crs and cs.crs != t.crs:
            raise OperationError(f"the contours state {cs.crs} and the template {t.crs}; no "
                                 "reprojection is done in v1")
        if abs(t.xinc - t.yinc) > 1e-9 * t.xinc:
            raise OperationError("the template grid has unequal X and Y increments")
        geometry = {"xori": t.xori, "yori": t.yori, "inc": t.xinc, "ncol": t.ncol,
                    "nrow": t.nrow}
    else:
        geometry = params["geometry"]
    try:
        points = data_points(cs, float(params.get("spacing") or geometry["inc"]),
                             params.get("crest_points", []))
        z, report = grid_from_points(points, geometry, params["method"],
                                     int(params.get("neighbors", TPS_NEIGHBOURS)))
    except ValueError as exc:
        raise OperationError(str(exc)) from None
    warnings = []
    if report["overshoot_shallow_m"] > 0:
        warnings.append(f"The surface rises {report['overshoot_shallow_m']:.2f} m above the "
                        "shallowest contour (or crest point): extrapolated relief.")
    if report["overshoot_deep_m"] > 0:
        warnings.append(f"The surface falls {report['overshoot_deep_m']:.2f} m below the deepest "
                        "contour.")
    if not params.get("crest_points"):
        warnings.append("No crest point was given: inside the innermost contour the "
                        + ("TIN is flat at that level." if params["method"] == "tin" else
                           "spline extrapolates the crest."))
    if "template" in roles and params.get("template_nulls", True):
        # The data hull bridges gaps and concave edges; the template says where data ends.
        held = ~np.ma.getmaskarray(z) & np.ma.getmaskarray(roles["template"].values)
        if held.any():
            warnings.append(f"{int(held.sum()):,} nodes inside the contours' hull are null in the "
                            "template and are kept null.")
        z = np.ma.MaskedArray(np.ma.getdata(z), mask=np.ma.getmaskarray(z)
                              | np.ma.getmaskarray(roles["template"].values))
    return Output(z, cs.domain, (geometry["xori"], geometry["yori"], geometry["inc"],
                                 geometry["inc"]), cs.crs, warnings)


@operation("outline_from_contour")
def _outline_from_contour(ctx, inputs, params) -> Fields:
    from posgridder.core.outline import Outline

    (cs,) = inputs
    k = int(params["line"])
    if not 0 <= k < cs.n_lines or not cs.closed(k):
        raise OperationError("only a closed contour line makes an outline")
    return Fields(Outline, dict(coords=np.asarray(cs.line(k))[:-1], crs=cs.crs))


# --------------------------------------------------------------------------- running
def _run(project: Project, op: str, input_uids: list[str], params: dict):
    if op not in OPERATIONS:
        raise OperationError(f"unknown operation {op!r}")
    ctx = Context(project)
    # Objects are passed as themselves; source files by their uid (their bytes are in ctx).
    inputs = [project.objects[u] if u in project.objects else u for u in input_uids]
    return OPERATIONS[op](ctx, inputs, dict(params))


def _build(out, *, uid: str, name: str, derivation: Derivation):
    if isinstance(out, Fields):
        return out.cls(uid=uid, name=name, derivation=derivation, **out.fields)
    xori, yori, xinc, yinc = out.geometry
    return Surface(uid=uid, name=name, xori=xori, yori=yori, xinc=xinc, yinc=yinc,
                   values=out.values, domain=out.domain, crs=out.crs, derivation=derivation,
                   warnings=tuple(out.warnings))


def apply(project: Project, op: str, input_uids: list[str], params: dict | None = None, *,
          name: str, replace: bool = False, supersedes: str | None = None):
    """Run ``op`` and add its result to the project.

    With ``replace`` (single-input operations only) the result becomes a new version of the
    input layer: it takes the layer's place, and the input stays in the history. ``supersedes``
    names another object the result is a new version of (an edited table, say).
    """
    params = dict(params or {})
    if replace and (op not in REPLACEABLE or len(input_uids) != 1):
        raise OperationError(f"'{op}' cannot replace its input; it makes a new layer")
    out = _run(project, op, input_uids, params)
    supersedes = input_uids[0] if replace else supersedes
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
    made_by: str = ""                   # app version that made the stored object


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
        rows.append(ReplayRow(uid, obj.name, d.operation, fresh.content_hash == obj.content_hash,
                              d.app_version))
    return rows
