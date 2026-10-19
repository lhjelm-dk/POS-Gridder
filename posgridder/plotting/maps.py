"""Map figures. Plotly, because the map needs equal axes in metres, hover values and, from
Phase 4, click and lasso selection of contours."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from posgridder.core.model import Surface

def surface_figure(surface: Surface, *, colorscale: str = "Viridis", reverse: bool = False,
                   height: int = 650, histogram: bool = False, bins: int = 30,
                   contours: float | bool | None = None) -> go.Figure:
    """The surface as a heatmap in its own coordinates, nulls left blank.

    ``colorscale`` is one of :data:`COLOUR_SCALES`, the same ten as the POS map. With
    ``histogram`` a narrow panel beside the colour bar shows the map area in each value interval.
    Overlays added later with ``fig.add_trace`` land on the map.
    """
    z = surface.values.filled(np.nan)
    unit = f" {surface.unit}" if surface.unit else ""
    scale = _scale(colorscale, reverse)
    stats = surface.stats()
    vmin, vmax = stats["min"], stats["max"]
    if not vmax > vmin:
        vmax = vmin + 1e-6
    fig = _map_frame(histogram)
    fig.add_trace(go.Heatmap(
        z=z, x=surface.x, y=surface.y, zmin=vmin, zmax=vmax, colorscale=scale,
        colorbar=dict(title=dict(text=f"{surface.domain}{(' (' + surface.unit + ')') if surface.unit else ''}"),
                      len=1.0, y=0.5, yanchor="middle", x=1.0, xanchor="left"),
        hovertemplate="X %{x:.0f}<br>Y %{y:.0f}<br>%{z:.2f}" + unit + "<extra></extra>",
    ), **_map_loc(histogram))
    if histogram:
        _value_histogram(fig, surface.values.compressed(), vmin, vmax, scale,
                         surface.xinc * surface.yinc / 1e6, bins, "%{customdata[0]:.1f}–"
                         "%{customdata[1]:.1f}" + unit, ".0f")
    if contours:
        add_structure_contours(fig, surface, None if contours is True else float(contours),
                               colour="#ffffff" if colorscale in ("Viridis", "Cividis", "Plasma",
                                                                  "Magma") and not reverse
                               else "#1e1b16", loc=_map_loc(histogram))
    _map_layout(fig, histogram, height, surface.name)
    return fig


def _map_frame(histogram: bool) -> go.Figure:
    if not histogram:
        return go.Figure()
    from plotly.subplots import make_subplots

    return make_subplots(rows=1, cols=2, column_widths=[0.84, 0.16], horizontal_spacing=0.03)


def _map_loc(histogram: bool) -> dict:
    return dict(row=1, col=1) if histogram else {}


def _value_histogram(fig, values, vmin, vmax, colorscale, cell_km2, bins, range_fmt, tickformat):
    """Map area per value interval, beside the colour bar, on the colour bar's range."""
    import plotly.colors as pc

    edges = np.linspace(vmin, vmax, bins + 1)
    counts, _ = np.histogram(values, bins=edges)
    centres = 0.5 * (edges[1:] + edges[:-1])
    colours = pc.sample_colorscale(colorscale, list((centres - vmin) / (vmax - vmin)))
    fig.add_trace(go.Bar(
        x=counts * cell_km2, y=centres, orientation="h", width=(edges[1] - edges[0]) * 0.92,
        marker=dict(color=colours, line=dict(width=0)), showlegend=False, name="Area",
        customdata=np.column_stack([edges[:-1], edges[1:]]),
        hovertemplate=range_fmt + "<br>%{x:.2f} km²<extra></extra>"), row=1, col=2)
    fig.update_xaxes(title_text="Area (km²)", rangemode="tozero", gridcolor="#ebe8df",
                     row=1, col=2)
    # Same range as the colour bar, so a bar sits beside its own colour.
    fig.update_yaxes(range=[vmin, vmax], tickformat=tickformat, showticklabels=False,
                     gridcolor="#ebe8df", row=1, col=2)


def _map_layout(fig, histogram: bool, height: int, title: str) -> None:
    loc = _map_loc(histogram)
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), title=dict(text=title,
                                                                      font=dict(size=14)),
        legend=dict(x=0.01, y=0.99, xanchor="left", yanchor="top",
                    bgcolor="rgba(30,27,22,0.6)", font=dict(color="#ffffff")),
        plot_bgcolor="#ffffff", bargap=0)
    fig.update_xaxes(title_text="X (m)", tickformat="d", showgrid=False, **loc)
    # Equal scaling, so a 250 m cell is square on screen.
    fig.update_yaxes(title_text="Y (m)", tickformat="d", showgrid=False, scaleanchor="x",
                     scaleratio=1, **loc)


