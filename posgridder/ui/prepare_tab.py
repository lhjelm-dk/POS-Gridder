"""Tab 2.0 Prepare: depth conversion, arithmetic and resampling.

Each tool makes a new layer through a recorded operation. The single-surface tools (scale,
offset, clip, smooth) can instead replace their input as a new version of the same layer; the
earlier version stays in the history and layers made from it are marked stale.
"""
from __future__ import annotations

import streamlit as st

from posgridder.core.model import ProjectError
from posgridder.core.operations import apply, result_domain
from posgridder.ui.state import active, notify, project, select, uid_of

TOOLS = ["Depth conversion", "Arithmetic", "Resample"]
ARITHMETIC = {
    "subtract": "A − B",
    "add": "A + B",
    "scale": "A × k",
    "offset": "A + k",
    "clip": "Clip to a range",
    "smooth": "Smooth (3 × 3 mean)",
}


def _layers(domains: tuple[str, ...] | None = None) -> list[str]:
    """Layer names, optionally of some domains. Names are unique among current layers."""
    proj = project()
    return [proj.objects[u].name for u in proj.current("surface")
            if domains is None or proj.objects[u].domain in domains]


def _default_index(options: list[str]) -> int | None:
    uid = active()
    name = project().objects[uid].name if uid else None
    return options.index(name) if name in options else (0 if options else None)


def _run(op: str, inputs: list[str], params: dict, name: str, replace: bool = False) -> None:
    try:
        surface = apply(project(), op, inputs, params, name=name, replace=replace)
    except ProjectError as exc:
        notify("error", str(exc))
    else:
        select(surface.uid)
        verb = "Replaced with a new version:" if replace else "Made"
        notify("success", f"{verb} **{surface.name}** ({surface.domain}).")
        for w in surface.warnings:
            notify("warning", f"{surface.name}: {w}")
    st.rerun()


def _depth_conversion() -> None:
    times = _layers(("time",))
    if not times:
        st.info("Depth conversion needs a layer imported with the domain **time** (TWT in ms, "
                "positive down).", icon=":material/info:")
        return
    method = st.segmented_control("Method", ["Constant velocity", "Velocity surface", "V0 + kZ"],
                                  default="Constant velocity", key="dc_method") or "Constant velocity"
    velocities = _layers(("velocity",))
    with st.form("depth_conversion", border=False):
        time_name = st.selectbox("Time surface", times, index=_default_index(times))
        if method == "Constant velocity":
            v = st.number_input("Average velocity (m/s)", min_value=1.0, value=2500.0, step=50.0)
            params = {"method": "constant", "velocity": v}
            extra: list[str] = []
        elif method == "Velocity surface":
            vel_name = st.selectbox("Average-velocity surface", velocities,
                                    index=0 if velocities else None,
                                    placeholder="No velocity layer in the project")
            params = {"method": "velocity_grid"}
            extra = [uid_of(vel_name)] if vel_name else []
        else:
            c1, c2 = st.columns(2)
            v0 = c1.number_input("V0 (m/s)", min_value=1.0, value=1800.0, step=50.0,
                                 help="Instantaneous velocity at the datum (MSL).")
            k = c2.number_input("k (1/s)", min_value=0.0, value=0.5, step=0.05, format="%.3f",
                                help="Velocity gradient with depth; 0 gives a constant velocity.")
            params = {"method": "v0k", "v0": v0, "k": k}
            extra = []
        name = st.text_input("New layer name", placeholder="Default: the time layer's name + depth")
        submitted = st.form_submit_button("Convert", icon=":material/swap_vert:")
    st.caption("One-way time t = TWT / 2000 s; depth positive down from MSL. Constant: z = V·t. "
               "Velocity surface: z = V(x, y)·t. V0 + kZ: z = (V0/k)(e^(k·t) − 1). No water layer "
               "and no well tie are applied.")
    if submitted:
        if method == "Velocity surface" and not extra:
            notify("error", "A velocity surface is needed: import one with the domain velocity.")
            st.rerun()
        _run("depth_convert", [uid_of(time_name), *extra], params,
             name.strip() or f"{time_name} depth")


