import numpy as np
import pytest

from posgridder.core.model import Project, Surface


def test_geometry(dome):
    assert (dome.nrow, dome.ncol) == (21, 31)
    assert dome.xmax == pytest.approx(dome.xori + 3000)
    assert dome.ymax == pytest.approx(dome.yori + 2000)
    assert dome.n_valid == 21 * 31 - 20
    assert dome.values.shape == (dome.y.size, dome.x.size)


def test_nan_becomes_masked():
    s = Surface("s", 0, 0, 1, 1, np.array([[1.0, np.nan], [3.0, 4.0]]))
    assert s.values.mask.tolist() == [[False, True], [False, False]]


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        Surface("s", 0, 0, 1, 1, np.ones(5))
    with pytest.raises(ValueError):
        Surface("s", 0, 0, -1, 1, np.ones((2, 2)))
    with pytest.raises(ValueError):
        Surface("s", 0, 0, 1, 1, np.ones((2, 2)), domain="colour")


def test_copy_is_independent(dome):
    twin = dome.copy("twin")
    twin.values[5, 5] = -1
    assert dome.values[5, 5] != -1
    assert twin.name == "twin" and dome.name == "dome"


def test_project_names_copy_rename_remove(dome):
    p = Project()
    assert p.add(dome) == "dome"
    assert p.add(dome.copy()) == "dome (2)"
    assert p.copy_surface("dome") == "dome copy"
    assert p.rename("dome (2)", "dome") == "dome (2)"          # taken, so numbered
    assert p.rename("dome (2)", "base") == "base"
    assert list(p.surfaces) == ["dome", "base", "dome copy"]   # order kept
    assert p.surfaces["base"].name == "base"
    p.remove("dome copy")
    assert list(p.surfaces) == ["dome", "base"]