# --------------------------------------------------------------------------- overlays
#: Reference categorical slots (dataviz palette, light mode): blue, orange, aqua.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")


def spill_field(surface: Surface, footprint: np.ndarray, spill: float) -> np.ndarray:
    """The surface with every node outside the footprint pushed just deeper than the spill.

    Contoured at the spill depth it gives the closure's outline as a true depth contour,
    interpolated between nodes, rather than the stair-step edge of the node mask; other
    structures never appear on it. The same rule measures the areas (core/volumes.py).
    """
    z = surface.values.filled(np.nan)
    fp = np.asarray(footprint, dtype=bool)
    lift = spill + 1e-6 * max(1.0, abs(spill))
    return np.where(fp, z, np.maximum(np.nan_to_num(z, nan=lift), lift))


def add_footprint(fig: go.Figure, surface: Surface, footprint: np.ndarray, *, name: str,
                  spill: float | None = None, color: str = "#ffffff", dash: str = "solid",
                  width: float = 2.0, loc: dict | None = None) -> go.Figure:
    """The outline of a closure footprint: the depth contour at ``spill`` within the footprint
    when the spill is given, otherwise the edge of the node mask."""
    if spill is not None:
        z, level = spill_field(surface, footprint, spill), spill
    else:
        z, level = np.asarray(footprint, dtype=float), 0.5
    fig.add_trace(go.Contour(
        z=z, x=surface.x, y=surface.y, name=name, showlegend=True,
        contours=dict(start=level, end=level, size=1, coloring="none"),
        line=dict(color=color, width=width, dash=dash), showscale=False, hoverinfo="skip"),
        **(loc or {}))
    return fig


def add_point(fig: go.Figure, x: float, y: float, *, name: str, text: str,
              symbol: str = "triangle-up", color: str = "#ffffff") -> go.Figure:
    fig.add_trace(go.Scatter(
        x=[x], y=[y], mode="markers", name=name,
        marker=dict(symbol=symbol, size=12, color=color, line=dict(color="#1e1b16", width=1.5)),
        hovertemplate=f"{text}<extra></extra>"))
    return fig


def add_outline(fig: go.Figure, coords: np.ndarray, *, name: str) -> go.Figure:
    ring = np.vstack([coords, coords[:1]])
    fig.add_trace(go.Scatter(x=ring[:, 0], y=ring[:, 1], mode="lines", name=name,
                             line=dict(color="#1e1b16", width=2, dash="dash"),
                             hovertemplate=f"{name}<extra></extra>"))
    return fig


def node_xy(surface: Surface, node) -> tuple[float, float]:
    i, j = node
    return float(surface.x[j]), float(surface.y[i])


