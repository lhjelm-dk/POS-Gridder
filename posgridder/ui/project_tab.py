"""Tab 7.0 Project: save, load, the replay check and the full history."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from posgridder.core.model import ProjectError
from posgridder.core.operations import replay
from posgridder.io import project_file
from posgridder.io.examples import load_example
from posgridder.ui.state import notify, project, select


def _save() -> None:
    proj = project()
    st.subheader("Save", divider="gray")
    st.write("The project file holds the imported files byte for byte, every layer version and "
             "every derivation, so the project reopens exactly and every layer can be recomputed.")
    if not proj.objects:
        st.caption("Nothing to save yet.")
        return
    st.download_button("Download project file", data=project_file.save(proj),
                       file_name="project.posgrid.zip", mime="application/zip",
                       icon=":material/save:", on_click="ignore")


def _load() -> None:
    st.subheader("Open", divider="gray")
    with st.form("open_project", clear_on_submit=True, border=False):
        upload = st.file_uploader("Project file", type=["zip"])
        confirm = st.checkbox("Replace the current project",
                              help="The current project is discarded; save it first if needed.")
        submitted = st.form_submit_button("Open", icon=":material/folder_open:")
    if submitted:
        if upload is None:
            notify("warning", "No project file was chosen.")
        elif project().objects and not confirm:
            notify("warning", "The current project holds layers; tick **Replace the current "
                              "project** to open another.")
        else:
            try:
                loaded = project_file.load(upload.getvalue())
            except ProjectError as exc:
                notify("error", str(exc))
            else:
                st.session_state["project"] = loaded
                select(loaded.layers[0] if loaded.layers else None)
                notify("success", f"Opened {upload.name}: {len(loaded.layers)} objects, "
                                  f"{len(loaded.objects)} versions, {len(loaded.sources)} source files.")
        st.rerun()


def _replay() -> None:
    proj = project()
    st.subheader("Replay check", divider="gray")
    st.write("Recomputes every layer version from the source files and compares it, node by "
             "node, with what the project holds.")
    if st.button("Run the replay check", icon=":material/fact_check:", disabled=not proj.objects):
        try:
            with st.spinner("Recomputing every object from the source files…"):
                rows = replay(proj)
        except ProjectError as exc:
            st.error(f"The replay stopped: {exc}", icon=":material/error:")
            return
        from posgridder import __version__

        frame = pd.DataFrame([{"Object": r.name, "Operation": r.operation,
                               "Identical": r.identical, "Made by version": r.made_by}
                              for r in rows])
        if frame["Identical"].all():
            st.success(f"All {len(rows)} versions reproduce exactly.", icon=":material/check_circle:")
        else:
            older = frame[~frame["Identical"] & (frame["Made by version"] != __version__)]
            st.error(f"{(~frame['Identical']).sum()} of {len(rows)} versions differ.",
                     icon=":material/error:")
            if len(older) == (~frame["Identical"]).sum():
                st.caption(f"Every difference is in an object made by an earlier version than "
                           f"this one ({__version__}); the calculation or its recorded text has "
                           "changed since. Recalculating such an object makes it current.")
        st.dataframe(frame, hide_index=True)


def _history() -> None:
    proj = project()
    st.subheader("History", divider="gray")
    if not proj.objects:
        st.caption("Empty.")
        return
    current = set(proj.layers)
    rows = []
    for uid, obj in proj.objects.items():
        status = ("stale" if proj.is_stale(uid) else "current") if uid in current else (
            "superseded" if proj.successor(uid) else "history (input)")
        rows.append({"Name": obj.name, "Kind": obj.kind,
                     "Domain": getattr(obj, "domain", ""), "Status": status,
                     "Made by": obj.derivation.describe(), "Created (UTC)": obj.derivation.created,
                     "Id": uid[:12]})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    if proj.sources:
        st.dataframe(pd.DataFrame([{"File": s.filename, "Bytes": s.size, "SHA-256": s.sha256,
                                    "Imported (UTC)": s.imported}
                                   for s in proj.sources.values()]), hide_index=True)


def _example() -> None:
    st.subheader("Example", divider="gray")
    st.write("A synthetic depth grid with two domes, a saddle and a data gap, for trying the "
             "workflow. It is added to the current project like an imported file.")
    if st.button("Load example project", icon=":material/science:"):
        select(load_example(project()))
        notify("success", "Added the example depth surface.")
        st.rerun()


def render() -> None:
    left, right = st.columns(2)
    with left:
        _save()
    with right:
        _load()
    _replay()
    _history()
    _example()
