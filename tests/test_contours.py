"""Contour sets, contour files, editing and contours → surface (plan §5.3, §5.4, T21)."""
import io

import numpy as np
import pytest
import shapely

from posgridder.core.benchmark import default_method, judge, run
from posgridder.core.contours import DEFAULT_METHOD
from posgridder.core.model import Source
from posgridder.core.operations import OperationError, apply, replay
from posgridder.io import project_file
from posgridder.io.vectors import inspect, to_geopackage
from tests.conftest import add_grid

A_PAR, L = 1e-4, 1500.0


def paraboloid(project, inc=50.0):
    x = np.arange(-L, L + inc / 2, inc)
    xx, yy = np.meshgrid(x, x)
    return add_grid(project, 2000 + A_PAR * (xx ** 2 + yy ** 2), domain="depth", name="top",
                    inc=inc, xori=-L, yori=-L)


def import_file(project, filename, data, **params):
    source = Source.from_bytes(filename, data)
    project.add_source(source, data)
    return apply(project, "contour_import", [source.uid], {"domain": "depth", **params},
                 name=filename)


def test_contours_of_a_paraboloid(project):
    top = paraboloid(project, inc=25.0)
    cs = apply(project, "contour", [top.uid], {"interval": 25.0}, name="c")
    assert cs.source_uid == top.uid and "every 25" in cs.origin
    circles = [k for k in range(cs.n_lines) if cs.levels[k] == 2100.0]
    (k,) = circles
    assert cs.closed(k)
    assert cs.area_km2(k) == pytest.approx(np.pi * 100 / A_PAR / 1e6, rel=2e-3)
    assert cs.levels.min() == 2025.0


def test_derived_contours_turn_stale_with_their_surface(project):
    top = paraboloid(project)
    cs = apply(project, "contour", [top.uid], {"interval": 25.0}, name="c")
    apply(project, "offset", [top.uid], {"constant": 1.0}, name="top", replace=True)
    assert project.is_stale(cs.uid)


def test_edit_makes_a_new_version_and_never_touches_the_surface(project):
    top = paraboloid(project)
    cs = apply(project, "contour", [top.uid], {"interval": 25.0}, name="c")
    regrid = apply(project, "contours_to_surface", [cs.uid, top.uid],
                   {"roles": ["contours", "template"], "method": "tin"}, name="regrid")
    edited = apply(project, "contour_edit", [cs.uid], {"delete": [0, 1]}, name="c", replace=True)
    assert edited.deleted[:2].all() and not cs.deleted.any()
    assert project.layers.count(edited.uid) == 1 and cs.uid not in project.layers
    assert project.is_stale(regrid.uid)
    assert project.objects[top.uid].content_hash == top.content_hash
    back = apply(project, "contour_edit", [edited.uid], {"restore": [0]}, name="c", replace=True)
    assert not back.deleted[0] and back.deleted[1]
    with pytest.raises(OperationError, match="nothing to grid"):
        apply(project, "contour_edit", [back.uid], {"delete": list(range(back.n_lines))},
              name="c", replace=True)


@pytest.mark.parametrize("method", ["tin", "tps"])
def test_plane_is_reproduced(project, method):
    x = np.arange(0, 2001, 50.0)
    xx, yy = np.meshgrid(x, x)
    plane = add_grid(project, 2000 + 0.02 * xx + 0.01 * yy, domain="depth", name="plane",
                     inc=50.0, xori=0.0, yori=0.0)
    cs = apply(project, "contour", [plane.uid], {"interval": 5.0}, name="c")
    s = apply(project, "contours_to_surface", [cs.uid, plane.uid],
              {"roles": ["contours", "template"], "method": method}, name=f"r {method}")
    ok = ~np.ma.getmaskarray(s.values)
    assert ok.sum() > 0.8 * ok.size
    np.testing.assert_allclose(s.values[ok], plane.values[ok], atol=1e-6)


def test_regrid_paraboloid_and_crest_point(project):
    top = paraboloid(project)
    cs = apply(project, "contour", [top.uid], {"interval": 10.0}, name="c")
    tin = apply(project, "contours_to_surface", [cs.uid, top.uid],
                {"roles": ["contours", "template"], "method": "tin"}, name="tin")
    assert tin.stats()["min"] == pytest.approx(2010.0)          # flat at the innermost contour
    assert any("flat" in w for w in tin.warnings)
    crest = apply(project, "contours_to_surface", [cs.uid, top.uid],
                  {"roles": ["contours", "template"], "method": "tin",
                   "crest_points": [[0.0, 0.0, 2000.0]]}, name="tin + crest")
    assert crest.stats()["min"] == pytest.approx(2000.0)
    tps = apply(project, "contours_to_surface", [cs.uid, top.uid],
                {"roles": ["contours", "template"], "method": "tps"}, name="tps")
    between = (top.values >= 2010) & (top.values <= cs.levels.max())
    err = (tps.values - top.values)[between]
    assert float(np.sqrt(np.ma.mean(err ** 2))) <= 10 / 4


