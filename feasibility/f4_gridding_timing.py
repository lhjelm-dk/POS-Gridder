"""F4: can linear TIN and a local thin-plate spline regrid dense contours fast enough?

A synthetic two-dome surface on the GEUS geometry (217 x 238 nodes at 250 m) is contoured at
10 m, the lines densified to points, and regridded onto the same nodes. Reports point count,
wall time and RMS error against the known surface (a preview; the D9 benchmark comes later).
"""
from __future__ import annotations

import time

import contourpy
import numpy as np
from scipy.interpolate import LinearNDInterpolator, RBFInterpolator

NCOL, NROW, INC = 217, 238, 250.0


def truth(xx, yy):
    x0, y0 = xx.mean(), yy.mean()
    d1 = 900 * np.exp(-(((xx - x0 + 9000) / 9000) ** 2 + ((yy - y0) / 12000) ** 2))
    d2 = 700 * np.exp(-(((xx - x0 - 11000) / 7000) ** 2 + ((yy - y0 - 8000) / 9000) ** 2))
    return 3000 - d1 - d2 + 0.004 * (yy - y0)


def contour_points(x, y, z, interval: float, spacing: float) -> np.ndarray:
    gen = contourpy.contour_generator(x, y, z, line_type=contourpy.LineType.Separate)
    out = []
    for level in np.arange(np.ceil(z.min() / interval) * interval, z.max(), interval):
        for line in gen.lines(level):
            seg = np.diff(line, axis=0)
            dist = np.concatenate([[0], np.cumsum(np.hypot(*seg.T))])
            s = np.arange(0, dist[-1], spacing)
            out.append(np.column_stack([np.interp(s, dist, line[:, 0]),
                                        np.interp(s, dist, line[:, 1]), np.full(s.size, level)]))
    return np.vstack(out)


def main() -> None:
    x = 621373.0625 + INC * np.arange(NCOL)
    y = 6145533.4525 + INC * np.arange(NROW)
    xx, yy = np.meshgrid(x, y)
    z = truth(xx, yy)
    nodes = np.column_stack([xx.ravel(), yy.ravel()])
    for spacing in (125.0, 60.0):
        pts = contour_points(x, y, z, 10.0, spacing)
        print(f"\ncontours every 10 m, vertices every {spacing:.0f} m: {len(pts):,} points "
              f"-> {len(nodes):,} nodes")
        t = time.perf_counter()
        tin = LinearNDInterpolator(pts[:, :2], pts[:, 2])(nodes).reshape(z.shape)
        print(f"  linear TIN            {time.perf_counter() - t:6.2f} s   "
              f"RMS {np.sqrt(np.nanmean((tin - z) ** 2)):.2f} m (inside hull)")
        inside = ~np.isnan(tin)
        for k in (30, 60, 150):
            t = time.perf_counter()
            # Shift to a local origin: thin-plate kernels on 6e6-scale coordinates lose precision.
            centre = pts[:, :2].mean(axis=0)
            rbf = RBFInterpolator(pts[:, :2] - centre, pts[:, 2], kernel="thin_plate_spline",
                                  neighbors=k)
            tps = rbf(nodes - centre).reshape(z.shape)
            print(f"  thin-plate, k={k:<3}     {time.perf_counter() - t:6.2f} s   "
                  f"RMS {np.sqrt(np.mean((tps - z)[inside] ** 2)):.2f} m inside hull, "
                  f"max {np.abs(tps - z)[inside].max():.1f} m (TIN max {np.nanmax(np.abs(tin - z)):.1f} m)")


if __name__ == "__main__":
    main()
