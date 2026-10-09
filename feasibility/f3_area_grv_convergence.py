"""F3: area and GRV accuracy against analytic answers, as the cell size halves.

Paraboloid z = z0 + a r^2 and cone z = z0 + s r, contact 100 m below the crest. Areas by
(i) contourpy filled polygons measured with shapely and (ii) node count; GRV by (iii) direct
column integration and (iv) trapezoid over a 1 m area-depth table. Sets the T5-T8 bound.
"""
from __future__ import annotations

import numpy as np
import contourpy
import shapely

Z0, A_PAR, S_CONE, H, T = 2000.0, 1e-4, 0.1, 100.0, 50.0
CASES = {
    # name: (depth(r), area(u), grv_top_only(u), grv_with_thickness(u, t))  with u = depth below crest
    "paraboloid": (lambda r: Z0 + A_PAR * r**2,
                   lambda u: np.pi * u / A_PAR,
                   lambda u: np.pi * u**2 / (2 * A_PAR),
                   lambda u, t: np.pi / A_PAR * (u**2 / 2 - max(u - t, 0) ** 2 / 2)),
    "cone": (lambda r: Z0 + S_CONE * r,
             lambda u: np.pi * (u / S_CONE) ** 2,
             lambda u: np.pi * u**3 / (3 * S_CONE**2),
             lambda u, t: np.pi / (3 * S_CONE**2) * (u**3 - max(u - t, 0) ** 3)),
}


def grid(h: float, f):
    x = np.arange(-2000.0, 2000.0 + h / 2, h)
    xx, yy = np.meshgrid(x, x)
    return x, x, f(np.hypot(xx, yy))


def polygon_area(x, y, z, level: float) -> float:
    gen = contourpy.contour_generator(x, y, z, fill_type=contourpy.FillType.OuterOffset)
    points, offsets = gen.filled(float(z.min()) - 1.0, level)
    area = 0.0
    for pts, offs in zip(points, offsets):
        rings = [pts[offs[k]:offs[k + 1]] for k in range(len(offs) - 1)]
        area += shapely.Polygon(rings[0], rings[1:]).area
    return area


def run() -> list[dict]:
    rows = []
    for name, (depth, area_fn, grv_fn, grv_t_fn) in CASES.items():
        for h in (100.0, 50.0, 25.0, 12.5):
            x, y, z = grid(h, depth)
            c = Z0 + H
            a_true, v_true, vt_true = area_fn(H), grv_fn(H), grv_t_fn(H, T)
            a_poly = polygon_area(x, y, z, c)
            a_node = np.count_nonzero(z <= c) * h * h
            v_direct = np.clip(c - z, 0, None).sum() * h * h
            base = z + T
            vt_direct = np.clip(np.minimum(base, c) - z, 0, None).sum() * h * h
            depths = np.arange(Z0, c + 0.5, 1.0)
            areas = np.array([polygon_area(x, y, z, d) if d > z.min() else 0.0 for d in depths])
            v_trap = np.trapezoid(areas, depths)
            rows.append(dict(case=name, h=h,
                             area_poly=a_poly / a_true - 1, area_node=a_node / a_true - 1,
                             grv_direct=v_direct / v_true - 1, grv_trap=v_trap / v_true - 1,
                             grv_t_direct=vt_direct / vt_true - 1))
    return rows


if __name__ == "__main__":
    rows = run()
    print(f"{'case':<11}{'h (m)':>7}{'area poly':>12}{'area node':>12}{'GRV direct':>12}"
          f"{'GRV trap':>12}{'GRV+t dir':>12}   (relative errors)")
    for r in rows:
        print(f"{r['case']:<11}{r['h']:>7.1f}{r['area_poly']:>12.2e}{r['area_node']:>12.2e}"
              f"{r['grv_direct']:>12.2e}{r['grv_trap']:>12.2e}{r['grv_t_direct']:>12.2e}")
