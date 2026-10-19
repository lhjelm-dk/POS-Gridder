"""Autosave: the current project written to a local file whenever it changes.

The folder is ``~/.pos-gridder/`` (the user's own folder, outside the repository), or the folder
in the environment variable ``POSGRIDDER_AUTOSAVE``; the value ``off`` switches autosave off.
Each file is a complete project file, imported files included, as **Download project file**
writes it.

The current session writes ``autosave.posgrid.zip`` and overwrites it on every change. Its first
write moves the file a previous session left there to ``autosave-1`` (and ``-1`` to ``-2``), so a
session that starts without reopening its predecessor cannot overwrite it: the last three
sessions can always be reopened from the Start tab.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from posgridder.core.model import Project
from posgridder.io import project_file

ENV = "POSGRIDDER_AUTOSAVE"
KEEP = 3


def hosted() -> bool:
    """True on Streamlit Community Cloud, which runs every app from ``/mount/src``.

    There one container serves every visitor, so a shared autosave folder would hand one user's
    project to the next. Autosave is therefore off on a hosted server unless the environment
    variable names a folder explicitly.
    """
    return (str(Path(__file__).resolve()).startswith("/mount/src")
            or os.environ.get("HOME") == "/home/appuser")


def off_reason() -> str | None:
    """Why autosave is off, in words for the Start tab; None when it is on."""
    value = os.environ.get(ENV, "").strip()
    if value.lower() == "off":
        return f"Autosave is off ({ENV}=off)."
    if not value and hosted():
        return ("Autosave is off on a hosted server, where one folder would be shared by every "
                "visitor. Download the project file on this tab to keep the work.")
    return None


def folder() -> Path | None:
    if off_reason() is not None:
        return None
    value = os.environ.get(ENV, "").strip()
    return Path(value) if value else Path.home() / ".pos-gridder"


def _file(k: int) -> Path:
    name = "autosave.posgrid.zip" if k == 0 else f"autosave-{k}.posgrid.zip"
    return folder() / name


def signature(project: Project) -> tuple:
    """Changes whenever an object is added, replaced, removed or renamed."""
    return (tuple(project.layers),
            tuple((uid, obj.name) for uid, obj in project.objects.items()))


def save_if_changed(project: Project, last: tuple | None,
                    first_in_session: bool) -> tuple[tuple, bool]:
    """Write the project when its signature differs from ``last``.

    Returns the signature and whether a file was written. ``first_in_session`` — no write yet
    in this session — rotates the earlier sessions' files before writing.
    """
    sig = signature(project)
    if folder() is None or not project.objects or sig == last:
        return sig, False
    folder().mkdir(parents=True, exist_ok=True)
    if first_in_session:
        for k in range(KEEP - 1, 0, -1):
            if _file(k - 1).exists():
                _file(k - 1).replace(_file(k))
    tmp = _file(0).with_suffix(".tmp")
    tmp.write_bytes(project_file.save(project))
    tmp.replace(_file(0))                      # never leave a half-written file behind
    return sig, True


def available() -> list[dict]:
    """The autosaves on disk, newest first: index, path, time written, size."""
    if folder() is None:
        return []
    out = []
    for k in range(KEEP):
        f = _file(k)
        if f.exists():
            stat = f.stat()
            out.append({"index": k, "path": f, "saved": datetime.fromtimestamp(stat.st_mtime),
                        "bytes": stat.st_size})
    return out


def load(index: int = 0) -> Project:
    f = _file(index) if folder() is not None else None
    if f is None or not f.exists():
        raise FileNotFoundError("no autosaved project")
    return project_file.load(f.read_bytes())
