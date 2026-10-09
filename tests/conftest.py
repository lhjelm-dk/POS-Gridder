from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from posgridder.core.model import Project, Surface
from posgridder.io.surfaces import import_surface
from posgridder.io.zmap import RawGrid, write_zmap

ROOT = Path(__file__).resolve().parents[1]
GEUS_GRID = ROOT / "data" / "private" / "HVN_Top Gassum_TWTgrd250m_3xsm_geus2023.dat"


@pytest.fixture
def geus_path() -> Path:
    """The GEUS Top Gassum TWT grid. It is not in the repository; tests that need it skip."""
    if not GEUS_GRID.exists():
        pytest.skip("GEUS test grid not present (data/private/ is untracked)")
    return GEUS_GRID


def add_grid(project: Project, z, *, domain: str, name: str = "grid", xori: float = 500_000.0,
             yori: float = 6_100_000.0, inc: float = 100.0, crs: str | None = "ED50-UTM32",
             mask=None) -> Surface:
    """Put a grid into ``project`` the way a user would: as ZMAP+ bytes through the importer.

    Every test layer is therefore a real, replayable import with a source file behind it.
    """
    z = np.asarray(z, dtype=float)
    values = np.ma.MaskedArray(z, mask=np.zeros_like(z, bool) if mask is None else mask)
    raw = RawGrid(name=name, xori=xori, yori=yori, xinc=inc, yinc=inc, values=values, crs=crs)
    data = write_zmap(raw).encode()
    return import_surface(project, f"{name}.dat", data, domain=domain)


def dome_values(nrow: int = 21, ncol: int = 31, inc: float = 100.0) -> np.ndarray:
    """A tilted dome, rows ≠ columns so a transposed read cannot pass by accident."""
    x = inc * np.arange(ncol)
    y = inc * np.arange(nrow)
    xx, yy = np.meshgrid(x, y)
    return (2000 + 1e-5 * ((xx - x[20]) ** 2 + (yy - y[12]) ** 2)
            - 0.01 * xx - 0.02 * yy)


@pytest.fixture
def project() -> Project:
    return Project()


@pytest.fixture
def dome(project) -> Surface:
    """The dome as a depth layer, with a null south-west corner."""
    mask = np.zeros((21, 31), bool)
    mask[:4, :5] = True
    return add_grid(project, dome_values(), domain="depth", name="dome", mask=mask)
