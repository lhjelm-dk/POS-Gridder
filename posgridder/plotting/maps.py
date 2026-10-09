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
