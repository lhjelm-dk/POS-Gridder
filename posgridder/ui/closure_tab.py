"""Tab 3.0 Closure: candidate crests and spills, then a confirmed interpretation.

Nothing here is accepted by default. The tool proposes crests (with their conservative spill)
and, for the chosen crest, every depth at which the fill reaches a boundary or a saddle. The
interpreter chooses the spill, accepts or not each boundary passed on the way, and confirms. The
confirmation is a recorded operation; volumes are only computed on confirmed closures.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from posgridder.core.closure import (BOUNDARY_TYPES, crest_candidates, fill_depth, footprint_at,
                                     nearest_node, spill_events)
from posgridder.core.model import ProjectError
from posgridder.core.operations import apply, recalculate
from posgridder.plotting.maps import (SERIES, add_footprint, add_point, node_xy,
                                      surface_figure)
from posgridder.ui.state import notify, project, uid_of


def _cached(key: tuple, compute):
    """A per-session cache keyed by surface uid and parameters (objects are immutable)."""
    cache = st.session_state.setdefault("_closure_cache", {})
    if key not in cache:
        if len(cache) > 32:
            cache.clear()
        cache[key] = compute()
    return cache[key]


def _candidates_section(surface, connectivity: int, min_height: float):
    cands = _cached(("cands", surface.uid, connectivity, min_height),
                    lambda: crest_candidates(surface, connectivity=connectivity,
                                             min_height=min_height))
    st.subheader("Candidate crests", divider="gray")
    st.caption("Each culmination with its conservative spill: every boundary (model edge, data "
               "limit, interior null) treated as a leak. Tallest first.")
    if not cands:
        st.info(f"No culmination closes by {min_height:g} m or more.", icon=":material/info:")
    frame = pd.DataFrame([{
        "Crest (m)": round(c.crest_depth, 1), "Spill (m)": round(c.spill_depth, 1),
        "Height (m)": round(c.height, 1), "Spill reaches": c.spill_type, "Nodes": c.nodes_at_spill,
        "X": round(node_xy(surface, c.node)[0]), "Y": round(node_xy(surface, c.node)[1]),
    } for c in cands])
    event = st.dataframe(frame, hide_index=True, on_select="rerun", selection_mode="single-row",
                         key=f"cand_table_{surface.uid}")
    rows = event.selection.rows if event else []
    with st.expander("Crest at given coordinates", icon=":material/my_location:"):
        c1, c2 = st.columns(2)
        x = c1.number_input("X (m)", value=None, format="%.1f", key="crest_x")
        y = c2.number_input("Y (m)", value=None, format="%.1f", key="crest_y")
    if x is not None and y is not None:
        try:
            node = nearest_node(surface, x, y)
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
            return None
        if np.ma.getmaskarray(surface.values)[node]:
            st.error("The nearest node is null.", icon=":material/error:")
            return None
        return node
    if rows:
        return cands[rows[0]].node
    return cands[0].node if cands else None


def _interpretation(surface, crest, connectivity: int, min_height: float) -> None:
    fill = _cached(("fill", surface.uid, crest, connectivity),
                   lambda: fill_depth(surface, crest, connectivity))
    events = _cached(("events", surface.uid, crest, connectivity, min_height),
                     lambda: spill_events(surface, fill, crest, connectivity=connectivity,
                                          min_height=min_height))
    z_crest = float(surface.values[crest])
    st.subheader(f"Spill from the crest at {z_crest:.1f} m", divider="gray")
    st.caption("The depths at which the fill from this crest first reaches each boundary and "
               "the saddle towards each other culmination. These are candidates; the choice is "
               "the interpreter's.")
    st.dataframe(pd.DataFrame([{"#": k, "Depth (m)": round(e.level, 2), "Reaches": e.type,
                                "Detail": e.detail} for k, e in enumerate(events)]),
                 hide_index=True)

    options = list(range(len(events))) + ["manual"]
    labels = {k: f"#{k}: {e.type} at {e.level:.1f} m" for k, e in enumerate(events)}
    labels["manual"] = "Manual spill depth"
    pick = st.radio("Spill", options, format_func=labels.get, key=f"spill_pick_{surface.uid}",
                    horizontal=True)
    choice: dict = {}
    if pick == "manual":
        c1, c2 = st.columns([1, 2])
        spill = c1.number_input("Spill depth (m)", value=float(round(events[0].level, 1))
                                if events else z_crest + 10, format="%.1f", key="manual_spill")
        reason = c2.text_input("Reason", placeholder="e.g. fault-dependent closure, fault seal "
                                                     "assumed at 2310 m", key="manual_reason")
        choice = {"manual": spill, "reason": reason}
    else:
        spill = events[pick].level
        choice = {"event": int(pick)}

    passed = [e for e in events if e.type in BOUNDARY_TYPES and e.level < spill]
    accept: list[str] = []
    for e in passed:
        if st.checkbox(f"Accept that the closure continues past the {e.type} at {e.level:.1f} m "
                       "(unverified)", key=f"accept_{e.type}"):
            accept.append(e.type)
    if accept:
        choice["accept"] = sorted(set(accept))

    footprint = footprint_at(surface, fill, spill) if spill > z_crest else None
    fig = surface_figure(surface, height=560)
    if footprint is not None and footprint.any():
        add_footprint(fig, surface, footprint, name=f"Footprint at {spill:.1f} m")
    cx, cy = node_xy(surface, crest)
    add_point(fig, cx, cy, name="Crest", text=f"Crest {z_crest:.1f} m")
    if pick != "manual":
        sx, sy = node_xy(surface, events[pick].node)
        add_point(fig, sx, sy, name="Spill", text=f"{events[pick].type} {spill:.1f} m",
                  symbol="x", color=SERIES[1])
    st.plotly_chart(fig, key="closure_preview")
    if footprint is not None:
        area = footprint.sum() * surface.xinc * surface.yinc / 1e6
        st.caption(f"Preview: {int(footprint.sum()):,} nodes, about {area:.2f} km² by node count; "
                   "tab **4.0 Volumes** measures areas on contoured polygons.")

    unaccepted = [e for e in passed if e.type not in accept]
    with st.form("confirm_closure", border=False):
        default = f"{surface.name} closure {z_crest:.0f}–{spill:.0f} m"
        name = st.text_input("Name", value=default)
        confirmed = st.form_submit_button("Confirm this interpretation", type="primary",
                                          icon=":material/verified:",
                                          disabled=bool(unaccepted))
    if unaccepted:
        st.caption("The chosen spill lies deeper than a boundary the fill passes on the way; "
                   "accepting it, or choosing a shallower spill, is needed first.")
    if confirmed:
        params = {"crest": [int(crest[0]), int(crest[1])], "connectivity": connectivity,
                  "min_height": min_height, "choice": choice}
        try:
            closure = apply(project(), "closure", [surface.uid], params, name=name)
        except ProjectError as exc:
            notify("error", str(exc))
        else:
            notify("success", f"Confirmed **{closure.name}**: crest {closure.crest_depth:.1f} m, "
                              f"spill {closure.spill_depth:.1f} m ({closure.spill_type}).")
        st.rerun()


def _confirmed_section() -> None:
    proj = project()
    uids = proj.current("closure")
    st.subheader("Confirmed closures", divider="gray")
    if not uids:
        st.caption("None yet.")
        return
    rows = []
    for u in uids:
        c = proj.objects[u]
        rows.append({"Name": c.name, "Surface": proj.objects[c.surface_uid].name
                     if c.surface_uid in proj.objects else "?",
                     "Crest (m)": round(c.crest_depth, 1), "Spill (m)": round(c.spill_depth, 1),
                     "Spill type": c.spill_type, "Height (m)": round(c.height, 1),
                     "Nodes": c.n_nodes, "Status": "stale" if proj.is_stale(u) else "current"})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    name = st.selectbox("Closure", [proj.objects[u].name for u in uids], key="closure_view")
    c = proj.objects[uid_of(name)]
    for reason in proj.stale_reasons(c.uid):
        st.warning(f"**Stale.** {reason}.", icon=":material/history:")
    with st.container(horizontal=True):
        if proj.is_stale(c.uid) and st.button("Recalculate", icon=":material/refresh:",
                                              key="closure_recalc"):
            try:
                recalculate(proj, c.uid)
                notify("success", "Recalculated as a new version.")
            except ProjectError as exc:
                notify("error", str(exc))
            st.rerun()
        if st.button("Remove", icon=":material/delete:", key="closure_remove"):
            proj.remove(c.uid)
            st.rerun()
    st.markdown("**Assumptions**\n" + "\n".join(f"- {a}" for a in c.assumptions))
    for w in c.warnings:
        st.warning(w, icon=":material/warning:")


def render() -> None:
    proj = project()
    depths = [proj.objects[u].name for u in proj.current("surface")
              if proj.objects[u].domain == "depth"]
    if not depths:
        st.info("Closure analysis needs a depth surface. A time surface is converted on tab "
                "**2.0 Prepare**.", icon=":material/info:")
        _confirmed_section()
        return
    with st.container(horizontal=True, vertical_alignment="bottom"):
        name = st.selectbox("Depth surface", depths, key="closure_surface", width=320)
        connectivity = st.segmented_control("Connectivity", [8, 4], default=8,
                                            key="closure_conn",
                                            help="8: a saddle through a cell corner counts. 4 "
                                                 "can report a closure the fill would leak "
                                                 "out of diagonally.") or 8
        min_height = st.number_input("Minimum closure height (m)", min_value=0.0, value=5.0,
                                     step=1.0, key="closure_min_h", width=220)
    surface = proj.objects[uid_of(name)]
    crest = _candidates_section(surface, int(connectivity), float(min_height))
    if crest is not None:
        _interpretation(surface, crest, int(connectivity), float(min_height))
    _confirmed_section()
