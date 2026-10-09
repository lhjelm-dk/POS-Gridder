from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from posgridder.core.model import Surface

ROOT = Path(__file__).resolve().parents[1]
GEUS_GRID = ROOT / "data" / "private" / "HVN_Top Gassum_TWTgrd250m_3xsm_geus2023.dat"


@pytest.fixture
def geus_path() -> Path:
    """The GEUS Top Gassum TWT grid. It is not in the repository; tests that need it skip."""
    if not GEUS_GRID.exists():
        pytest.skip("GEUS test grid not present (data/private/ is untracked)")
    return GEUS_GRID


@pytest.fixture
def dome() -> Surface:
    """A synthetic dome, 21 x 31 nodes at 100 m, with a null corner. Value = depth in m.

    Columns and rows differ in number so a transposed read cannot pass by accident, and the
    surface tilts so a mirrored one cannot either.
    """
    x = 500_000 + 100.0 * np.arange(31)
    y = 6_100_000 + 100.0 * np.arange(21)
    xx, yy = np.meshgrid(x, y)
    z = (2000 + 1e-5 * ((xx - x[20]) ** 2 + (yy - y[12]) ** 2)
         - 0.01 * (xx - x[0]) - 0.02 * (yy - y[0]))
    mask = np.zeros_like(z, dtype=bool)
    mask[:4, :5] = True                                  # south-west corner is null
    return Surface("dome", x[0], y[0], 100.0, 100.0, np.ma.MaskedArray(z, mask=mask),
                   domain="depth", unit="m", crs="ED50-UTM32")
