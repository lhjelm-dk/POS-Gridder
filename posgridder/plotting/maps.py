"""Map figures. Plotly, because the map needs equal axes in metres, hover values and, from
Phase 4, click and lasso selection of contours."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from posgridder.core.model import Surface

COLORSCALES: tuple[str, ...] = ("Viridis", "Turbo", "Earth", "RdBu", "Greys")


def surface_figure(surface: Surface, *, colorscale: str = "Viridis", reverse: bool = False,
                   height: int = 650) -> go.Figure:
    """The surface as a heatmap in its own coordinates, nulls left blank."""
    z = surface.values.filled(np.nan)
    unit = f" {surface.unit}" if surface.unit else ""
    fig = go.Figure(go.Heatmap(
        z=z, x=surface.x, y=surface.y,
        colorscale=colorscale, reversescale=reverse,
        colorbar=dict(title=dict(text=f"{surface.domain}{(' (' + surface.unit + ')') if surface.unit else ''}")),
        hovertemplate="X %{x:.0f}<br>Y %{y:.0f}<br>%{z:.2f}" + unit + "<extra></extra>",
    ))
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(title="X (m)", tickformat="d", showgrid=False),
        # Equal scaling, so a 250 m cell is square on screen.
        yaxis=dict(title="Y (m)", tickformat="d", showgrid=False, scaleanchor="x", scaleratio=1),
        title=dict(text=surface.name, font=dict(size=14)),
        legend=dict(x=0.01, y=0.99, xanchor="left", yanchor="top",
                    bgcolor="rgba(30,27,22,0.6)", font=dict(color="#ffffff")),
    )
    return fig


# --------------------------------------------------------------------------- overlays
#: Reference categorical slots (dataviz palette, light mode): blue, orange, aqua.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")


def add_footprint(fig: go.Figure, surface: Surface, footprint: np.ndarray, *, name: str,
                  color: str = "#ffffff", dash: str = "solid") -> go.Figure:
    """The boundary of a footprint mask, drawn as one contour line at 0.5."""
    fig.add_trace(go.Contour(
        z=footprint.astype(float), x=surface.x, y=surface.y, name=name, showlegend=True,
        contours=dict(start=0.5, end=0.5, size=1, coloring="none"),
        line=dict(color=color, width=2, dash=dash), showscale=False, hoverinfo="skip"))
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


def pos_figure(m, *, height: int = 600, title: str | None = None) -> go.Figure:
    """POS in the trap on a sequential ramp; the other categories in flat greys beneath it."""
    from posgridder.core.pos import CATEGORIES

    fig = go.Figure()
    for code, grey in CATEGORY_GREYS.items():
        sel = m.category == code
        if not sel.any():
            continue
        fig.add_trace(go.Heatmap(
            z=np.where(sel, 1.0, np.nan), x=m.x, y=m.y, colorscale=[[0, grey], [1, grey]],
            showscale=False, name=CATEGORIES[code], showlegend=True,
            hovertemplate=f"{CATEGORIES[code]}<extra></extra>"))
    zero = np.where(m.category == 2, 0.0, np.nan)
    if np.isfinite(zero).any():
        fig.add_trace(go.Heatmap(z=zero, x=m.x, y=m.y, colorscale=[[0, "#f5f1e6"], [1, "#f5f1e6"]],
                                 showscale=False, name=CATEGORIES[2], showlegend=True,
                                 hovertemplate=f"{CATEGORIES[2]}: POS 0<extra></extra>"))
    vmax = max(float(np.nanmax(m.pos)) if np.isfinite(m.pos).any() else 0.0, 1e-6)
    fig.add_trace(go.Heatmap(
        z=np.where(m.category == 1, m.pos, np.nan), x=m.x, y=m.y, zmin=0, zmax=vmax,
        colorscale=POS_SCALE, name="POS", colorbar=dict(title=dict(text="POS"), tickformat=".0%"),
        hovertemplate="X %{x:.0f}<br>Y %{y:.0f}<br>POS %{z:.1%}<extra></extra>"))
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(title="X (m)", tickformat="d", showgrid=False),
        yaxis=dict(title="Y (m)", tickformat="d", showgrid=False, scaleanchor="x", scaleratio=1),
        title=dict(text=title or m.name, font=dict(size=14)),
        legend=dict(x=0.01, y=0.99, xanchor="left", yanchor="top",
                    bgcolor="rgba(30,27,22,0.6)", font=dict(color="#ffffff")),
        plot_bgcolor="#ffffff")
    return fig
