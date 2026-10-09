"""Tab 1.0 Surfaces: the active surface on a map, its geometry and statistics, and export."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from posgridder.io.surfaces import FORMATS, write_surface
from posgridder.plotting.maps import COLORSCALES, surface_figure
from posgridder.ui.sidebar import project


def render() -> None:
    proj = project()
    name = st.session_state.get("active_surface")
    if not proj.surfaces or name not in proj.surfaces:
        st.info("The project holds no surfaces. Surfaces are imported in the sidebar.",
                icon=":material/info:")
        return
    surface = proj.surfaces[name]

    with st.container(horizontal=True, vertical_alignment="bottom"):
        colorscale = st.selectbox("Colour scale", COLORSCALES, key="map_colorscale", width=200)
        reverse = st.toggle("Reverse", key="map_reverse")
    st.plotly_chart(surface_figure(surface, colorscale=colorscale, reverse=reverse),
                    key="surface_map")

    left, right = st.columns(2)
    with left:
        st.subheader("Geometry", divider="gray")
        st.dataframe(pd.DataFrame({
            "Property": ["Columns × rows", "Increment X × Y (m)", "X range (m)", "Y range (m)",
                         "CRS", "Domain", "Provenance"],
            "Value": [f"{surface.ncol} × {surface.nrow}",
                      f"{surface.xinc:g} × {surface.yinc:g}",
                      f"{surface.xori:,.1f} – {surface.xmax:,.1f}",
                      f"{surface.yori:,.1f} – {surface.ymax:,.1f}",
                      surface.crs or "not stated",
                      f"{surface.domain} ({surface.unit})" if surface.unit else surface.domain,
                      surface.provenance or "–"],
        }), hide_index=True)
    with right:
        st.subheader("Statistics", divider="gray")
        stats = surface.stats()
        with st.container(horizontal=True):
            st.metric("Valid nodes", f"{stats['valid']:,}",
                      help=f"Of {stats['nodes']:,} nodes; the rest are null.", border=True)
            st.metric("Min", f"{stats['min']:.2f}", border=True)
            st.metric("Max", f"{stats['max']:.2f}", border=True)
            st.metric("Mean", f"{stats['mean']:.2f}", border=True)

        st.subheader("Export", divider="gray")
        fmt = st.selectbox("Format", list(FORMATS), format_func=lambda k: FORMATS[k].label,
                           key="export_format")
        st.download_button("Download", data=write_surface(surface, fmt),
                           file_name=f"{surface.name}{FORMATS[fmt].extensions[0]}",
                           icon=":material/download:", on_click="ignore")
