"""The whole app, rendered through Streamlit's AppTest."""
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from posgridder.core.model import Project
from tests.conftest import add_grid, dome_values

pytestmark = pytest.mark.render

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _app(project: Project | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    if project is not None:
        at.session_state["project"] = project
    return at.run()


def _project() -> Project:
    p = Project()
    add_grid(p, dome_values(), domain="depth", name="top")
    add_grid(p, np.linspace(900, 1600, 21 * 31).reshape(21, 31), domain="time", name="twt")
    return p


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def _names(at) -> list[str]:
    proj = at.session_state["project"]
    return [proj.objects[u].name for u in proj.layers]


def test_empty_app_renders():
    at = _app()
    assert not at.exception
    assert any("no layers" in i.value.lower() for i in at.info)


def test_layers_map_and_lineage():
    at = _app(_project())
    assert not at.exception
    assert at.radio(key="active_layer").value == "top"
    assert len(at.get("plotly_chart")) == 1
    assert any("file top.dat" in c.value for c in at.code)


def test_copy_rename_delete():
    at = _app(_project())
    _button(at, "Copy").click().run()
    assert not at.exception
    assert at.radio(key="active_layer").value == "top copy"

    next(t for t in at.text_input if t.label == "Rename to").set_value("top again")
    _button(at, "Rename").click().run()
    assert not at.exception
    assert at.radio(key="active_layer").value == "top again"

    _button(at, "Delete").click().run()
    assert not at.exception
    assert _names(at) == ["top", "twt"]


def test_depth_conversion_through_the_form():
    at = _app(_project())
    _button(at, "Convert").click().run()
    assert not at.exception
    assert _names(at)[-1] == "twt depth"
    assert at.radio(key="active_layer").value == "twt depth"
    assert any("Made" in s.value for s in at.success)


def test_refused_arithmetic_is_reported():
    at = _app(_project())
    at.segmented_control(key="prepare_tool").set_value("Arithmetic").run()
    at.segmented_control(key="ar_op").set_value("add").run()
    selects = {s.label: s for s in at.selectbox}
    selects["A"].set_value("top")
    selects["B"].set_value("twt")
    _button(at, "Calculate").click().run()
    assert not at.exception
    assert any("not a defined combination" in e.value for e in at.error)
    assert _names(at) == ["top", "twt"]


def test_stale_layer_offers_recalculation():
    p = _project()
    at = _app(p)
    from posgridder.core.operations import apply
    top = p.by_name("top")
    thick = apply(p, "subtract", [top.uid, top.uid], name="zero")
    apply(p, "offset", [top.uid], {"constant": 5.0}, name="top", replace=True)
    at.session_state["_pending_active"] = thick.uid
    at.run()
    assert any("Stale" in w.value for w in at.warning)
    _button(at, "Recalculate from the newest inputs").click().run()
    assert not at.exception
    proj = at.session_state["project"]
    assert not proj.is_stale(proj.by_name("zero").uid)


def test_project_tab_replay():
    at = _app(_project())
    _button(at, "Run the replay check").click().run()
    assert not at.exception
    assert any("reproduce exactly" in s.value for s in at.success)
