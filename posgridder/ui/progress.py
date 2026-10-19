"""The progress strip above the tabs: the workflow steps, the next one, and stale results."""
from __future__ import annotations

import streamlit as st

from posgridder.core.progress import next_step, stale, status
from posgridder.ui.state import project


def render() -> None:
    proj = project()
    steps = status(proj)
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        for s in steps:
            if s.done:
                st.badge(s.label, icon=":material/check:", color="green")
            else:
                st.badge(s.label, icon=":material/radio_button_unchecked:", color="gray")
        n = len(stale(proj))
        if n:
            st.badge(f"{n} stale", icon=":material/history:", color="orange")
    nxt = next_step(steps)
    if stale(proj):
        st.caption("Stale: made from inputs that have since changed; each shows a Recalculate "
                   "button where it is listed.")
    if nxt is not None:
        st.caption(f"Next: {nxt.hint}.")
    elif not stale(proj):
        st.caption("Every step is done. The prospect summary is on tab 7 POS & results.")
