"""Conversion between :class:`Surface` and ``xtgeo.RegularSurface``.

xtgeo stores values as ``(ncol, nrow)`` with the first index along x; ours is ``(nrow, ncol)``
with row 0 in the south. Rotated grids are refused for now: every tool downstream assumes the
grid axes are the map axes.
"""
from __future__ import annotations

import numpy as np

from posgridder.core.model import Surface


def from_xtgeo(xsurf, name: str | None = None, provenance: str = "") -> Surface:
    if abs(float(xsurf.rotation)) > 1e-9:
        raise ValueError(f"rotated grids are not supported yet (rotation {xsurf.rotation} deg)")
    values = np.ma.asarray(xsurf.values, dtype=float)
    if int(getattr(xsurf, "yflip", 1)) == -1:
        # A y-flipped grid counts rows southwards from yori; turn it into the usual layout.
        values = values[:, ::-1]
        yori = float(xsurf.yori) - (xsurf.nrow - 1) * float(xsurf.yinc)
    else:
        yori = float(xsurf.yori)
    return Surface(
        name=name or getattr(xsurf, "name", None) or "surface",
        xori=float(xsurf.xori), yori=yori,
        xinc=float(xsurf.xinc), yinc=float(xsurf.yinc),
        values=values.T,
        provenance=provenance,
    )


def to_xtgeo(surface: Surface):
    import xtgeo

    return xtgeo.RegularSurface(
        ncol=surface.ncol, nrow=surface.nrow,
        xori=surface.xori, yori=surface.yori,
        xinc=surface.xinc, yinc=surface.yinc,
        values=np.ma.MaskedArray(surface.values.filled(np.nan).T,
                                 mask=np.ma.getmaskarray(surface.values).T),
        name=surface.name,
    )
