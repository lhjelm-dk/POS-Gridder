"""The objects a POS-Gridder project holds, and the rules that keep them traceable.

**Every object is immutable.** A change makes a new object; the old one stays in the project's
history. That is what lets the project say, for any layer, exactly which inputs and parameters
made it, and mark a layer *stale* when one of its inputs has since been replaced.

- :class:`Source` — an imported file: its name, size and SHA-256. Its bytes are kept, so every
  layer can be recomputed from the original file.
- :class:`Surface` — a regular, unrotated grid plus the :class:`Derivation` that produced it.
  ``values`` is a read-only masked array of shape ``(nrow, ncol)`` with **row 0 at the southern
  edge** and column 0 at the western edge, so ``values[i, j]`` sits at ``(x[j], y[i])``.
- :class:`Project` — all sources and surfaces ever made, the ordered list of current layers, and
  the supersession links between versions.

Depth and time are stored positive down. A file that stores them negative is flipped on import,
and the flip is an import parameter in the derivation, not an edit of the file.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

import numpy as np

from posgridder import __version__

#: What a surface's values measure, and the one unit each domain is held in for v1.
UNITS: dict[str, str] = {
    "depth": "m",
    "time": "ms",
    "thickness": "m",
    "velocity": "m/s",
    "probability": "fraction",
    "other": "",
}
DOMAINS: tuple[str, ...] = tuple(UNITS)


def new_uid() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Source:
    """An imported file. Never modified; its bytes travel with the project."""
    uid: str
    filename: str
    sha256: str
    size: int
    imported: str

    @classmethod
    def from_bytes(cls, filename: str, data: bytes) -> "Source":
        return cls(uid=new_uid(), filename=filename, sha256=hashlib.sha256(data).hexdigest(),
                   size=len(data), imported=_now())


@dataclass(frozen=True)
class Derivation:
    """How an object was made: the operation, its inputs (by uid) and its parameters.

    ``params_json`` is canonical JSON, so two derivations with equal parameters compare equal and
    the record can be written to the project file as it is.
    """
    operation: str
    inputs: tuple[str, ...]
    params_json: str = "{}"
    supersedes: str | None = None
    app_version: str = __version__
    created: str = field(default_factory=_now)

    @classmethod
    def make(cls, operation: str, inputs, params: dict[str, Any] | None = None,
             supersedes: str | None = None) -> "Derivation":
        return cls(operation=operation, inputs=tuple(inputs),
                   params_json=json.dumps(params or {}, sort_keys=True), supersedes=supersedes)

    @property
    def params(self) -> dict[str, Any]:
        return json.loads(self.params_json)

    def describe(self) -> str:
        params = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.operation}({params})" if params else self.operation


def _read_only(values: np.ma.MaskedArray) -> np.ma.MaskedArray:
    data = np.array(np.ma.getdata(values), dtype=float)
    mask = np.array(np.ma.getmaskarray(values), dtype=bool)
    mask |= ~np.isfinite(data)
    data[mask] = np.nan
    data.flags.writeable = False
    mask.flags.writeable = False
    out = np.ma.MaskedArray(data, mask=mask, copy=False)
    return out


@dataclass(frozen=True)
class Surface:
    uid: str
    name: str
    xori: float
    yori: float
    xinc: float
    yinc: float
    values: np.ma.MaskedArray
    domain: str
    derivation: Derivation
    crs: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.domain not in DOMAINS:
            raise ValueError(f"unknown domain {self.domain!r}; expected one of {DOMAINS}")
        values = np.ma.asarray(self.values)
        if values.ndim != 2 or min(values.shape) < 2:
            raise ValueError(f"a surface needs a 2-D grid of at least 2 x 2 nodes, got {values.shape}")
        if not (self.xinc > 0 and self.yinc > 0):
            raise ValueError("grid increments must be positive")
        object.__setattr__(self, "values", _read_only(values))
        for name in ("xori", "yori", "xinc", "yinc"):
            object.__setattr__(self, name, float(getattr(self, name)))

    # ------------------------------------------------------------------ geometry
    @property
    def unit(self) -> str:
        return UNITS[self.domain]

    @property
    def nrow(self) -> int:
        return int(self.values.shape[0])

    @property
    def ncol(self) -> int:
        return int(self.values.shape[1])

    @property
    def xmax(self) -> float:
        return self.xori + (self.ncol - 1) * self.xinc

    @property
    def ymax(self) -> float:
        return self.yori + (self.nrow - 1) * self.yinc

    @property
    def x(self) -> np.ndarray:
        return self.xori + self.xinc * np.arange(self.ncol)

    @property
    def y(self) -> np.ndarray:
        return self.yori + self.yinc * np.arange(self.nrow)

    @property
    def geometry(self) -> tuple[float, float, float, float, int, int]:
        return (self.xori, self.yori, self.xinc, self.yinc, self.ncol, self.nrow)

    def same_geometry(self, other: "Surface") -> bool:
        """True when both grids have the same nodes, to a millionth of a cell."""
        if self.values.shape != other.values.shape:
            return False
        tol = 1e-6 * min(self.xinc, self.yinc)
        return all(abs(a - b) <= tol for a, b in zip(self.geometry[:4], other.geometry[:4]))

    # ------------------------------------------------------------------ content
    @property
    def n_valid(self) -> int:
        return int(self.values.count())

    def stats(self) -> dict[str, float | int]:
        v = self.values.compressed()
        return {
            "nodes": self.nrow * self.ncol,
            "valid": int(v.size),
            "min": float(v.min()) if v.size else float("nan"),
            "max": float(v.max()) if v.size else float("nan"),
            "mean": float(v.mean()) if v.size else float("nan"),
        }

    @property
    def content_hash(self) -> str:
        """SHA-256 of geometry, mask and values: equal hashes mean identical grids."""
        h = hashlib.sha256()
        h.update(json.dumps(list(self.geometry)).encode())
        mask = np.ma.getmaskarray(self.values)
        h.update(np.ascontiguousarray(mask).tobytes())
        h.update(np.ascontiguousarray(np.where(mask, 0.0, np.ma.getdata(self.values))).tobytes())
        return h.hexdigest()

    def renamed(self, name: str) -> "Surface":
        """The same object under another name. A name is a label, not data: the uid stays."""
        return replace(self, name=name)


class ProjectError(ValueError):
    """A request the project refuses, with the reason in the message."""


@dataclass
class Project:
    """Sources, every surface version ever made, and the ordered list of current layers."""
    sources: dict[str, Source] = field(default_factory=dict)
    source_bytes: dict[str, bytes] = field(default_factory=dict)
    objects: dict[str, Surface] = field(default_factory=dict)
    layers: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ names
    def layer_names(self) -> dict[str, str]:
        return {uid: self.objects[uid].name for uid in self.layers}

    def unique_name(self, name: str, ignore: str | None = None) -> str:
        """``name``, or ``name (2)``, ``name (3)``… if a current layer already has it."""
        taken = {n for uid, n in self.layer_names().items() if uid != ignore}
        base = name.strip() or "surface"
        if base not in taken:
            return base
        n = 2
        while f"{base} ({n})" in taken:
            n += 1
        return f"{base} ({n})"

    def by_name(self, name: str) -> Surface:
        for uid in self.layers:
            if self.objects[uid].name == name:
                return self.objects[uid]
        raise KeyError(name)

    # ------------------------------------------------------------------ adding
    def add_source(self, source: Source, data: bytes) -> None:
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise ProjectError(f"{source.filename}: bytes do not match the recorded SHA-256")
        self.sources[source.uid] = source
        self.source_bytes[source.uid] = data

    def add(self, surface: Surface) -> Surface:
        """Register a new object and show it as a layer.

        A surface whose derivation ``supersedes`` another takes that layer's place in the list;
        the old version stays in ``objects`` as history.
        """
        for uid in surface.derivation.inputs:
            if uid not in self.objects and uid not in self.sources:
                raise ProjectError(f"input {uid[:8]} is not in the project")
        old = surface.derivation.supersedes
        surface = surface.renamed(self.unique_name(surface.name, ignore=old))
        self.objects[surface.uid] = surface
        if old is not None and old in self.layers:
            self.layers[self.layers.index(old)] = surface.uid
        else:
            self.layers.append(surface.uid)
        return surface

    def rename(self, uid: str, name: str) -> Surface:
        surface = self.objects[uid].renamed(self.unique_name(name, ignore=uid))
        self.objects[uid] = surface
        return surface

    def remove(self, uid: str) -> None:
        """Take a layer off the list. Objects still needed as inputs stay in the history."""
        self.layers.remove(uid)
        self._prune()

    def _prune(self) -> None:
        needed: set[str] = set(self.layers)
        stack = list(self.layers)
        while stack:
            obj = self.objects.get(stack.pop())
            if obj is None:
                continue
            for uid in (*obj.derivation.inputs, obj.derivation.supersedes):
                if uid and uid not in needed:
                    needed.add(uid)
                    stack.append(uid)
        self.objects = {k: v for k, v in self.objects.items() if k in needed}
        self.sources = {k: v for k, v in self.sources.items() if k in needed}
        self.source_bytes = {k: v for k, v in self.source_bytes.items() if k in needed}

    # ------------------------------------------------------------------ versions and staleness
    def successor(self, uid: str) -> str | None:
        for obj in self.objects.values():
            if obj.derivation.supersedes == uid:
                return obj.uid
        return None

    def latest(self, uid: str) -> str:
        seen = {uid}
        while (nxt := self.successor(uid)) is not None and nxt not in seen:
            uid = nxt
            seen.add(uid)
        return uid

    def current_input(self, inp: str, of: str) -> str:
        """The version of input ``inp`` that object ``of`` should now read.

        Normally the newest version. But when ``of`` is itself the version that replaced
        ``inp`` (a smoothing applied in place, say), ``inp`` is its own predecessor and stays.
        """
        return inp if self.successor(inp) == of else self.latest(inp)

    def stale_reasons(self, uid: str) -> list[str]:
        """Why ``uid`` no longer reflects its inputs; empty when it is current.

        A surface is stale when an input has been superseded by a newer version, or when an
        input is itself stale. Nothing is recalculated here: recalculation is a deliberate act.
        """
        reasons: list[str] = []
        obj = self.objects[uid]
        for inp in obj.derivation.inputs:
            if inp in self.sources:
                continue
            name = self.objects[inp].name if inp in self.objects else inp[:8]
            if self.current_input(inp, uid) != inp:
                reasons.append(f"input '{name}' has a newer version")
            elif self.stale_reasons(inp):
                reasons.append(f"input '{name}' is stale")
        return reasons

    def is_stale(self, uid: str) -> bool:
        return bool(self.stale_reasons(uid))

    def lineage(self, uid: str, depth: int = 0) -> list[str]:
        """The chain of operations back to the source files, one line per step."""
        pad = "    " * depth
        if uid in self.sources:
            src = self.sources[uid]
            return [f"{pad}file {src.filename} (SHA-256 {src.sha256[:12]}…, {src.size:,} bytes)"]
        obj = self.objects[uid]
        lines = [f"{pad}{obj.name} ← {obj.derivation.describe()}"]
        for inp in obj.derivation.inputs:
            lines += self.lineage(inp, depth + 1)
        return lines
