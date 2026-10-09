"""Depth charts for the volumes tab. Depth runs down the y axis, as on a well section."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from posgridder.plotting.maps import SERIES


def _depth_layout(fig: go.Figure, xtitle: str, spill: float, height: int = 420) -> go.Figure:
    fig.add_hline(y=spill, line=dict(color="#7a776f", width=1, dash="dot"),
                  annotation_text=f"spill {spill:.1f} m", annotation_position="bottom right")
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), hovermode="y unified",
        xaxis=dict(title=xtitle, rangemode="tozero", gridcolor="#ebe8df", zeroline=False),
        yaxis=dict(title="Depth (m TVDSS)", autorange="reversed", gridcolor="#ebe8df"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        plot_bgcolor="#ffffff",
    )
    return fig


def area_depth_figure(table: pd.DataFrame, spill: float) -> go.Figure:
    fig = go.Figure()
    for col, label, color in (("top_area_km2", "Top", SERIES[0]),
                              ("base_area_km2", "Base", SERIES[1])):
        fig.add_trace(go.Scatter(x=table[col], y=table["depth_m"], mode="lines", name=label,
                                 line=dict(color=color, width=2),
                                 hovertemplate=f"{label} %{{x:.3f}} km²<extra></extra>"))
    return _depth_layout(fig, "Area (km²)", spill)


def grv_figure(table: pd.DataFrame, spill: float) -> go.Figure:
    fig = go.Figure()
    for col, label, color, dash in (
            ("grv_direct_1e6m3", "Direct (column sum)", SERIES[0], "solid"),
            ("grv_trapezoid_1e6m3", "Area–depth (trapezoid)", SERIES[1], "dash"),
            ("grv_single_fill_1e6m3", "Single fill from the crest", SERIES[2], "solid")):
        fig.add_trace(go.Scatter(x=table[col], y=table["depth_m"], mode="lines", name=label,
                                 line=dict(color=color, width=2, dash=dash),
                                 hovertemplate=f"{label} %{{x:.2f}}<extra></extra>"))
    return _depth_layout(fig, "GRV above the contact (10⁶ m³)", spill)
