"""The immutable model: sources, versions, staleness, names (plan §6.2, T23)."""
import numpy as np
import pytest

from posgridder.core.model import Derivation, Project, ProjectError, Surface, new_uid
from posgridder.core.operations import OperationError, apply, recalculate
from tests.conftest import add_grid, dome_values


def test_geometry(dome):
    assert (dome.nrow, dome.ncol) == (21, 31)
    assert dome.xmax == pytest.approx(dome.xori + 3000)
    assert dome.ymax == pytest.approx(dome.yori + 2000)
    assert dome.n_valid == 21 * 31 - 20
    assert dome.unit == "m"


def test_values_are_read_only(dome):
    with pytest.raises(ValueError):
        dome.values[5, 5] = -1.0
    with pytest.raises((AttributeError, TypeError)):
        dome.name = "other"


def test_nan_becomes_masked():
    s = Surface(new_uid(), "s", 0, 0, 1, 1, np.array([[1.0, np.nan], [3.0, 4.0]]), "other",
                Derivation.make("test", []))
    assert s.values.mask.tolist() == [[False, True], [False, False]]


def test_rejects_bad_input():
    d = Derivation.make("test", [])
    with pytest.raises(ValueError):
        Surface(new_uid(), "s", 0, 0, 1, 1, np.ones(5), "other", d)
    with pytest.raises(ValueError):
        Surface(new_uid(), "s", 0, 0, -1, 1, np.ones((2, 2)), "other", d)
    with pytest.raises(ValueError):
        Surface(new_uid(), "s", 0, 0, 1, 1, np.ones((2, 2)), "colour", d)


def test_content_hash_tracks_values(project, dome):
    twin = apply(project, "copy", [dome.uid], name="twin")
    assert twin.content_hash == dome.content_hash
    shifted = apply(project, "offset", [dome.uid], {"constant": 1e-6}, name="shifted")
    assert shifted.content_hash != dome.content_hash


def test_source_is_recorded(project, dome):
    (source,) = project.sources.values()
    assert dome.derivation.inputs == (source.uid,)
    assert len(source.sha256) == 64 and source.size > 0
    with pytest.raises(ProjectError):
        project.add_source(source, b"tampered")


def test_unique_names_rename_copy_remove(project, dome):
    copy = apply(project, "copy", [dome.uid], name="dome")
    assert copy.name == "dome (2)"
    renamed = project.rename(copy.uid, "base")
    assert renamed.uid == copy.uid and renamed.name == "base"
    assert project.rename(copy.uid, "dome").name == "dome (2)"
    assert [project.objects[u].name for u in project.layers] == ["dome", "dome (2)"]
    project.remove(copy.uid)
    assert project.layers == [dome.uid]
    assert copy.uid not in project.objects                 # nothing needed it: pruned


def test_removed_input_stays_as_history(project, dome):
    thick = apply(project, "subtract", [dome.uid, dome.uid], name="zero")
    project.remove(dome.uid)
    assert dome.uid in project.objects                     # still needed by 'zero'
    assert project.layers == [thick.uid]


def test_replace_supersedes_and_marks_dependents_stale(project, dome):
    """T23: editing an input marks every dependent stale and recalculates nothing."""
    base = apply(project, "offset", [dome.uid], {"constant": 50.0}, name="base")
    thick = apply(project, "subtract", [base.uid, dome.uid], name="thick")
    total = apply(project, "add", [dome.uid, thick.uid], name="again base")
    assert not project.is_stale(thick.uid)

    smooth = apply(project, "smooth", [dome.uid], {"passes": 2}, name="dome", replace=True)
    assert smooth.name == "dome"
    assert project.layers[0] == smooth.uid and dome.uid in project.objects
    assert not project.is_stale(smooth.uid)                # replacing its own input is not stale
    assert project.stale_reasons(base.uid) == ["input 'dome' has a newer version"]
    assert project.is_stale(thick.uid) and project.is_stale(total.uid)
    assert project.objects[thick.uid].content_hash == thick.content_hash   # untouched

    with pytest.raises(OperationError, match="itself stale"):
        recalculate(project, thick.uid)
    new_base = recalculate(project, base.uid)
    assert new_base.derivation.inputs == (smooth.uid,)
    assert not project.is_stale(new_base.uid)
    new_thick = recalculate(project, thick.uid)
    assert new_thick.derivation.inputs == (new_base.uid, smooth.uid)
    np.testing.assert_allclose(new_thick.values.compressed(), 50.0)
    assert project.is_stale(total.uid)                     # still waiting for its own recalculation


def test_lineage_reaches_the_file(project, dome):
    thick = apply(project, "subtract", [dome.uid, dome.uid], name="zero")
    lines = project.lineage(thick.uid)
    assert lines[0].startswith("zero ← subtract")
    assert any("file dome.dat" in line for line in lines)


def test_project_refuses_unknown_inputs(project):
    s = Surface(new_uid(), "x", 0, 0, 1, 1, np.ones((2, 2)), "other",
                Derivation.make("copy", ["nope"]))
    with pytest.raises(ProjectError):
        project.add(s)



def test_surface_map_offers_the_pos_scales(dome):
    from posgridder.plotting.maps import COLORSCALES, POS_SCALES, surface_figure

    assert COLORSCALES == tuple(POS_SCALES) and len(COLORSCALES) == 10
    for name in COLORSCALES:
        for reverse in (False, True):
            fig = surface_figure(dome, colorscale=name, reverse=reverse)
            scale = fig.data[0].colorscale
            assert scale[0][0] == 0.0 and scale[-1][0] == 1.0
    light, dark = (surface_figure(dome, colorscale="Blues").data[0].colorscale[i][1]
                   for i in (0, -1))
    flipped = surface_figure(dome, colorscale="Blues", reverse=True).data[0].colorscale
    assert flipped[0][1] == dark and flipped[-1][1] == light



def test_surface_histogram(dome):
    from posgridder.plotting.maps import surface_figure

    fig = surface_figure(dome, colorscale="Greens", histogram=True)
    (bars,) = [t for t in fig.data if t.type == "bar"]
    assert sum(bars.x) == pytest.approx(dome.n_valid * dome.xinc * dome.yinc / 1e6)
    heat = [t for t in fig.data if t.type == "heatmap"][0]
    assert (heat.zmin, heat.zmax) == pytest.approx((dome.stats()["min"], dome.stats()["max"]))
    assert not [t for t in surface_figure(dome).data if t.type == "bar"]
