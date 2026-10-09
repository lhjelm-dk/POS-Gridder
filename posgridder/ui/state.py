"""Session state shared by the sidebar and the tabs: the project, the active layer, notices."""
from __future__ import annotations

import streamlit as st

from posgridder.core.model import Project


def project() -> Project:
    """The session's project, created on first use."""
    if "project" not in st.session_state:
        st.session_state["project"] = Project()
    return st.session_state["project"]


def select(uid: str | None) -> None:
    """Make ``uid`` the active layer on the next run.

    The layer list is a widget keyed ``active_layer``, and Streamlit refuses a write to a
    widget's key once it has rendered, so the choice is parked and applied before the list draws.
    """
    st.session_state["_pending_active"] = uid


def uid_of(name: str | None) -> str | None:
    """Layer widgets offer names, which are unique among current layers; this maps one back."""
    if name is None:
        return None
    try:
        return project().by_name(name).uid
    except KeyError:
        return None


def active() -> str | None:
    """The active surface's uid. The layer list holds its name."""
    uid = uid_of(st.session_state.get("active_layer"))
    return uid if uid is not None and project().objects[uid].kind == "surface" else None


def notify(kind: str, message: str) -> None:
    """Park a message for the next run; a rerun would clear one written now."""
    st.session_state.setdefault("_notices", []).append((kind, message))


def show_notices() -> None:
    icons = {"error": ":material/error:", "warning": ":material/warning:",
             "success": ":material/check_circle:", "info": ":material/info:"}
    for kind, message in st.session_state.pop("_notices", []):
        getattr(st, kind)(message, icon=icons[kind])