def test_new_grid_over_the_contours_and_hull(project):
    top = paraboloid(project)
    cs = apply(project, "contour", [top.uid], {"interval": 25.0}, name="c")
    from posgridder.core.contours import geometry_for
    g = geometry_for(cs, 100.0)
    s = apply(project, "contours_to_surface", [cs.uid],
              {"roles": ["contours"], "method": "tps", "geometry": g}, name="free")
    assert s.xinc == 100.0 and s.domain == "depth"
    # Corners beyond the outermost contour lie outside the data hull: null, not invented.
    assert s.values.mask[0, 0] and s.values.mask[-1, -1]


def test_template_nulls_are_kept(project):
    x = np.arange(-L, L + 25, 50.0)
    xx, yy = np.meshgrid(x, x)
    mask = np.zeros(xx.shape, bool)
    mask[25:36, 25:36] = True                                  # a hole in the middle
    top = add_grid(project, 2000 + A_PAR * (xx ** 2 + yy ** 2), domain="depth", name="holed",
                   inc=50.0, xori=-L, yori=-L, mask=mask)
    cs = apply(project, "contour", [top.uid], {"interval": 25.0}, name="c")
    s = apply(project, "contours_to_surface", [cs.uid, top.uid],
              {"roles": ["contours", "template"], "method": "tps"}, name="r")
    assert s.values.mask[mask].all()


def test_reconcile_as_a_new_version_of_the_source(project):
    top = paraboloid(project)
    closure = apply(project, "closure", [top.uid], {"crest": [30, 30], "choice": {"event": 0}},
                    name="closure")
    cs = apply(project, "contour", [top.uid], {"interval": 10.0}, name="c")
    revised = apply(project, "contours_to_surface", [cs.uid, top.uid],
                    {"roles": ["contours", "template"], "method": "tps"}, name="top",
                    supersedes=top.uid)
    assert revised.name == "top" and project.layers[0] == revised.uid
    assert project.is_stale(closure.uid)
    assert top.uid in project.objects                          # the original stays in history


def test_geojson_with_attribute_and_z(project):
    import geopandas as gpd

    ring = shapely.Point(0, 0).buffer(500, 64).exterior
    frame = gpd.GeoDataFrame({"depth": [2100.0, 2200.0]},
                             geometry=[ring, shapely.LineString([(0, 0), (900, 0)])])
    buf = io.BytesIO()
    frame.to_file(buf, driver="GeoJSON")
    cs = import_file(project, "lines.geojson", buf.getvalue(), level_field="depth")
    assert cs.n_lines == 2 and list(cs.levels) == [2100.0, 2200.0]
    assert cs.closed(0) and not cs.closed(1)
    assert cs.area_km2(0) == pytest.approx(np.pi * 0.25, rel=2e-3)

    z_lines = [shapely.LineString([(0, 0, 2050), (100, 0, 2050)]),
               shapely.LineString([(0, 10, 2050), (100, 10, 2060)])]       # mixed Z
    zf = gpd.GeoDataFrame({"id": [1, 2]}, geometry=z_lines)
    buf = io.BytesIO()
    zf.to_file(buf, driver="GeoJSON")
    info = inspect(buf.getvalue(), "z.geojson")
    assert info.has_z and "id" in info.numeric_fields
    cs = import_file(project, "z.geojson", buf.getvalue())
    assert cs.n_lines == 1 and any("do not share one Z" in w for w in cs.warnings)


def test_ascii_and_geopackage_round_trip(project):
    text = "x y z id\n0 0 2100 a\n100 0 2100 a\n100 100 2100 a\n0 0 2110 b\n0 200 2110 b\n"
    cs = import_file(project, "lines.xyz", text.encode())
    assert cs.n_lines == 2 and list(cs.levels) == [2100.0, 2110.0]
    edited = apply(project, "contour_edit", [cs.uid], {"delete": [1]}, name=cs.name, replace=True)
    gpkg = to_geopackage(edited)
    back = import_file(project, "back.gpkg", gpkg, level_field="level")
    assert back.n_lines == 2
    np.testing.assert_allclose(back.coords, edited.coords)
    neg = import_file(project, "neg.xyz", text.replace("21", "-21").encode())
    assert any("negative" in w for w in neg.warnings)
    flipped = import_file(project, "flip.xyz", text.replace("21", "-21").encode(),
                          flip_sign=True)
    assert flipped.levels[0] == 2100.0


