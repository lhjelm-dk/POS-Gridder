"""The D9 benchmark: which contours→surface method, judged by geology, not by fit statistics.

Known surfaces are contoured at interval Δ from a fine (10 m) sampling, regridded onto a 50 m
grid by each method, and compared with the exact answer on the same nodes. The thresholds are
those of plan §7.2 (decision D9):

    plane                       reproduced to 1e-6 m
    spurious closures           none higher than Δ/2
    depth between contours      RMS ≤ Δ/4, max ≤ Δ/2
    spill depth                 within Δ/2 plus the grid's resolution at the spill
    crest (none supplied)       within Δ (paraboloid and cone; reported for the rest)
    area at a contoured level   within 1 %
    GRV to the spill            within 3 % (closures of at least 5Δ relief)

The default method is the thin-plate spline if it meets every threshold, otherwise linear TIN.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from posgridder.core.closure import crest_candidates, spill_resolution
from posgridder.core.model import Project
from posgridder.core.operations import apply

TARGET_INC = 50.0
FINE_INC = 10.0
A_PAR, S_CONE = 1e-4, 0.1


def _cases() -> dict:
    """name: (depth function of x, y, half width, analytic area(u), analytic GRV(u) or None)."""
    def par(x, y):
        return 2000 + A_PAR * (x ** 2 + y ** 2)

    def cone(x, y):
        return 2000 + S_CONE * np.hypot(x, y)

    def domes(x, y):
        a = 2000 + A_PAR * ((x + 700) ** 2 + y ** 2)
        b = 2010 + A_PAR * ((x - 700) ** 2 + y ** 2)
        return np.minimum(a, b)

    def plane(x, y):
        return 2000 + 0.02 * x + 0.01 * y

    return {
        "plane": (plane, 1500.0, None, None),
        "paraboloid": (par, 1500.0, lambda u: np.pi * u / A_PAR,
                       lambda u: np.pi * u ** 2 / (2 * A_PAR)),
        "cone": (cone, 1500.0, lambda u: np.pi * (u / S_CONE) ** 2,
                 lambda u: np.pi * u ** 3 / (3 * S_CONE ** 2)),
        "two domes": (domes, 2000.0, None, None),
    }


def _grid(project, f, half, inc, name):
    from posgridder.io.surfaces import import_surface
    from posgridder.io.zmap import RawGrid, write_zmap

    x = np.arange(-half, half + inc / 2, inc)
    xx, yy = np.meshgrid(x, x)
    raw = RawGrid(name, -half, -half, inc, inc, np.ma.MaskedArray(f(xx, yy)), crs="bench")
    return import_surface(project, f"{name}.dat", write_zmap(raw).encode(), domain="depth")


def _closure_stats(project, surface, min_height):
    cands = crest_candidates(surface, min_height=min_height)
    if not cands:
        return cands, None, None
    c = apply(project, "closure", [surface.uid],
              {"crest": list(cands[0].node), "min_height": min_height,
               "choice": {"event": 0}}, name=f"cl {surface.name}")
    v = apply(project, "volumes", [c.uid, surface.uid],
              {"roles": ["closure", "top"], "geometry": "top_constant", "thickness": 1e5},
              name=f"v {surface.name}")
    return cands, c, v


def run(intervals=(10.0, 25.0), methods=("tin", "tps")) -> pd.DataFrame:
    rows = []
    for case, (f, half, area_fn, grv_fn) in _cases().items():
        for delta in intervals:
            project = Project()
            fine = _grid(project, f, half, FINE_INC, f"{case} fine")
            truth = _grid(project, f, half, TARGET_INC, f"{case} truth")
            cs = apply(project, "contour", [fine.uid], {"interval": delta}, name="contours")
            levels = np.unique(cs.levels)
            t_cands, t_closure, t_vol = (_closure_stats(project, truth, delta / 2)
                                         if case != "plane" else ([], None, None))
            for method in methods:
                s = apply(project, "contours_to_surface", [cs.uid, truth.uid],
                          {"roles": ["contours", "template"], "method": method},
                          name=f"{method} {delta}")
                z, zt = np.ma.getdata(s.values), np.ma.getdata(truth.values)
                valid = ~np.ma.getmaskarray(s.values)
                between = valid & (zt >= levels.min()) & (zt <= levels.max())
                err = (z - zt)[between]
                row = {"case": case, "interval_m": delta, "method": method,
                       "rms_m": float(np.sqrt(np.mean(err ** 2))),
                       "max_m": float(np.max(np.abs(err)))}
                if case == "plane":
                    row["plane_max_m"] = float(np.max(np.abs((z - zt)[valid])))
                    rows.append(row)
                    continue
                cands, closure, vol = _closure_stats(project, s, delta / 2)
                row["spurious_closures"] = max(0, len(cands) - len(t_cands))
                tc = t_cands[0]
                row["crest_error_m"] = float(cands[0].crest_depth - tc.crest_depth)
                row["spill_error_m"] = float(closure.spill_depth - t_closure.spill_depth)
                row["spill_bound_m"] = delta / 2 + spill_resolution(
                    truth, tuple(t_closure.events[0]["node"]) if t_closure.events else tc.node)
                relief = t_closure.spill_depth - t_closure.crest_depth
                level = float(levels[(levels > tc.crest_depth + 0.4 * relief)][0])
                u = level - tc.crest_depth
                ref_area = area_fn(u) if area_fn else t_vol.area_at(level) * 1e6
                got_area = vol.area_at(level) * 1e6
                row["area_level_m"] = level
                row["area_error_rel"] = float(got_area / ref_area - 1)
                c_star = min(t_closure.spill_depth, closure.spill_depth)
                ref_grv = (grv_fn(c_star - tc.crest_depth) / 1e6 if grv_fn
                           else t_vol.grv_at(c_star))
                row["grv_error_rel"] = float(vol.grv_at(c_star) / ref_grv - 1)
                row["relief_intervals"] = float(relief / delta)
                row["analytic"] = bool(area_fn)
                rows.append(row)
    return pd.DataFrame(rows)


def judge(frame: pd.DataFrame) -> pd.DataFrame:
    """Pass/fail of every threshold, per case, interval and method."""
    out = frame.copy()
    d = out["interval_m"]
    out["pass_rms"] = out["rms_m"] <= d / 4
    out["pass_max"] = out["max_m"] <= d / 2
    plane = out["case"] == "plane"
    out.loc[plane, "pass_plane"] = out.loc[plane, "plane_max_m"] <= 1e-6
    rest = ~plane
    out.loc[rest, "pass_spurious"] = out.loc[rest, "spurious_closures"] == 0
    out.loc[rest, "pass_spill"] = out.loc[rest, "spill_error_m"].abs() <= out.loc[rest, "spill_bound_m"]
    crest_checked = rest & out["analytic"].astype("boolean").fillna(False).astype(bool)
    out.loc[rest, "pass_crest"] = True
    out.loc[crest_checked, "pass_crest"] = out.loc[crest_checked, "crest_error_m"].abs() <= d[crest_checked]
    out.loc[rest, "pass_area"] = out.loc[rest, "area_error_rel"].abs() <= 0.01
    big = rest & (out["relief_intervals"] >= 5)
    out.loc[rest, "pass_grv"] = True
    out.loc[big, "pass_grv"] = out.loc[big, "grv_error_rel"].abs() <= 0.03
    checks = [c for c in out.columns if c.startswith("pass_")]
    out["pass_all"] = out[checks].astype("boolean").fillna(True).astype(bool).all(axis=1)
    return out


def default_method(judged: pd.DataFrame) -> str:
    """Thin-plate spline if it meets every threshold in every case; otherwise TIN."""
    return "tps" if judged[judged["method"] == "tps"]["pass_all"].all() else "tin"
