"""Tab 6.0 Contours: contour sets made from a surface or imported, edited, and reconciled.

A contour set derived from a surface is not independent evidence: it records its source and
turns stale when the surface changes. Deleting lines makes a new version of the set; the source
surface is never changed by it. A surface is made from contours only on request, with a
declared method, as a new layer or — explicitly — as a new version of the source surface.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import streamlit as st

from posgridder.core.contours import DEFAULT_METHOD, METHODS, geometry_for
from posgridder.core.model import DOMAINS, ProjectError, Source
from posgridder.core.operations import apply, recalculate
from posgridder.io.vectors import Z_LEVEL, inspect, kind_of, to_geopackage
from posgridder.plotting.maps import contour_figure
from posgridder.ui.state import notify, project, select, uid_of


def _names(kind: str, domains=None) -> list[str]:
    proj = project()
    return [proj.objects[u].name for u in proj.current(kind)
            if domains is None or proj.objects[u].domain in domains]


def _make_form() -> None:
    proj = project()
    surfaces = _names("surface")
    if not surfaces:
        st.caption("No surface to contour.")
        return
    with st.form("make_contours", border=False):
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        name = c1.selectbox("Surface", surfaces)
        interval = c2.number_input("Interval", min_value=0.01, value=10.0, step=5.0)
        start = c3.number_input("Start", value=None, format="%.2f", placeholder="auto")
        stop = c4.number_input("Stop", value=None, format="%.2f", placeholder="auto")
        submitted = st.form_submit_button("Contour", icon=":material/stacked_line_chart:")
    if submitted:
        params = {"interval": interval}
        if start is not None:
            params["start"] = start
        if stop is not None:
            params["stop"] = stop
        try:
            cs = apply(proj, "contour", [uid_of(name)], params,
                       name=f"{name} contours {interval:g}")
            st.session_state["_pending_cs"] = cs.name
            notify("success", f"Made **{cs.name}**: {cs.n_lines} lines.")
        except ProjectError as exc:
            notify("error", str(exc))
        st.rerun()


def _import_form() -> None:
    proj = project()
    up = st.file_uploader("Contour file: GeoPackage, GeoJSON, zipped Shapefile, or ASCII "
                          "'x y z id'", type=["gpkg", "geojson", "json", "zip", "txt", "xyz",
                                              "dat", "csv"], key="contour_upload")
    if up is None:
        return
    try:
        kind = kind_of(up.name)
        info = inspect(up.getvalue(), up.name)
    except ValueError as exc:
        st.error(str(exc), icon=":material/error:")
        return
    if kind == "vector":
        st.caption(f"{info.n_features} features ({', '.join(info.geometry_types)}); "
                   f"Z values: {'yes' if info.has_z else 'no'}; CRS: {info.crs or 'not stated'}.")
    with st.form("import_contours", border=False):
        c1, c2, c3 = st.columns(3)
        if kind == "vector":
            fields = info.numeric_fields + ([Z_LEVEL] if info.has_z else [])
            level = c1.selectbox("Level from", fields, index=None if len(fields) != 1 else 0,
                                 placeholder="Choose the level attribute")
        else:
            level = Z_LEVEL
            c1.caption("Level from the z column.")
        domain = c2.selectbox("Domain", DOMAINS, index=None, placeholder="Required")
        flip = c3.checkbox("Flip the sign of the levels")
        crs = st.text_input("CRS", value=info.crs or "",
                            help="Kept as text; contour sets and surfaces with different stated "
                                 "systems are not combined.")
        name = st.text_input("Name", value=up.name.rsplit(".", 1)[0])
        submitted = st.form_submit_button("Import", type="primary", icon=":material/upload:")
    if submitted:
        if level is None or domain is None:
            notify("error", "The level field and the domain are required.")
            st.rerun()
        source = Source.from_bytes(up.name, up.getvalue())
        proj.add_source(source, up.getvalue())
        try:
            cs = apply(proj, "contour_import", [source.uid],
                       {"level_field": None if level == Z_LEVEL else level, "domain": domain,
                        "flip_sign": flip, "crs": crs.strip() or None}, name=name)
            st.session_state["_pending_cs"] = cs.name
            notify("success", f"Imported **{cs.name}**: {cs.n_lines} lines.")
            for w in cs.warnings:
                notify("warning", w)
        except ProjectError as exc:
            proj.sources.pop(source.uid, None)
            proj.source_bytes.pop(source.uid, None)
            notify("error", str(exc))
        st.rerun()


def _edit(cs, delete=(), restore=()) -> None:
    try:
        apply(project(), "contour_edit", [cs.uid],
              {"delete": sorted(int(k) for k in delete), "restore": sorted(int(k) for k in restore)},
              name=cs.name, replace=True)
        st.session_state.pop("contour_selection", None)
        notify("success", f"{len(delete)} lines deleted, {len(restore)} restored: a new version "
                          f"of **{cs.name}**.")
    except ProjectError as exc:
        notify("error", str(exc))
    st.rerun()


def _view(cs) -> None:
    proj = project()
    for reason in proj.stale_reasons(cs.uid):
        st.warning(f"**Stale.** {reason}.", icon=":material/history:")
    if proj.is_stale(cs.uid) and st.button("Recalculate", icon=":material/refresh:",
                                           key="cs_recalc"):
        try:
            recalculate(proj, cs.uid)
            notify("success", "Recalculated as a new version.")
        except ProjectError as exc:
            notify("error", str(exc))
        st.rerun()
    for w in cs.warnings:
        st.warning(w, icon=":material/warning:")
    st.caption(f"{cs.origin.capitalize()}. {len(cs.active())} of {cs.n_lines} lines active; "
               f"domain {cs.domain}.")

    background = proj.objects.get(cs.source_uid) if cs.source_uid else None
    selected = set(st.session_state.get("contour_selection", {}).get(cs.uid, []))
    event = st.plotly_chart(contour_figure(cs, background=background, selected=selected),
                            key=f"contour_map_{cs.uid}", on_select="rerun",
                            selection_mode=("box", "lasso", "points"))
    picked = {int(p["customdata"]) for p in (event.selection.points if event else [])
              if p.get("customdata") is not None}
    if picked and picked != selected:
        st.session_state["contour_selection"] = {cs.uid: sorted(picked)}
        st.rerun()
    st.caption("Box or lasso on the map selects lines (the toolbar switches between them).")

    table = pd.DataFrame({
        "Line": np.arange(cs.n_lines), "Level": cs.levels,
        "Closed": [cs.closed(k) for k in range(cs.n_lines)],
        "Area (km²)": [cs.area_km2(k) for k in range(cs.n_lines)],
        "Vertices": np.diff(cs.offsets), "Deleted": cs.deleted,
    })
    ev = st.dataframe(table, hide_index=True, on_select="rerun", selection_mode="multi-row",
                      height=240, key=f"contour_table_{cs.uid}")
    rows = set(ev.selection.rows) if ev else set()
    chosen = sorted(selected | rows)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.write(f"Selected lines: {', '.join(map(str, chosen)) if chosen else 'none'}")
        if st.button("Delete selected", icon=":material/delete:", disabled=not chosen,
                     key="cs_delete"):
            _edit(cs, delete=[k for k in chosen if not cs.deleted[k]])
        if st.button("Restore selected", icon=":material/undo:", disabled=not chosen,
                     key="cs_restore"):
            _edit(cs, restore=[k for k in chosen if cs.deleted[k]])
        if st.button("Clear selection", key="cs_clear", disabled=not chosen):
            st.session_state.pop("contour_selection", None)
            st.rerun()
        closed = [k for k in chosen if cs.closed(k)]
        if len(closed) == 1 and st.button("Outline from this line", icon=":material/pentagon:",
                                          key="cs_outline"):
            try:
                o = apply(proj, "outline_from_contour", [cs.uid], {"line": closed[0]},
                          name=f"{cs.name} line {closed[0]}")
                notify("success", f"Made the outline **{o.name}** ({o.area_km2:.3f} km²).")
            except ProjectError as exc:
                notify("error", str(exc))
            st.rerun()
    st.download_button("Contours (GeoPackage)", to_geopackage(cs), file_name=f"{cs.name}.gpkg",
                       icon=":material/download:", on_click="ignore")
    _reconcile(cs)


def _reconcile(cs) -> None:
    proj = project()
    st.subheader("Make a surface from these contours", divider="gray")
    st.caption("The active lines only. Thin-plate spline is the default, chosen by the D9 "
               "benchmark (docs/BENCHMARK.md); linear TIN honours the contours exactly and never "
               "overshoots, but is flat inside the innermost contour.")
    source = proj.objects.get(cs.source_uid) if cs.source_uid else None
    templates = _names("surface")
    with st.form("reconcile", border=False):
        c1, c2 = st.columns(2)
        method = c1.radio("Method", list(METHODS), index=list(METHODS).index(DEFAULT_METHOD),
                          format_func=METHODS.get)
        template = c2.selectbox("Grid nodes from", ["A new grid over the contours", *templates],
                                index=1 + templates.index(source.name)
                                if source is not None and source.name in templates else 0)
        inc = c2.number_input("Cell size for a new grid (m)", min_value=1.0, value=50.0, step=25.0)
        crest = st.text_area("Crest points (optional): x y depth, one per line", height=70,
                             help="Fixes the crest inside the innermost contour, where the "
                                  "contours say nothing.")
        replace_source = False
        if source is not None and source.uid in proj.layers:
            replace_source = st.checkbox(
                f"Make the result a new version of '{source.name}'",
                help="Its dependents (closures, volumes, POS maps) are then marked stale. "
                     "Otherwise the result is a new layer and nothing else changes.")
        name = st.text_input("Name", value=f"{cs.name} → surface")
        submitted = st.form_submit_button("Make surface", type="primary",
                                          icon=":material/grid_on:")
    if not submitted:
        return
    try:
        points = []
        for ln in crest.splitlines():
            if ln.strip():
                x, y, z = (float(v) for v in re.split(r"[\t,; ]+", ln.strip())[:3])
                points.append([x, y, z])
        params = {"method": method, "crest_points": points}
        inputs = [cs.uid]
        if template == "A new grid over the contours":
            params["roles"] = ["contours"]
            params["geometry"] = geometry_for(cs, inc)
        else:
            params["roles"] = ["contours", "template"]
            inputs.append(uid_of(template))
        surface = apply(proj, "contours_to_surface", inputs, params,
                        name=source.name if replace_source else name,
                        supersedes=source.uid if replace_source else None)
        select(surface.uid)
        notify("success", f"Made **{surface.name}** ({METHODS[method].split(' (')[0]}).")
        for w in surface.warnings:
            notify("warning", w)
    except (ValueError, ProjectError) as exc:
        notify("error", str(exc))
    st.rerun()


def render() -> None:
    with st.expander("Contour a surface", icon=":material/stacked_line_chart:",
                     expanded=not _names("contours")):
        _make_form()
    with st.expander("Import contours", icon=":material/upload_file:"):
        _import_form()
    names = _names("contours")
    if not names:
        return
    pending = st.session_state.pop("_pending_cs", None)
    if pending in names:
        st.session_state["cs_view"] = pending
    cs = project().objects[uid_of(st.selectbox("Contour set", names, key="cs_view"))]
    _view(cs)
