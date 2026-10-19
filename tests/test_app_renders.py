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
    assert any("no surfaces" in i.value.lower() for i in at.info)


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
    at.segmented_control(key="surface_view").set_value("Depth conversion").run()
    _button(at, "Convert").click().run()
    assert not at.exception
    assert _names(at)[-1] == "twt depth"
    assert at.radio(key="active_layer").value == "twt depth"
    assert any("Made" in s.value for s in at.success)


def test_refused_arithmetic_is_reported():
    at = _app(_project())
    at.segmented_control(key="surface_view").set_value("Arithmetic").run()
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


def test_closure_and_volumes_workflow():
    """Load the example, confirm the proposed closure, calculate volumes, see the exports."""
    at = _app()
    _button(at, "Load example project").click().run()
    assert not at.exception
    assert at.dataframe                                   # candidate table is shown
    _button(at, "Confirm this interpretation").click().run()
    assert not at.exception
    proj = at.session_state["project"]
    assert len(proj.current("closure")) == 1
    assert any("Confirmed" in s.value for s in at.success)
    calc = [b for b in at.button if b.label == "Calculate"]
    calc[-1].click().run()                                # the volumes form's button
    assert not at.exception
    assert len(proj.current("volumes")) == 1
    labels = [b.label for b in at.get("download_button")]
    assert "HCWC Builder area–depth (CSV)" in labels


UNIFORM = "\n".join(f"{p}\t{2080 + 1.6 * (100 - p):.2f}" for p in range(100, -1, -1))


def test_hcwc_and_pos_workflow():
    """Example → closure → volumes → pasted table → POS map (event a) → GRV by percentile."""
    at = _app()
    _button(at, "Load example project").click().run()
    _button(at, "Confirm this interpretation").click().run()
    [b for b in at.button if b.label == "Calculate"][-1].click().run()
    assert not at.exception
    paste = next(t for t in at.text_area if t.label.startswith("Percentile and depth"))
    paste.set_value(UNIFORM)
    at.selectbox(key="paste_basis").set_value("geological")
    at.selectbox(key="paste_cond").set_value("h_min")
    at.selectbox(key="paste_tails").set_value("raw")
    at.number_input(key="paste_pg").set_value(0.35)
    at.number_input(key="paste_f").set_value(0.8)
    _button(at, "Add table").click().run()
    assert not at.exception, at.exception
    proj = at.session_state["project"]
    assert len(proj.current("hcwc")) == 1

    next(r for r in at.radio if r.label == "Event").set_value("a")
    _button(at, "Map POS").click().run()
    assert not at.exception, at.exception
    (m,) = [proj.objects[u] for u in proj.current("posmap")]
    assert m.summary["pos_at_crest"] == pytest.approx(0.35 * 0.8)
    assert any(d.label == "POS grid (ZMAP+)" for d in at.get("download_button"))

    at.segmented_control(key="results_section").set_value("Area and GRV by percentile").run()
    _button(at, "Evaluate").click().run()
    assert not at.exception, at.exception
    (pv,) = [proj.objects[u] for u in proj.current("pctvol")]
    assert pv.summary["grv_P10_1e6m3"] > pv.summary["grv_P90_1e6m3"] > 0


def test_contour_workflow():
    """Example → contour → select (as the map would) and delete → surface from the contours."""
    at = _app()
    _button(at, "Load example project").click().run()
    _button(at, "Contour").click().run()
    assert not at.exception, at.exception
    proj = at.session_state["project"]
    (cs_uid,) = proj.current("contours")
    at.session_state["contour_selection"] = {cs_uid: [0, 1]}
    at.run()
    assert at.segmented_control(key="contour_step").value == "Edit"   # straight to editing
    _button(at, "Delete selected").click().run()
    assert not at.exception, at.exception
    (new_uid,) = proj.current("contours")
    assert new_uid != cs_uid and proj.objects[new_uid].deleted[:2].all()
    at.segmented_control(key="contour_step").set_value("Make surface").run()
    _button(at, "Make surface").click().run()
    assert not at.exception, at.exception
    made = proj.objects[proj.current("surface")[-1]]
    assert made.derivation.operation == "contours_to_surface"
    assert made.derivation.params["method"] == "tps"



def test_scale_pickers_on_every_map():
    """Data, closure and contour maps each offer the ten scales; the choice reaches the figure."""
    at = _app()
    _button(at, "Load example project").click().run()
    _button(at, "Contour").click().run()
    assert not at.exception, at.exception
    for key in ("data_map_scale", "closure_map_scale", "contour_map_scale"):
        box = at.selectbox(key=key)
        assert len(box.options) == 10 and box.value == "Viridis"
        box.set_value("Cividis").run()
        assert not at.exception, at.exception
    at.segmented_control(key="contour_lines").set_value("Black").run()
    at.toggle(key="closure_map_reverse").set_value(True).run()
    assert not at.exception, at.exception



def test_autosave_reopen_and_rotation(tmp_path):
    """Every change is autosaved; a new session keeps the last one and can reopen it."""
    from posgridder.io import autosave

    at = _app()
    _button(at, "Load example project").click().run()
    assert not at.exception, at.exception
    saves = autosave.available()
    assert [s["index"] for s in saves] == [0]
    first = autosave.load(0)
    assert len(first.current("surface")) == 1

    # A second session: its first change moves the first session's file aside.
    at2 = _app()
    _button(at2, "Load example project").click().run()
    _button(at2, "Load example project").click().run()
    assert [s["index"] for s in autosave.available()] == [0, 1]
    assert len(autosave.load(1).current("surface")) == 1
    assert len(autosave.load(0).current("surface")) == 2

    # A third session reopens the latest without writing anything new.
    at3 = _app()
    _button(at3, "Reopen last project").click().run()
    assert not at3.exception, at3.exception
    assert len(at3.session_state["project"].current("surface")) == 2
    assert [s["index"] for s in autosave.available()] == [0, 1]


def test_autosave_off(monkeypatch):
    from posgridder.io import autosave

    monkeypatch.setenv("POSGRIDDER_AUTOSAVE", "off")
    at = _app()
    _button(at, "Load example project").click().run()
    assert not at.exception
    assert autosave.available() == []
    assert any("Autosave is off" in c.value for c in at.caption)


def test_pos_map_on_structure_contours():
    """The result map draws the depth contours, the spill contour and the crest over POS."""
    p = Project()
    from tests.test_pos import dome, table_dist
    top, closure = dome(p)
    dist = table_dist(p, 2100, 2200, p_g=0.3, h_min=50.0, apex=2000.0)
    from posgridder.core.operations import apply
    apply(p, "pos_map", [closure.uid, top.uid, dist.uid],
          {"roles": ["closure", "top", "hcwc"], "event": "b"}, name="m")
    at = _app(p)
    assert not at.exception, at.exception
    from posgridder.plotting.maps import pos_figure
    m = p.objects[p.current("posmap")[0]]
    fig = pos_figure(m, structure=top, closure=closure)
    names = [t.name for t in fig.data]
    assert any(n and n.startswith("Spill") for n in names)
    assert any(n and n.startswith("Crest") for n in names)
    assert sum(1 for t in fig.data if t.type == "contour") >= 3
