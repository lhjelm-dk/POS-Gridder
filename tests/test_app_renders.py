"""The whole app, rendered through Streamlit's AppTest."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from posgridder.core.model import Project

pytestmark = pytest.mark.render

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _app_with(*surfaces) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    if surfaces:
        project = Project()
        for s in surfaces:
            project.add(s)
        at.session_state["project"] = project
    return at.run()


def test_empty_app_renders():
    at = _app_with()
    assert not at.exception
    assert any("no surfaces" in i.value.lower() for i in at.info)


def test_app_with_a_surface(dome):
    at = _app_with(dome)
    assert not at.exception
    assert at.radio(key="active_surface").value == "dome"
    assert len(at.get("plotly_chart")) == 1


def test_copy_rename_delete(dome):
    at = _app_with(dome)
    next(b for b in at.button if b.label == "Copy").click().run()
    assert not at.exception
    assert at.radio(key="active_surface").value == "dome copy"

    at.text_input[0].set_value("top gassum")
    next(b for b in at.button if b.label == "Rename").click().run()
    assert not at.exception
    assert at.radio(key="active_surface").value == "top gassum"

    next(b for b in at.button if b.label == "Delete").click().run()
    assert not at.exception
    assert list(at.session_state["project"].surfaces) == ["dome"]
