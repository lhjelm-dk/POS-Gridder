"""The sidebar: import and the layer list, in the manner of a QGIS layer tree."""
from __future__ import annotations

import streamlit as st

from posgridder.core.model import DOMAINS, Project
from posgridder.io.surfaces import FORMATS, read_surface

UNITS_BY_DOMAIN = {"depth": "m", "time": "ms", "thickness": "m", "velocity": "m/s",
                   "pos": "fraction", "other": ""}


def select(name: str) -> None:
    """Make ``name`` the active layer on the next run.

    The layer list is a widget keyed ``active_surface``, and Streamlit refuses a write to a
    widget's key once it has rendered, so the choice is parked and applied before the list draws.
    """
    st.session_state["_pending_active"] = name


def project() -> Project:
    """The session's project, created on first use."""
    if "project" not in st.session_state:
        st.session_state["project"] = Project()
    return st.session_state["project"]


def _import_form(proj: Project) -> None:
    with st.form("import_surface", clear_on_submit=True, border=False):
        files = st.file_uploader("Surface files", accept_multiple_files=True,
                                 help="ZMAP+ (.dat, .zmap), IRAP classic ASCII (.irapasc, .fgr), "
                                      "IRAP binary (.gri, .irap). The format follows the extension "
                                      "unless one is chosen below.")
        labels = {"auto": "From extension"} | {k: f.label for k, f in FORMATS.items()}
        fmt = st.selectbox("Format", list(labels), format_func=labels.get)
        domain = st.selectbox("Domain", DOMAINS, index=DOMAINS.index("depth"))
        flip = st.checkbox("Flip sign", help="Depth is stored positive down. A file that stores "
                                             "depth or time as negative numbers is flipped here.")
        submitted = st.form_submit_button("Import", icon=":material/upload:")
    if not (submitted and files):
        return
    for upload in files:
        try:
            surface = read_surface(upload.getvalue(), None if fmt == "auto" else fmt,
                                   filename=upload.name)
        except Exception as exc:                        # noqa: BLE001 — reported to the user
            # Parked, not shown: the rerun below would clear a message written now.
            st.session_state.setdefault("_import_errors", []).append(f"{upload.name}: {exc}")
            continue
        surface.domain = domain
        surface.unit = UNITS_BY_DOMAIN[domain]
        if flip:
            surface.values = -surface.values
            surface.provenance += "; sign flipped on import"
        name = proj.add(surface)
        select(name)
        st.toast(f"Imported {name}", icon=":material/check:")
    st.rerun()


def _layer_list(proj: Project) -> None:
    names = list(proj.surfaces)
    pending = st.session_state.pop("_pending_active", None)
    if pending in names:
        st.session_state["active_surface"] = pending
    if not names:
        st.caption("No surfaces in the project.")
        return
    if st.session_state.get("active_surface") not in names:
        st.session_state["active_surface"] = names[0]
    active = st.radio("Surfaces", names, key="active_surface")

    with st.container(horizontal=True):
        if st.button("Copy", icon=":material/content_copy:"):
            select(proj.copy_surface(active))
            st.rerun()
        if st.button("Delete", icon=":material/delete:"):
            proj.remove(active)
            st.rerun()
    with st.form("rename_surface", border=False):
        new = st.text_input("Rename to", value=active)
        if st.form_submit_button("Rename", icon=":material/edit:") and new.strip():
            select(proj.rename(active, new.strip()))
            st.rerun()


def render() -> None:
    proj = project()
    with st.sidebar:
        st.subheader("Project", divider="gray")
        # Outside the import expander, which is folded once the project holds a surface.
        for message in st.session_state.pop("_import_errors", []):
            st.error(message, icon=":material/error:")
        _layer_list(proj)
        with st.expander("Import surfaces", icon=":material/upload_file:",
                         expanded=not proj.surfaces):
            _import_form(proj)