def _arithmetic() -> None:
    op = st.segmented_control("Operation", list(ARITHMETIC), format_func=ARITHMETIC.get,
                              default="subtract", key="ar_op") or "subtract"
    layers = _layers()
    if not layers:
        st.info("The project holds no layers.", icon=":material/info:")
        return
    proj = project()
    with st.form("arithmetic", border=False):
        a = st.selectbox("A", layers, index=_default_index(layers))
        params: dict = {}
        inputs = [a]
        if op in ("subtract", "add"):
            b = st.selectbox("B", layers, index=min(1, len(layers) - 1))
            inputs.append(b)
        elif op == "scale":
            params["factor"] = st.number_input("k", value=1.0, format="%.6g")
        elif op == "offset":
            params["constant"] = st.number_input("k", value=0.0, format="%.6g",
                                                 help="In the layer's own unit.")
        elif op == "clip":
            c1, c2 = st.columns(2)
            lo = c1.number_input("Minimum", value=None, format="%.6g", placeholder="none")
            hi = c2.number_input("Maximum", value=None, format="%.6g", placeholder="none")
            params = {"min": lo, "max": hi}
        else:
            params["passes"] = st.number_input("Passes", min_value=1, max_value=50, value=1)
        replace = False
        if op not in ("subtract", "add"):
            replace = st.checkbox("Replace A with the result",
                                  help="The result becomes a new version of A's layer. The "
                                       "earlier version stays in the history, and layers made "
                                       "from it are marked stale.")
        name = st.text_input("New layer name", placeholder="Default: describes the operation")
        submitted = st.form_submit_button("Calculate", icon=":material/calculate:")
    st.caption("A ± B is defined for depth − depth → thickness, depth ± thickness → depth, "
               "thickness ± thickness → thickness and other ± other → other. Both layers must "
               "share their nodes; otherwise one is resampled first. Nulls stay null.")
    if submitted:
        uids = [uid_of(n) for n in inputs]
        if op in ("subtract", "add"):
            try:
                result_domain(op, proj.objects[uids[0]].domain, proj.objects[uids[1]].domain)
            except ProjectError as exc:
                notify("error", str(exc))
                st.rerun()
            sign = "−" if op == "subtract" else "+"
            default = f"{inputs[0]} {sign} {inputs[1]}"
        else:
            default = a if replace else f"{a} {op}"
        _run(op, uids, params, name.strip() or default, replace=replace)


def _resample() -> None:
    layers = _layers()
    if len(layers) < 2:
        st.info("Resampling needs two layers: the one to resample and one whose nodes it takes.",
                icon=":material/info:")
        return
    with st.form("resample", border=False):
        src = st.selectbox("Layer to resample", layers, index=_default_index(layers))
        target = st.selectbox("Onto the nodes of", layers, index=min(1, len(layers) - 1))
        method = st.segmented_control("Method", ["bilinear", "nearest"], default="bilinear")
        name = st.text_input("New layer name", placeholder="Default: name + resampled")
        submitted = st.form_submit_button("Resample", icon=":material/grid_on:")
    st.caption("Bilinear needs all four surrounding source nodes valid; nearest takes the "
               "nearest node. Target nodes outside the source are null. The target's values "
               "are not used.")
    if submitted:
        if src == target:
            notify("error", "A layer cannot be resampled onto itself.")
            st.rerun()
        _run("resample", [uid_of(src), uid_of(target)], {"method": method or "bilinear"},
             name.strip() or f"{src} resampled")


def render() -> None:
    tool = st.segmented_control("Tool", TOOLS, default=TOOLS[0], key="prepare_tool",
                                label_visibility="collapsed") or TOOLS[0]
    with st.container(border=True):
        if tool == "Depth conversion":
            _depth_conversion()
        elif tool == "Arithmetic":
            _arithmetic()
        elif tool == "Resample":
            _resample()
