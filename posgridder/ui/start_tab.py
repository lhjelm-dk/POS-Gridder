"""Tab 1 Start: begin a project, keep it, and audit it.

Starting comes first: reopen the autosaved project, load the example, open a project file, or
begin anew. Saving follows. The replay check and the full history — the audit trail — are
folded away below.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from posgridder.core.model import Project, ProjectError
from posgridder.core.operations import replay
from posgridder.io import autosave, project_file
from posgridder.io.examples import load_example
from posgridder.ui.state import notify, project, select


def _replace(loaded: Project, message: str) -> None:
    st.session_state["project"] = loaded
    st.session_state["_autosave_sig"] = autosave.signature(loaded)
    surfaces = loaded.current("surface")
    select(surfaces[0] if surfaces else None)
    notify("success", message)


def _reopen(save: dict) -> None:
    try:
        loaded = autosave.load(save["index"])
        _replace(loaded, f"Reopened the project autosaved {save['saved']:%Y-%m-%d %H:%M}: "
                         f"{len(loaded.layers)} objects.")
    except (ProjectError, OSError) as exc:
        notify("error", f"The autosaved project could not be opened: {exc}")
    st.rerun()


def _start() -> None:
    proj = project()
    st.subheader("Start", divider="gray")
    has_work = bool(proj.objects)
    saves = autosave.available()
    with st.container(horizontal=True):
        if saves:
            last = saves[0]
            if st.button("Reopen last project", type="primary", icon=":material/history:",
                         help=f"Autosaved {last['saved']:%Y-%m-%d %H:%M} "
                              f"({last['bytes'] / 1e6:.1f} MB): {last['path']}"):
                _reopen(last)
        if st.button("Load example project", icon=":material/science:",
                     help="A synthetic depth grid with two domes, a saddle and a data gap, "
                          "added to the current project like an imported file."):
            select(load_example(proj))
            notify("success", "Added the example depth surface.")
            st.rerun()
        if has_work and st.button("New empty project", icon=":material/note_add:",
                                  help="Discards the current project. It stays in the autosave "
                                       "until the next change is saved over it."):
            _replace(Project(), "Started an empty project.")
            st.rerun()
    if autosave.folder() is None:
        st.caption("Autosave is off (POSGRIDDER_AUTOSAVE=off).")
    else:
        st.caption(f"Every change is saved to {autosave.folder()}. The last {autosave.KEEP} "
                   "sessions are kept.")
    if len(saves) > 1:
        with st.expander("Earlier sessions", icon=":material/folder_special:"):
            for s in saves[1:]:
                if st.button(f"Reopen the session saved {s['saved']:%Y-%m-%d %H:%M} "
                             f"({s['bytes'] / 1e6:.1f} MB)", key=f"reopen_{s['index']}"):
                    _reopen(s)

    with st.form("open_project", clear_on_submit=True, border=False):
        upload = st.file_uploader("Open a project file", type=["zip"])
        confirm = st.checkbox("Replace the current project",
                              help="The current project is discarded; save it first if needed.")
        submitted = st.form_submit_button("Open", icon=":material/folder_open:")
    if submitted:
        if upload is None:
            notify("warning", "No project file was chosen.")
        elif project().objects and not confirm:
            notify("warning", "The current project holds objects; tick **Replace the current "
                              "project** to open another.")
        else:
            try:
                loaded = project_file.load(upload.getvalue())
            except ProjectError as exc:
                notify("error", str(exc))
            else:
                _replace(loaded, f"Opened {upload.name}: {len(loaded.layers)} objects, "
                                 f"{len(loaded.objects)} versions, {len(loaded.sources)} "
                                 "source files.")
        st.rerun()


def _save() -> None:
    proj = project()
    st.subheader("Save", divider="gray")
    if not proj.objects:
        st.caption("Nothing to save yet.")
        return
    st.write("The project file holds the imported files byte for byte, every version and every "
             "derivation, so the project reopens exactly and every result can be recomputed.")
    st.download_button("Download project file", data=project_file.save(proj),
                       file_name="project.posgrid.zip", mime="application/zip",
                       icon=":material/save:", on_click="ignore")


def _replay() -> None:
    proj = project()
    st.markdown("Replay check: every version is recomputed from the source files and compared "
                "with what the project holds.")
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
    if not proj.objects:
        st.caption("The history is empty.")
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


def render() -> None:
    _start()
    _save()
    with st.expander("Audit: replay check and history", icon=":material/fact_check:"):
        _replay()
        _history()
