"""A synthetic example project: two domes on a tilted flank, as a ZMAP+ depth grid.

Made in code, then imported through the ordinary importer, so the example behaves exactly as a
user's file would: a source with a SHA-256, an import derivation, replayable.
"""
from __future__ import annotations

import numpy as np

from posgridder.core.model import Project
from posgridder.io.surfaces import import_surface
from posgridder.io.zmap import RawGrid, write_zmap

EXAMPLE_NAME = "example two domes"


def example_grid() -> RawGrid:
    """101 × 81 nodes at 100 m. Dome A crest about 2050 m, dome B about 2090 m to the north-east,
    joined by a saddle; the flank dips to the south."""
    x = 600_000.0 + 100.0 * np.arange(101)
    y = 6_150_000.0 + 100.0 * np.arange(81)
    xx, yy = np.meshgrid(x - x[0], y - y[0])
    a = 2050 + 2.0e-5 * ((xx - 3500) ** 2 + 1.6 * (yy - 4200) ** 2)
    b = 2090 + 3.0e-5 * ((xx - 7000) ** 2 + (yy - 5600) ** 2)
    z = np.minimum(a, b) + 0.012 * (8000 - yy) * 0.25
    z += 3.0 * np.sin(xx / 900.0) * np.cos(yy / 1100.0)
    mask = np.zeros_like(z, bool)
    mask[:6, 80:] = True                                    # a data gap in the south-east corner
    return RawGrid(EXAMPLE_NAME, x[0], y[0], 100.0, 100.0,
                   np.ma.MaskedArray(z, mask=mask), crs="ED50-UTM32")


def load_example(project: Project) -> str:
    grid = example_grid()
    surface = import_surface(project, f"{EXAMPLE_NAME}.dat", write_zmap(grid).encode(),
                             domain="depth")
    return surface.uid
