"""Tab 5 Volumes: area–depth and GRV for a confirmed closure, outlines, and exports."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from posgridder.core.model import ProjectError
from posgridder.core.operations import apply, recalculate
from posgridder.core.outline import parse_xy
from posgridder.core.volumes import GEOMETRIES, builder_csv, scope_csv
from posgridder.plotting.charts import area_depth_figure, grv_figure
from posgridder.ui.state import notify, project, uid_of


def _names(kind: str, domain: str | None = None) -> list[str]:
    proj = project()
    return [proj.objects[u].name for u in proj.current(kind)
            if domain is None or proj.objects[u].domain == domain]


def _calculate_form() -> None:
    proj = project()
    closures = _names("closure")
    if not closures:
        st.info("Volumes are computed on a confirmed closure (tab **4 Closure**).",
                icon=":material/info:")
        return
    geometry = st.segmented_control("Geometry", list(GEOMETRIES), format_func=GEOMETRIES.get,
                                    default="top_constant", key="vol_geometry") or "top_constant"
    with st.form("volumes", border=False):
        closure_name = st.selectbox("Closure", closures)
        params: dict = {"geometry": geometry}
        extra_role, extra_name = None, None
        if geometry == "top_base":
            extra_name = st.selectbox("Base surface (depth)", _names("surface", "depth"))
            extra_role = "base"
        elif geometry == "top_grid":
            extra_name = st.selectbox("Thickness surface", _names("surface", "thickness"),
                                      placeholder="None: subtract base − top on tab 2.0",
                                      index=0 if _names("surface", "thickness") else None)
            extra_role = "thickness"
        else:
            params["thickness"] = st.number_input("Thickness (m, vertical)", min_value=0.1,
                                                  value=50.0, step=5.0)
        outlines = _names("outline")
        outline = st.selectbox("Outline", ["None", *outlines],
                               help="Limits area and GRV to the polygon. It is never a spill "
                                    "barrier.")
        params["step"] = st.number_input("Depth step (m)", min_value=0.1, value=1.0, step=0.5)
        name = st.text_input("Name", placeholder="Default: closure name + geometry")
        submitted = st.form_submit_button("Calculate", type="primary", icon=":material/calculate:")
    if not submitted:
        return
    closure = proj.objects[uid_of(closure_name)]
    roles, inputs = ["closure", "top"], [closure.uid, closure.surface_uid]
    if extra_role:
        if not extra_name:
            notify("error", f"The {GEOMETRIES[geometry].lower()} geometry needs a {extra_role} "
                            "surface.")
            st.rerun()
        roles.append(extra_role)
        inputs.append(uid_of(extra_name))
    if outline != "None":
        roles.append("outline")
        inputs.append(uid_of(outline))
    params["roles"] = roles
    try:
        result = apply(proj, "volumes", inputs, params,
                       name=name.strip() or f"{closure.name} · {GEOMETRIES[geometry].lower()}")
    except ProjectError as exc:
        notify("error", str(exc))
    else:
        st.session_state["_pending_volume"] = result.name
        notify("success", f"Calculated ‘{result.name}’.")
    st.rerun()


def _outlines() -> None:
    proj = project()
    with st.expander("Outlines", icon=":material/pentagon:"):
        st.caption("Boundary polygons that limit area and GRV. Vertices as one 'x y' pair per "
                   "line, in the grid's coordinates; the ring closes itself.")
        with st.form("outline_text", clear_on_submit=True, border=False):
            text = st.text_area("Vertices", height=140, placeholder="630000 6160000\n640000 "
                                                                    "6160000\n640000 6170000")
            upload = st.file_uploader("…or a text file of vertices", type=["txt", "xy", "csv", "dat"])
            name = st.text_input("Name", value="outline")
            add = st.form_submit_button("Add outline", icon=":material/add:")
        if add:
            raw = upload.getvalue().decode("utf-8", errors="replace") if upload else text
            try:
                coords = parse_xy(raw)
                surfaces = proj.current("surface")
                crs = proj.objects[surfaces[0]].crs if surfaces else None
                apply(proj, "outline_points", [], {"coords": coords.tolist(), "crs": crs},
                      name=name)
                notify("success", f"Added the outline ‘{name}’.")
            except (ValueError, ProjectError) as exc:
                notify("error", f"Outline not added: {exc}")
            st.rerun()
        closures = _names("closure")
        if closures:
            with st.container(horizontal=True, vertical_alignment="bottom"):
                c_name = st.selectbox("From a closure footprint", closures, key="outline_from")
                if st.button("Make outline", icon=":material/polyline:"):
                    try:
                        o = apply(proj, "outline_from_closure", [uid_of(c_name)],
                                  name=f"{c_name} outline")
                        notify("success", f"Made ‘{o.name}’ ({o.area_km2:.2f} km²).")
                    except ProjectError as exc:
                        notify("error", str(exc))
                    st.rerun()
        uids = proj.current("outline")
        if uids:
            st.dataframe(pd.DataFrame([{"Name": proj.objects[u].name,
                                        "Vertices": len(proj.objects[u].coords),
                                        "Area (km²)": round(proj.objects[u].area_km2, 3),
                                        "Made by": proj.objects[u].derivation.operation}
                                       for u in uids]), hide_index=True)


def _results() -> None:
    proj = project()
    names = _names("volumes")
    st.subheader("Results", divider="gray")
    if not names:
        st.caption("None yet.")
        return
    pending = st.session_state.pop("_pending_volume", None)
    if pending in names:
        st.session_state["volume_view"] = pending
    name = st.selectbox("Result", names, key="volume_view")
    v = proj.objects[uid_of(name)]
    for reason in proj.stale_reasons(v.uid):
        st.warning(f"Stale: {reason}.", icon=":material/history:")
    if proj.is_stale(v.uid) and st.button("Recalculate", icon=":material/refresh:",
                                          key="vol_recalc"):
        try:
            recalculate(proj, v.uid)
            notify("success", "Recalculated as a new version.")
        except ProjectError as exc:
            notify("error", str(exc))
        st.rerun()

    s = v.summary
    with st.container(horizontal=True):
        st.metric("Crest", f"{s['crest_depth_m']:.1f} m", border=True)
        st.metric("Spill", f"{s['spill_depth_m']:.1f} m", border=True)
        st.metric("Area at spill", f"{s['area_at_spill_km2']:.3f} km²", border=True)
        st.metric("GRV at spill", f"{s['grv_direct_at_spill_1e6m3']:,.2f} × 10⁶ m³",
                  help="Direct column sum over the footprint.", border=True)
        st.metric("Area–depth vs direct", f"{s['agreement_relative']:.2%}",
                  help="Relative difference of the two GRV routes at the spill; tolerance 1 %.",
                  border=True)
    for w in v.warnings:
        st.warning(w, icon=":material/warning:")
    st.markdown("Assumptions:\n\n" + "\n".join(f"- {a}" for a in v.assumptions))

    left, right = st.columns(2)
    with left:
        st.plotly_chart(area_depth_figure(v.table, s["spill_depth_m"]), key="area_depth_chart")
    with right:
        st.plotly_chart(grv_figure(v.table, s["spill_depth_m"]), key="grv_chart")

    st.dataframe(v.table.rename(columns={
        "depth_m": "Depth (m)", "top_area_km2": "Top area (km²)",
        "base_area_km2": "Base area (km²)", "grv_trapezoid_1e6m3": "GRV area–depth (10⁶ m³)",
        "grv_direct_1e6m3": "GRV direct (10⁶ m³)", "grv_single_fill_1e6m3": "GRV single fill (10⁶ m³)",
    }), hide_index=True, height=260)
    provenance = [f"POS-Gridder {v.derivation.app_version}: {v.name}",
                  *proj.lineage(v.uid), *v.assumptions]
    with st.container(horizontal=True):
        st.download_button("HCWC Builder area–depth (CSV)", builder_csv(v, provenance),
                           file_name=f"{v.name} area_depth.csv", mime="text/csv",
                           icon=":material/download:", on_click="ignore")
        st.download_button("SCOPE-HC area–depth (CSV)", scope_csv(v),
                           file_name=f"{v.name} scope_area_depth.csv", mime="text/csv",
                           icon=":material/download:", on_click="ignore")


def render() -> None:
    _calculate_form()
    _outlines()
    _results()
