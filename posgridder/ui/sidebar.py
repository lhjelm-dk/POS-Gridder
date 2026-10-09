"""The sidebar: the layer list, in the manner of a QGIS layer tree, and the import form."""
from __future__ import annotations

import streamlit as st

from posgridder.core.model import DOMAINS, UNITS, ProjectError
from posgridder.core.operations import apply
from posgridder.io.surfaces import FORMATS, import_surface
from posgridder.ui.state import active as active_uid, notify, project, select

DOMAIN_LABELS = {d: f"{d} ({UNITS[d]})" if UNITS[d] else d for d in DOMAINS}


def _caption(uid: str) -> str:
    proj = project()
    flag = " · :orange[stale]" if proj.is_stale(uid) else ""
    return f"{proj.objects[uid].domain}{flag}"


def _import_form() -> None:
    proj = project()
    with st.form("import_surface", clear_on_submit=True, border=False):
        files = st.file_uploader("Surface files", accept_multiple_files=True,
                                 help="ZMAP+ ASCII grids (.dat, .zmap, .zmp). The file is kept in "
                                      "the project with its SHA-256, so every layer can be "
                                      "recomputed from it.")
        domain = st.selectbox("Domain", DOMAINS, index=None, format_func=DOMAIN_LABELS.get,
                              placeholder="What the values measure",
                              help="No default: a time grid read as depth gives plausible "
                                   "numbers that mean nothing.")
        flip = st.checkbox("Flip sign", help="Depth and time are stored positive down. A file "
                                             "that stores them as negative numbers is flipped "
                                             "here; the flip is recorded as an import parameter.")
        crs = st.text_input("CRS", placeholder="From the file, if it states one",
                            help="Overrides the coordinate system the file states. Layers with "
                                 "different stated systems are not combined.")
        submitted = st.form_submit_button("Import", icon=":material/upload:")
    if not submitted:
        return
    if not files:
        notify("warning", "No file was chosen.")
    elif domain is None:
        notify("error", "The domain is required: the import records what the values measure.")
    else:
        for upload in files:
            try:
                surface = import_surface(proj, upload.name, upload.getvalue(), domain=domain,
                                         flip_sign=flip, crs=crs.strip() or None)
            except (ValueError, ProjectError) as exc:
                notify("error", f"{upload.name}: {exc}")
                continue
            select(surface.uid)
            notify("success", f"Imported **{surface.name}** as {domain}.")
            for w in surface.warnings:
                notify("warning", f"{surface.name}: {w}")
    st.rerun()


def _layer_list() -> None:
    proj = project()
    surfaces = proj.current("surface")
    names = [proj.objects[u].name for u in surfaces]
    pending = st.session_state.pop("_pending_active", None)
    if pending in surfaces:
        st.session_state["active_layer"] = proj.objects[pending].name
    if not surfaces:
        st.caption("No surfaces in the project.")
        return
    if st.session_state.get("active_layer") not in names:
        st.session_state["active_layer"] = names[0]
    # Names are the options: they are unique among current layers, and a label that changes
    # (a layer turning stale) must not change the widget's value, so state goes in the captions.
    st.radio("Surfaces", names, captions=[_caption(u) for u in surfaces], key="active_layer")
    active = active_uid()

    with st.container(horizontal=True):
        if st.button("Copy", icon=":material/content_copy:"):
            obj = proj.objects[active]
            select(apply(proj, "copy", [active], name=f"{obj.name} copy").uid)
            st.rerun()
        if st.button("Delete", icon=":material/delete:",
                     help="Takes the surface off the list. Objects made from it keep it in "
                          "their history, so they stay reproducible."):
            proj.remove(active)
            st.rerun()
    with st.form("rename_layer", border=False):
        new = st.text_input("Rename to", value=proj.objects[active].name)
        if st.form_submit_button("Rename", icon=":material/edit:") and new.strip():
            select(proj.rename(active, new.strip()).uid)
            st.rerun()


def render() -> None:
    with st.sidebar:
        st.subheader("Project", divider="gray")
        _layer_list()
        with st.expander("Import surfaces", icon=":material/upload_file:",
                         expanded=not project().current("surface")):
            _import_form()
        st.caption(f"Formats: {', '.join(f.label for f in FORMATS.values())}")
