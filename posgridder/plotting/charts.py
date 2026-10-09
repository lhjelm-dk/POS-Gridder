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


def exceedance_figure(depths, exceedance, *, multiplier: float | None = None,
                      marks: dict | None = None) -> go.Figure:
    """Exceedance (and POS = multiplier × exceedance) against depth, depth down."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=exceedance, y=depths, mode="lines", name="P(contact deeper)",
                             line=dict(color=SERIES[0], width=2),
                             hovertemplate="%{x:.1%} at %{y:.1f} m<extra></extra>"))
    if multiplier is not None:
        fig.add_trace(go.Scatter(x=multiplier * exceedance, y=depths, mode="lines",
                                 name=f"POS (× {multiplier:.3f})",
                                 line=dict(color=SERIES[1], width=2),
                                 hovertemplate="%{x:.1%} at %{y:.1f} m<extra></extra>"))
    for label, depth in (marks or {}).items():
        fig.add_hline(y=depth, line=dict(color="#7a776f", width=1, dash="dot"),
                      annotation_text=f"{label} {depth:.1f} m",
                      annotation_position="bottom right")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), hovermode="y unified",
                      xaxis=dict(title="Probability", tickformat=".0%", range=[0, 1.02],
                                 gridcolor="#ebe8df"),
                      yaxis=dict(title="Depth (m TVDSS)", autorange="reversed",
                                 gridcolor="#ebe8df"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
                      plot_bgcolor="#ffffff")
    return fig


def percentile_figure(table: pd.DataFrame) -> go.Figure:
    """GRV against exceedance percentile (P100 at the left, as in the Builder)."""
    fig = go.Figure()
    for col, label, color in (("grv_1e6m3", "GRV (area–depth)", SERIES[0]),
                              ("grv_single_fill_1e6m3", "GRV, single fill", SERIES[2])):
        fig.add_trace(go.Scatter(x=table["percentile"], y=table[col], mode="lines", name=label,
                                 line=dict(color=color, width=2),
                                 hovertemplate="P%{x:.0f}: %{y:.2f} × 10⁶ m³<extra></extra>"))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
                      xaxis=dict(title="Exceedance percentile", autorange="reversed",
                                 gridcolor="#ebe8df", dtick=10),
                      yaxis=dict(title="GRV (10⁶ m³)", rangemode="tozero", gridcolor="#ebe8df"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
                      plot_bgcolor="#ffffff")
    return fig
