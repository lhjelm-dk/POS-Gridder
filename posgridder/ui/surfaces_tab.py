"""Tab 2 Surfaces: the active surface on a map, and the tools that make new surfaces.

One switch at the top: the map (with geometry, statistics, lineage and export) or one of the
tools — depth conversion, arithmetic, resampling. Each tool makes a new layer through a
recorded operation.
"""
from __future__ import annotations

import streamlit as st

from posgridder.ui import data_tab, prepare_tab

VIEWS = ["Map", *prepare_tab.TOOLS]


def render() -> None:
    view = st.segmented_control("View", VIEWS, default="Map", key="surface_view",
                                label_visibility="collapsed") or "Map"
    if view == "Map":
        data_tab.render()
    else:
        with st.container(border=True):
            prepare_tab.render_tool(view)
