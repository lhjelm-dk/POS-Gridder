"""POS-Gridder — Streamlit shell.

The sidebar holds the project's surfaces; each tab is a module in ``posgridder/ui``. The tabs
follow the workflow: start or open a project, prepare the structure (surfaces, or contours),
interpret the closure, measure it, bring in the contacts, and conclude with POS and the volumes
by percentile.
"""
from __future__ import annotations

import streamlit as st

from posgridder.io import autosave
from posgridder.ui import (closure_tab, contours_tab, pos_tab, progress, sidebar, start_tab,
                           surfaces_tab, theme, volumes_tab)
from posgridder.ui.state import project, show_notices

st.set_page_config(page_title="POS-Gridder", page_icon=":material/layers:", layout="wide")
theme.apply()

st.title("POS-Gridder")
st.caption("*by Lars Hjelm* · Surfaces, contours and spatial chance of success")

sidebar.render()
# Always one container here, empty or not: an element that comes and goes above the tabs would
# shift their position, and Streamlit would then rebuild them and jump back to the first tab.
with st.container():
    progress.render()
    show_notices()

start, surfaces, contours, closure, volumes, contacts, results = st.tabs(theme.tab_labels())
with start:
    start_tab.render()
with surfaces:
    surfaces_tab.render()
with contours:
    contours_tab.render()
with closure:
    closure_tab.render()
with volumes:
    volumes_tab.render()
with contacts:
    pos_tab.render_contacts()
with results:
    pos_tab.render_results()

# Autosave after the run, once whatever this run changed is in the project.
# The first write of a session moves the previous session's file aside (see io/autosave.py).
try:
    sig, written = autosave.save_if_changed(
        project(), st.session_state.get("_autosave_sig"),
        first_in_session=not st.session_state.get("_autosave_written", False))
    st.session_state["_autosave_sig"] = sig
    if written:
        st.session_state["_autosave_written"] = True
except OSError as exc:
    st.toast(f"Autosave failed: {exc}", icon=":material/warning:")
