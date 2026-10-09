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
    )
    return fig
