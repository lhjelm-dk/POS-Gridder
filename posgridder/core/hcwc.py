"""Contact distributions from HCWC Builder, and depth→POS curves typed by the interpreter.

Conventions (plan §5.7, HCWC Builder ``hcwc/io/geox.py``):

- A table runs from **P100 to P0 in the exceedance convention**: P100 is the *shallowest*
  contact, P0 the deepest. ``Pxx`` is the chance the contact is at least that deep.
- Depth is m TVDSS, positive down.
- A current Builder export holds only the realisations whose column reaches the assessment
  minimum ``h_min`` (``result.contact_m[result.above_minimum]``): it is conditioned on
  ``H ≥ h_min``. Its tails are truncated at P99.5/P0.5 by default.

The exceedance function ``E(z) = P(C > z)`` is piecewise linear in depth between rows, 1 above
the shallowest row and 0 below the deepest. Rows with the same depth (a point mass, such as
contacts piling up at a spill) make a step: just above the depth E takes the group's higher
exceedance, at and below it the lower. The inequality is strict: a contact exactly at the
structural depth leaves no column.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, replace
from typing import ClassVar

import numpy as np
import pandas as pd

from posgridder.core.model import Derivation, hash_parts, read_only

BASES = {"geological": "Geological", "given_dhi": "Given the DHI"}
CONDITIONINGS = {"h_min": "Conditioned on H ≥ h_min (current Builder export)",
                 "unconditioned": "Unconditioned (every successful realisation)"}
TAILS = {"truncated": "Truncated (P99.5/P0.5, Builder default)", "raw": "Raw sample min/max",
         "unknown": "Not known"}
ERROR_BOUND = 0.015          # one percentile step (0.01) plus tail truncation (0.005)


class TableError(ValueError):
    """A percentile table that breaks the exceedance convention; the message says how."""


# --------------------------------------------------------------------------- the table
def validate_table(percentiles, depths) -> tuple[np.ndarray, np.ndarray]:
    """Check a percentile table and return it as arrays (percentiles 100 → 0)."""
    p = np.asarray(percentiles, dtype=float)
    d = np.asarray(depths, dtype=float)
    if p.shape != d.shape or p.ndim != 1:
        raise TableError("percentiles and depths must be two columns of equal length")
    if p.size < 2:
        raise TableError("a table needs at least two rows")
    if not (np.isfinite(p).all() and np.isfinite(d).all()):
        raise TableError("the table holds empty or non-numeric cells")
    if p[0] < p[-1]:
        raise TableError("the percentiles run upwards; the exceedance convention runs P100 "
                         "(shallowest) down to P0 (deepest)")
    if not (np.diff(p) < 0).all():
        raise TableError("the percentiles must fall strictly, row by row, from 100 to 0")
    if p[0] != 100 or p[-1] != 0:
        raise TableError("the table must start at P100 and end at P0, so both ends are known")
    if (d <= 0).any():
        raise TableError("depths are negative or zero; depth is positive down (flip the sign "
                         "on import if the file stores it negative)")
    if (np.diff(d) < 0).any():
        k = int(np.argmax(np.diff(d) < 0))
        raise TableError(f"depth decreases from P{p[k]:g} ({d[k]:g} m) to P{p[k + 1]:g} "
                         f"({d[k + 1]:g} m); in the exceedance convention depth increases as "
                         "the percentile falls — the column may be reversed")
    return p, d


class Exceedance:
    """``E(z) = P(C > z)`` from a validated table (plan §5.7)."""

    def __init__(self, percentiles, depths, shift: float = 0.0):
        p, d = validate_table(percentiles, depths)
        e = p / 100.0
        d = d + shift
        self.depths, self.e_hi, self.e_lo = [], [], []
        for depth in np.unique(d):
            group = e[d == depth]
            self.depths.append(float(depth))
            self.e_hi.append(float(group.max()))      # just above this depth
            self.e_lo.append(float(group.min()))      # at and below it
        self.depths = np.array(self.depths)
        self.e_hi = np.array(self.e_hi)
        self.e_lo = np.array(self.e_lo)

    def __call__(self, z) -> np.ndarray:
        z = np.asarray(z, dtype=float)
        u, hi, lo = self.depths, self.e_hi, self.e_lo
        if u.size == 1:                                  # every contact at one depth
            return np.where(z < u[0], 1.0, lo[0])
        # u[k] ≤ z < u[k+1]: from the lower value at u[k] to the upper value just above u[k+1].
        k = np.clip(np.searchsorted(u, z, side="right") - 1, 0, u.size - 2)
        between = lo[k] + (hi[k + 1] - lo[k]) * (z - u[k]) / (u[k + 1] - u[k])
        return np.where(z < u[0], 1.0, np.where(z >= u[-1], lo[-1], between))

    def depth_at(self, exceedance: float) -> float:
        """The depth at which E falls to ``exceedance`` (for reading P90/P50/P10 back)."""
        z = np.linspace(self.depths[0], self.depths[-1], 20001)
        e = self(z)
        idx = int(np.argmax(e <= exceedance))
        return float(z[idx])


def parse_csv(data: bytes) -> tuple[np.ndarray, np.ndarray, str]:
    """``Percentile`` plus ``Value`` or ``Depth(m)``; returns percentiles, depths, depth header."""
    text = data.decode("utf-8-sig", errors="replace")
    try:
        frame = pd.read_csv(io.StringIO(text), comment="#")
    except Exception as exc:                            # noqa: BLE001 — reported as a table error
        raise TableError(f"not a readable CSV ({exc})") from None
    cols = {re.sub(r"[^a-z]", "", c.lower()): c for c in frame.columns}
    pcol = cols.get("percentile")
    dcol = next((cols[k] for k in ("depthm", "depth", "value") if k in cols), None)
    if pcol is None or dcol is None:
        raise TableError(f"expected columns Percentile and Value (or Depth(m)); the file has "
                         f"{', '.join(map(str, frame.columns))}")
    p = pd.to_numeric(frame[pcol], errors="coerce").to_numpy(float)
    d = pd.to_numeric(frame[dcol], errors="coerce").to_numpy(float)
    return p, d, str(dcol)


def split_row(line: str) -> list[str]:
    """One pasted row as cells, accepting decimal commas.

    Tab, semicolon or space separate the columns (a spreadsheet pastes with tabs), and a comma
    inside a cell is then a decimal comma: ``1915,05409<TAB>98``. A row with none of those and
    commas only is comma-separated with decimal points: ``100,2126.7``.
    """
    line = line.replace("%", "").strip()
    if re.search(r"[\t; ]", line):
        cells = re.split(r"[\t; ]+", line)
        return [c.replace(",", ".") for c in cells if c]
    return [c for c in line.split(",") if c]


def parse_rows(text: str, columns: int = 2) -> np.ndarray:
    """Numeric rows of at least ``columns`` cells; header lines before the first row are skipped."""
    rows = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        cells = split_row(line)
        try:
            rows.append([float(c) for c in cells[:columns]])
            if len(rows[-1]) < columns:
                raise ValueError
        except ValueError:
            if rows and len(rows[-1]) < columns:
                rows.pop()
            if not rows:
                continue                                # a header line
            raise TableError(f"line {n} does not hold {columns} numbers: {raw.strip()!r}") \
                from None
    if not rows:
        raise TableError("no rows found")
    return np.array(rows)


def looks_like_percentiles(values: np.ndarray) -> bool:
    """A column running from 100 down to 0 (or up from 0 to 100) in steps: percentiles."""
    v = np.asarray(values, dtype=float)
    return (v.size >= 3 and v.min() == 0 and v.max() == 100
            and (bool((np.diff(v) < 0).all()) or bool((np.diff(v) > 0).all())))


def parse_pasted(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Percentile and depth pasted from a spreadsheet, in either column order.

    The percentile column is the one running between 100 and 0; the other is depth. Decimal
    commas are read as such (see :func:`split_row`).
    """
    arr = parse_rows(text, 2)
    first, second = arr[:, 0], arr[:, 1]
    if looks_like_percentiles(second) and not looks_like_percentiles(first):
        return second, first
    return first, second


