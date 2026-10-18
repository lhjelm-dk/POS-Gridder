"""POS-Gridder — Streamlit shell.

The sidebar holds the project's layers; each tab is a module in ``posgridder/ui``. Tabs carry
the numbers they have in ``docs/PLAN.md`` §6.4.
"""
from __future__ import annotations

import streamlit as st

from posgridder.ui import (closure_tab, contours_tab, data_tab, pos_tab, prepare_tab,
                           project_tab, sidebar, volumes_tab)
from posgridder.ui.state import show_notices

st.set_page_config(page_title="POS-Gridder", page_icon=":material/layers:", layout="wide")

st.title("POS-Gridder")
st.caption("*by Lars Hjelm* · Surfaces, contours and gridded chance of success")

sidebar.render()
# Always one container here, empty or not: an element that comes and goes above the tabs would
# shift their position, and Streamlit would then rebuild them and jump back to the first tab.
with st.container():
    show_notices()

data, prepare, closure, volumes, hcwc, contours, project = st.tabs(
    ["1.0 Data", "2.0 Prepare", "3.0 Closure", "4.0 Volumes", "5.0 HCWC & POS", "6.0 Contours",
     "7.0 Project"])
with data:
    data_tab.render()
with prepare:
    prepare_tab.render()
with closure:
    closure_tab.render()
with volumes:
    volumes_tab.render()
with hcwc:
    pos_tab.render()
with contours:
    contours_tab.render()
with project:
    project_tab.render()
