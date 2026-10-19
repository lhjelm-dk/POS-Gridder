"""Where a project stands in the workflow: which steps are done, and what comes next.

A step is done when the project holds a current object that completes it. The structure step
is done by a depth surface made any way — imported, depth-converted or made from contours.
"""
from __future__ import annotations

from dataclasses import dataclass

from posgridder.core.model import Project


@dataclass(frozen=True)
class Step:
    label: str
    done: bool
    tab: str
    hint: str


def status(project: Project) -> list[Step]:
    def has(kind, test=lambda o: True):
        return any(test(project.objects[u]) for u in project.current(kind))

    return [
        Step("Surface", has("surface"), "1 Start or the sidebar",
             "import a surface in the sidebar, or load the example on tab 1 Start"),
        Step("Depth", has("surface", lambda s: s.domain == "depth"), "2 Surfaces or 3 Contours",
             "convert time to depth on tab 2 Surfaces, or make a depth surface from contours on "
             "tab 3 Contours"),
        Step("Closure", has("closure"), "4 Closure", "confirm a closure on tab 4 Closure"),
        Step("Volumes", has("volumes"), "5 Volumes", "calculate area and GRV on tab 5 Volumes"),
        Step("Contacts", has("hcwc") or has("poscurve"), "6 Contacts",
             "import or paste a contact distribution, or type a POS curve, on tab 6 Contacts"),
        Step("POS", has("posmap"), "7 POS & results", "map POS on tab 7 POS & results"),
    ]


def next_step(steps: list[Step]) -> Step | None:
    return next((s for s in steps if not s.done), None)


def stale(project: Project) -> list[str]:
    """Names of the current objects that are stale."""
    return [project.objects[u].name for u in project.layers if project.is_stale(u)]
