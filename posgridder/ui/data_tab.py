"""Tab 1.0 Data: the active layer on a map, its geometry, statistics, lineage and export."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from posgridder.core.model import ProjectError
from posgridder.core.operations import recalculate
from posgridder.io.surfaces import FORMATS, write_surface
from posgridder.plotting.maps import COLORSCALES, surface_figure
from posgridder.ui.state import active, notify, project, select


def _stale_panel(uid: str) -> None:
    proj = project()
    reasons = proj.stale_reasons(uid)
    if not reasons:
        return
    with st.container(border=True):
        st.warning("**Stale.** " + "; ".join(reasons) + ". The layer still shows the values made "
                   "from the earlier inputs.", icon=":material/history:")
        if st.button("Recalculate from the newest inputs", icon=":material/refresh:",
                     key="recalculate"):
            try:
                select(recalculate(proj, uid).uid)
                notify("success", "Recalculated as a new version; the earlier one is kept in the "
                                  "project history.")
            except ProjectError as exc:
                notify("error", str(exc))
            st.rerun()


def render() -> None:
    proj = project()
    uid = active()
    if uid is None:
        st.info("The project holds no surfaces. Surfaces are imported in the sidebar.",
                icon=":material/info:")
        return
    surface = proj.objects[uid]
    _stale_panel(uid)
    for w in surface.warnings:
        st.warning(w, icon=":material/warning:")

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
                         "CRS", "Domain"],
            "Value": [f"{surface.ncol} × {surface.nrow}",
                      f"{surface.xinc:g} × {surface.yinc:g}",
                      f"{surface.xori:,.1f} – {surface.xmax:,.1f}",
                      f"{surface.yori:,.1f} – {surface.ymax:,.1f}",
                      surface.crs or "not stated",
                      f"{surface.domain} ({surface.unit})" if surface.unit else surface.domain],
        }), hide_index=True)
        st.subheader("Lineage", divider="gray")
        st.code("\n".join(proj.lineage(uid)), language=None, wrap_lines=True)
    with right:
        st.subheader("Statistics", divider="gray")
        stats = surface.stats()
        unit = f" {surface.unit}" if surface.unit else ""
        with st.container(horizontal=True):
            st.metric("Valid nodes", f"{stats['valid']:,}",
                      help=f"Of {stats['nodes']:,} nodes; the rest are null.", border=True)
            st.metric("Min", f"{stats['min']:.2f}{unit}", border=True)
            st.metric("Max", f"{stats['max']:.2f}{unit}", border=True)
            st.metric("Mean", f"{stats['mean']:.2f}{unit}", border=True)

        st.subheader("Export", divider="gray")
        fmt = st.selectbox("Format", list(FORMATS), format_func=lambda k: FORMATS[k].label,
                           key="export_format")
        st.download_button("Download", data=write_surface(surface, fmt),
                           file_name=f"{surface.name}{FORMATS[fmt].extensions[0]}",
                           icon=":material/download:", on_click="ignore")
        st.caption(f"Layer id {uid[:12]} · content hash {surface.content_hash[:12]}")