def test_outline_from_a_closed_contour(project):
    top = paraboloid(project, inc=25.0)
    cs = apply(project, "contour", [top.uid], {"interval": 50.0}, name="c")
    k = int(np.flatnonzero(cs.levels == 2100.0)[0])
    o = apply(project, "outline_from_contour", [cs.uid], {"line": k}, name="o")
    assert o.area_km2 == pytest.approx(cs.area_km2(k), rel=1e-9)
    open_line = [j for j in range(cs.n_lines) if not cs.closed(j)]
    if open_line:
        with pytest.raises(OperationError, match="closed"):
            apply(project, "outline_from_contour", [cs.uid], {"line": open_line[0]}, name="x")


def test_round_trip_and_replay(project):
    top = paraboloid(project)
    cs = apply(project, "contour", [top.uid], {"interval": 25.0}, name="c")
    edited = apply(project, "contour_edit", [cs.uid], {"delete": [2]}, name="c", replace=True)
    apply(project, "contours_to_surface", [edited.uid, top.uid],
          {"roles": ["contours", "template"], "method": "tps"}, name="r")
    loaded = project_file.load(project_file.save(project))
    assert all(r.identical for r in replay(loaded))


def test_benchmark_picks_the_pinned_default():
    """T21 / D9: the benchmark's choice is the default the app uses."""
    judged = judge(run())
    assert default_method(judged) == DEFAULT_METHOD
    assert judged[judged["method"] == DEFAULT_METHOD]["pass_all"].all()


def test_geus_self_consistency(project, geus_path):
    """The GEUS grid, depth-converted, contoured at 10 m and regridded by the default method:
    the main closure's crest, spill and GRV against the original. Self-consistency, not truth."""
    from posgridder.core.closure import crest_candidates
    from posgridder.io.surfaces import import_surface

    t = import_surface(project, geus_path.name, geus_path.read_bytes(), domain="time",
                       flip_sign=True)
    d = apply(project, "depth_convert", [t.uid], {"method": "v0k", "v0": 1800.0, "k": 0.5},
              name="depth")
    cs = apply(project, "contour", [d.uid], {"interval": 10.0}, name="c")
    r = apply(project, "contours_to_surface", [cs.uid, d.uid],
              {"roles": ["contours", "template"], "method": DEFAULT_METHOD}, name="regrid")

    def main_closure(surface):
        cand = crest_candidates(surface, min_height=10.0)[0]
        c = apply(project, "closure", [surface.uid], {"crest": list(cand.node), "min_height": 10.0,
                                                      "choice": {"event": 0}}, name=f"c {surface.name}")
        v = apply(project, "volumes", [c.uid, surface.uid],
                  {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 50.0},
                  name=f"v {surface.name}")
        return c, v

    c0, v0 = main_closure(d)
    c1, v1 = main_closure(r)
    assert abs(c1.crest_depth - c0.crest_depth) <= 10.0
    assert abs(c1.spill_depth - c0.spill_depth) <= 5.0 + c0.spill_resolution_m
    g0 = v0.summary["grv_direct_at_spill_1e6m3"]
    assert v1.grv_at(c0.spill_depth) == pytest.approx(v0.grv_at(min(c0.spill_depth,
                                                                    c1.spill_depth)), rel=0.03)
    assert g0 > 0



def test_crs_mismatch_refused_for_contours_and_outlines(project):
    top = paraboloid(project)                                  # ED50-UTM32
    text = "x y z id\n-500 0 2100 a\n0 500 2100 a\n500 0 2100 a\n0 -500 2100 a\n"
    cs = import_file(project, "lines.xyz", text.encode(), crs="EPSG:25832")
    with pytest.raises(OperationError, match="reprojection"):
        apply(project, "contours_to_surface", [cs.uid, top.uid],
              {"roles": ["contours", "template"], "method": "tin"}, name="x")
    closure = apply(project, "closure", [top.uid], {"crest": [30, 30], "choice": {"event": 0}},
                    name="c")
    assert any("Faults are not represented" in a for a in closure.assumptions)
    o = apply(project, "outline_points", [], {"coords": [[0, 0], [900, 0], [0, 900]],
                                              "crs": "EPSG:25832"}, name="o")
    with pytest.raises(OperationError, match="reprojection"):
        apply(project, "volumes", [closure.uid, top.uid, o.uid],
              {"roles": ["closure", "top", "outline"], "geometry": "top_constant",
               "thickness": 10.0}, name="v")
