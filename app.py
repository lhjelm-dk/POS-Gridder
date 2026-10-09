"""POS-Gridder — Streamlit shell.

The sidebar holds the project's layers; each tab is a module in ``posgridder/ui``. Tabs are
added phase by phase as set out in ``docs/PLAN.md``.
"""
from __future__ import annotations

import streamlit as st

from posgridder.ui import sidebar, surfaces_tab

st.set_page_config(page_title="POS-Gridder", page_icon=":material/layers:", layout="wide")

st.title("POS-Gridder")
st.caption("*by Lars Hjelm* · Surfaces, contours and gridded chance of success")

sidebar.render()

(surfaces,) = st.tabs(["1.0 Surfaces"])
with surfaces:
    surfaces_tab.render()
