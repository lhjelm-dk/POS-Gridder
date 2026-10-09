"""Every kind of object a project holds, by its ``kind`` tag (used by the project file)."""
from __future__ import annotations

from posgridder.core.closure import Closure
from posgridder.core.hcwc import ContactDistribution, PosCurve
from posgridder.core.model import Surface
from posgridder.core.outline import Outline
from posgridder.core.pos import PercentileVolumes, PosMap
from posgridder.core.volumes import VolumeResult

KINDS: dict[str, type] = {cls.kind: cls for cls in (
    Surface, Closure, Outline, VolumeResult, ContactDistribution, PosCurve, PosMap,
    PercentileVolumes)}
