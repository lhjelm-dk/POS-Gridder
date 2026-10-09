"""POS-Gridder — Streamlit shell.

The sidebar holds the project's layers; each tab is a module in ``posgridder/ui``. Tabs carry
the numbers they have in ``docs/PLAN.md`` §6.4, so a tab added in a later phase slots in
without renumbering: 3.0 Closure, 4.0 Volumes, 5.0 HCWC & POS and 6.0 Contours follow.
"""
from __future__ import annotations

import streamlit as st

from posgridder.ui import data_tab, prepare_tab, project_tab, sidebar
from posgridder.ui.state import show_notices

st.set_page_config(page_title="POS-Gridder", page_icon=":material/layers:", layout="wide")

st.title("POS-Gridder")
st.caption("*by Lars Hjelm* · Surfaces, contours and gridded chance of success")

sidebar.render()
show_notices()

data, prepare, project = st.tabs(["1.0 Data", "2.0 Prepare", "7.0 Project"])
with data:
    data_tab.render()
with prepare:
    prepare_tab.render()
with project:
    project_tab.render()