def basis_from_filename(filename: str) -> str | None:
    """The Builder writes ``hcwc_percentiles_<basis>.csv``; the basis is read back from it."""
    name = filename.lower()
    if "given_dhi" in name or "given dhi" in name:
        return "given_dhi"
    if "geological" in name:
        return "geological"
    return None


def parse_hcwc_json(data: bytes) -> dict:
    """What a Builder prospect file says about the multiplier: P(G), h_min, the apex.

    Read from ``inputs`` only; the ``resolved`` block can be stale (feasibility F5). P(G) is the
    product of ``play_<element> × cond_<element>`` over the elements present. The apex is the
    midpoint of the P1 and P99 typed in the Builder.
    """
    try:
        doc = json.loads(data.decode("utf-8-sig"))
        inputs = doc["inputs"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TableError(f"not a HCWC Builder prospect file ({exc})") from None
    elements = sorted(k[5:] for k in inputs if k.startswith("play_") and f"cond_{k[5:]}" in inputs)
    out: dict = {"name": inputs.get("prospect_name"), "elements": {}}
    if elements:
        chances = {e: float(inputs[f"play_{e}"]) * float(inputs[f"cond_{e}"]) for e in elements}
        out["elements"] = chances
        out["p_g"] = float(np.prod(list(chances.values())))
    if "min_column_input" in inputs:
        out["h_min"] = float(inputs["min_column_input"])
    if "apex_p1" in inputs and "apex_p99" in inputs:
        out["apex"] = 0.5 * (float(inputs["apex_p1"]) + float(inputs["apex_p99"]))
    if "spill_input" in inputs:
        out["spill"] = float(inputs["spill_input"])
    out["dhi"] = bool(inputs.get("dhi_toggle", False))
    return out


# --------------------------------------------------------------------------- the objects
@dataclass(frozen=True)
class ContactDistribution:
    """A contact-depth distribution and everything that says what it means."""
    kind: ClassVar[str] = "hcwc"
    uid: str
    name: str
    derivation: Derivation
    percentiles: np.ndarray
    depths: np.ndarray
    basis: str
    conditioning: str
    tails: str
    p_g: float | None = None
    f_hmin: float | None = None
    h_min: float | None = None
    apex: float | None = None
    builder_spill: float | None = None     # the spill depth typed in the Builder, if known
    origin: str = ""
    sources: tuple[str, ...] = ()          # where each multiplier input came from, in words
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        p, d = validate_table(self.percentiles, self.depths)
        object.__setattr__(self, "percentiles", read_only(p))
        object.__setattr__(self, "depths", read_only(d))
        if self.basis not in BASES:
            raise ValueError(f"unknown basis {self.basis!r}")
        if self.conditioning not in CONDITIONINGS:
            raise ValueError(f"unknown conditioning {self.conditioning!r}")
        if self.tails not in TAILS:
            raise ValueError(f"unknown tail treatment {self.tails!r}")
        for name in ("p_g", "f_hmin"):
            v = getattr(self, name)
            if v is not None and not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must lie between 0 and 1, got {v}")

    def exceedance(self, shift: float = 0.0) -> Exceedance:
        return Exceedance(self.percentiles, self.depths, shift)

    @property
    def content_hash(self) -> str:
        return hash_parts(self.percentiles, self.depths, self.basis, self.conditioning, self.tails,
                          self.p_g, self.f_hmin, self.h_min, self.apex, self.origin,
                          list(self.sources),
                          # Only when set, so distributions saved before the field existed
                          # keep their hash and their project files still load.
                          *([self.builder_spill] if self.builder_spill is not None else []))

    def renamed(self, name: str) -> "ContactDistribution":
        return replace(self, name=name)

    def to_record(self):
        meta = {k: getattr(self, k) for k in ("basis", "conditioning", "tails", "p_g", "f_hmin",
                                              "h_min", "apex", "builder_spill", "origin")}
        meta["sources"] = list(self.sources)
        return meta, {"percentiles": self.percentiles, "depths": self.depths}

    @classmethod
    def from_record(cls, common, meta, arrays) -> "ContactDistribution":
        meta = dict(meta)
        meta["sources"] = tuple(meta["sources"])
        return cls(percentiles=arrays["percentiles"], depths=arrays["depths"], **meta, **common)


@dataclass(frozen=True)
class PosCurve:
    """A depth → POS curve typed by the interpreter (decision D6)."""
    kind: ClassVar[str] = "poscurve"
    uid: str
    name: str
    derivation: Derivation
    depths: np.ndarray
    values: np.ndarray
    meaning: str                            # "total" or "conditional"
    warnings: tuple[str, ...] = ()

    MEANINGS: ClassVar[dict] = {"total": "Total POS (P(G) included)",
                                "conditional": "Conditional on G (multiplied by P(G))"}

    def __post_init__(self) -> None:
        d = np.asarray(self.depths, dtype=float)
        v = np.asarray(self.values, dtype=float)
        if d.shape != v.shape or d.ndim != 1 or d.size < 1:
            raise ValueError("a curve needs depth and value columns of equal length")
        if not (np.isfinite(d).all() and np.isfinite(v).all()):
            raise ValueError("the curve holds empty or non-numeric cells")
        if (np.diff(d) <= 0).any():
            raise ValueError("depths must increase strictly, row by row")
        if ((v < 0) | (v > 1)).any():
            raise ValueError("values are fractions between 0 and 1 (24 % is 0.24)")
        if self.meaning not in self.MEANINGS:
            raise ValueError(f"unknown meaning {self.meaning!r}")
        object.__setattr__(self, "depths", read_only(d))
        object.__setattr__(self, "values", read_only(v))

    def at(self, z, spill: float) -> np.ndarray:
        """Linear in depth between rows, the first value above the first row, 0 at the spill."""
        d, v = self.depths, self.values
        keep = d < spill
        d, v = np.append(d[keep], spill), np.append(v[keep], 0.0)
        return np.interp(np.asarray(z, dtype=float), d, v, left=v[0], right=0.0)

    @property
    def content_hash(self) -> str:
        return hash_parts(self.depths, self.values, self.meaning)

    def renamed(self, name: str) -> "PosCurve":
        return replace(self, name=name)

    def to_record(self):
        return {"meaning": self.meaning}, {"depths": self.depths, "values": self.values}

    @classmethod
    def from_record(cls, common, meta, arrays) -> "PosCurve":
        return cls(depths=arrays["depths"], values=arrays["values"], meaning=meta["meaning"],
                   **common)