# --------------------------------------------------------------------------- POS maps
#: Sequential single-hue ramp (dataviz reference blue, light = low, dark = high).
POS_SCALE = [[0.0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"],
             [1.0, "#0d366b"]]
#: Recessive greys for the regions where no POS is mapped, darkest for "not determinable".
CATEGORY_GREYS = {3: "#8c8a82", 4: "#d9d6cc", 5: "#eeece6"}


#: POS colour scales: five single-hue ramps and five perceptually ordered multi-hue ones.
#: Rainbow scales (Jet, Turbo) are left out: their bright bands read as edges in a smooth
#: probability field. Cividis is the one designed for colour-vision deficiency.
POS_SCALES: dict[str, object] = {
    "Blues": POS_SCALE,
    "Greens": "Greens",
    "Purples": "Purples",
    "Oranges": "Oranges",
    "Greys": "Greys",
    "Viridis": "Viridis",
    "Cividis": "Cividis",
    "Plasma": "Plasma",
    "Magma": "Magma",
    "YlGnBu": "YlGnBu",
}
#: Plotly's single-hue ramps run dark → light; reversed they read light = low, like Blues.
_DARK_FIRST = {"Greens", "Purples", "Oranges", "Greys", "YlGnBu"}
#: The same scales serve every map: surfaces, closure previews, contour backgrounds, POS.
COLOUR_SCALES = POS_SCALES
COLORSCALES: tuple[str, ...] = tuple(POS_SCALES)


def _scale(name: str, reverse: bool):
    """A colorscale as a list of [position, colour]: single-hue ramps light at the low end,
    multi-hue ones (Viridis …) dark at the low end, either flipped by ``reverse``."""
    import plotly.colors as pc

    spec = POS_SCALES[name]
    if isinstance(spec, str):
        flip = (spec in _DARK_FIRST) != reverse
        spec = pc.get_colorscale(spec + ("_r" if flip else ""))
    elif reverse:
        spec = [[1 - p, c] for p, c in reversed(spec)]
    return [[float(p), c] for p, c in spec]


def pos_figure(m, *, height: int = 600, title: str | None = None, scale: str = "Blues",
               reverse: bool = False, histogram: bool = True, bins: int = 20,
               structure=None, closure=None, contour_interval: float | None = None) -> go.Figure:
    """POS in the trap on the chosen scale; the other categories in flat greys beneath it.

    With ``histogram`` a narrow panel beside the colour bar shows the trap area in each POS
    interval, its bars coloured from the same scale, so the colour bar reads as a distribution.
    With ``structure`` (the top surface) its depth contours are drawn over the colours; with
    ``closure`` its spill contour and crest are marked.
    """
    from posgridder.core.pos import CATEGORIES

    colorscale = _scale(scale, reverse)
    fig = _map_frame(histogram)
    loc = _map_loc(histogram)
    for code, grey in CATEGORY_GREYS.items():
        sel = m.category == code
        if not sel.any():
            continue
        fig.add_trace(go.Heatmap(
            z=np.where(sel, 1.0, np.nan), x=m.x, y=m.y, colorscale=[[0, grey], [1, grey]],
            showscale=False, name=CATEGORIES[code], showlegend=True,
            hovertemplate=f"{CATEGORIES[code]}<extra></extra>"), **loc)
    zero = np.where(m.category == 2, 0.0, np.nan)
    if np.isfinite(zero).any():
        fig.add_trace(go.Heatmap(z=zero, x=m.x, y=m.y, colorscale=[[0, "#f5f1e6"], [1, "#f5f1e6"]],
                                 showscale=False, name=CATEGORIES[2], showlegend=True,
                                 hovertemplate=f"{CATEGORIES[2]}: POS 0<extra></extra>"), **loc)
    pos = m.pos[m.category == 1]
    vmax = max(float(pos.max()) if pos.size else 0.0, 1e-6)
    fig.add_trace(go.Heatmap(
        z=np.where(m.category == 1, m.pos, np.nan), x=m.x, y=m.y, zmin=0, zmax=vmax,
        colorscale=colorscale, name="POS",
        colorbar=dict(title=dict(text="POS"), tickformat=".0%", len=1.0, y=0.5, yanchor="middle",
                      x=1.0, xanchor="left"),
        hovertemplate="X %{x:.0f}<br>Y %{y:.0f}<br>POS %{z:.1%}<extra></extra>"), **loc)
    if histogram:
        _value_histogram(fig, pos, 0.0, vmax, colorscale, m.xinc * m.yinc / 1e6, bins,
                         "POS %{customdata[0]:.1%}–%{customdata[1]:.1%}", ".0%")
    if structure is not None:
        add_structure_contours(fig, structure, contour_interval, loc=loc)
    if closure is not None and structure is not None:
        add_footprint(fig, structure, closure.footprint, spill=closure.spill_depth,
                      name=f"Spill {closure.spill_depth:.1f} m", color=SERIES[1], width=2.5,
                      loc=loc)
        cx, cy = node_xy(structure, closure.crest)
        fig.add_trace(go.Scatter(
            x=[cx], y=[cy], mode="markers", name=f"Crest {closure.crest_depth:.1f} m",
            marker=dict(symbol="triangle-up", size=11, color="#ffffff",
                        line=dict(color="#1e1b16", width=1.5)),
            hovertemplate=f"Crest {closure.crest_depth:.1f} m<extra></extra>"), **loc)
    _map_layout(fig, histogram, height, title or m.name)
    return fig


# --------------------------------------------------------------------------- contour sets
def contour_figure(cs, *, background=None, selected=(), height: int = 620,
                   colorscale: str = "Viridis", reverse: bool = False,
                   line_colour: str = "#ffffff", closure=None,
                   major_every: int = 5) -> go.Figure:
    """Active lines solid (every ``major_every``-th level thicker and labelled), deleted lines
    dotted grey, selected lines orange, and the closure's spill contour if given.

    Every vertex carries an invisible marker with its line number in ``customdata``, so a box or
    lasso selection returns line numbers (feasibility F2: line-only traces are not selectable).
    """
    fig = (surface_figure(background, height=height, colorscale=colorscale, reverse=reverse)
           if background is not None else go.Figure())
    selected = set(int(k) for k in selected)

    def trace(ids, name, color, dash, width):
        xs, ys, cd, lv = [], [], [], []
        for k in ids:
            pts = cs.line(k)
            xs += list(pts[:, 0]) + [None]
            ys += list(pts[:, 1]) + [None]
            cd += [k] * len(pts) + [None]
            lv += [cs.levels[k]] * len(pts) + [None]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers", name=name, customdata=cd,
            line=dict(color=color, width=width, dash=dash),
            marker=dict(size=5, color=color, opacity=0.0),
            selected=dict(marker=dict(opacity=0.0)), unselected=dict(marker=dict(opacity=0.0)),
            text=[f"{v:g}" if v is not None else None for v in lv],
            hovertemplate="Level %{text}<br>line %{customdata}<extra></extra>"))

    active = [k for k in cs.active() if k not in selected]
    gone = [k for k in range(cs.n_lines) if cs.deleted[k] and k not in selected]
    sel = sorted(selected)
    levels = np.unique(cs.levels)
    step = float(np.min(np.diff(levels))) if levels.size > 1 else 0.0
    major = step * major_every

    def is_major(k):
        return step > 0 and abs(cs.levels[k] / major - round(cs.levels[k] / major)) < 1e-6

    colour = line_colour if background is not None else SERIES[0]
    minor_ids = [k for k in active if not is_major(k)]
    major_ids = [k for k in active if is_major(k)]
    if minor_ids:
        trace(minor_ids, "Contours", colour, "solid", 0.8)
    if major_ids:
        trace(major_ids, f"Every {major:g}", colour, "solid", 1.8)
        # One label per major line, at its middle vertex.
        lx, ly, lt = [], [], []
        for k in major_ids:
            pts = cs.line(k)
            if len(pts) >= 8:
                mid = pts[len(pts) // 2]
                lx.append(mid[0])
                ly.append(mid[1])
                lt.append(f"{cs.levels[k]:g}")
        fig.add_trace(go.Scatter(x=lx, y=ly, mode="text", text=lt, showlegend=False,
                                 textfont=dict(size=10, color=colour), hoverinfo="skip"))
    if closure is not None and background is not None:
        add_footprint(fig, background, closure.footprint, spill=closure.spill_depth,
                      name=f"Closure, spill {closure.spill_depth:.1f} m", color=SERIES[1],
                      dash="dash", width=2.5)
    if gone:
        trace(gone, "Deleted", "#8c8a82", "dot", 1.2)
    if sel:
        trace(sel, "Selected", SERIES[1], "solid", 3)
    if background is None:
        fig.update_layout(
            height=height, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="#ffffff",
            xaxis=dict(title="X (m)", tickformat="d", showgrid=False),
            yaxis=dict(title="Y (m)", tickformat="d", showgrid=False, scaleanchor="x",
                       scaleratio=1),
            legend=dict(x=0.01, y=0.99, xanchor="left", yanchor="top",
                        bgcolor="rgba(30,27,22,0.6)", font=dict(color="#ffffff")))
    fig.update_layout(title=dict(text=cs.name, font=dict(size=14)), dragmode="select")
    return fig


# --------------------------------------------------------------------------- structure contours
def nice_interval(relief: float, target: int = 25) -> float:
    """A round contour interval giving about ``target`` lines over ``relief``: 1, 2, 2.5 or 5
    times a power of ten."""
    if not relief > 0:
        return 1.0
    raw = relief / target
    power = 10.0 ** np.floor(np.log10(raw))
    for step in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= step * power:
            return float(step * power)
    return float(10 * power)


def add_structure_contours(fig: go.Figure, surface, interval: float | None = None, *,
                           colour: str = "#1e1b16", loc: dict | None = None,
                           major_every: int = 5) -> float:
    """Depth contours over a map: thin lines at ``interval``, every ``major_every``-th thicker
    and labelled. Returns the interval used (automatic when ``interval`` is None)."""
    st = surface.stats()
    interval = interval or nice_interval(st["max"] - st["min"])
    z = surface.values.filled(np.nan)
    start = np.ceil(st["min"] / interval) * interval
    major = interval * major_every
    loc = loc or {}
    common = dict(z=z, x=surface.x, y=surface.y, showscale=False, hoverinfo="skip",
                  showlegend=False)
    fig.add_trace(go.Contour(
        contours=dict(start=start, end=st["max"], size=interval, coloring="none"),
        line=dict(color=colour, width=0.6), name="contours", **common), **loc)
    fig.add_trace(go.Contour(
        contours=dict(start=np.ceil(st["min"] / major) * major, end=st["max"], size=major,
                      coloring="none", showlabels=True,
                      labelfont=dict(size=10, color=colour)),
        line=dict(color=colour, width=1.4), name=f"contours every {major:g}", **common), **loc)
    return interval
