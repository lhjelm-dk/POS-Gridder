# Archive

Code moved out of the package rather than deleted.

- `xtgeo_bridge.py` — conversion between POS-Gridder surfaces and `xtgeo.RegularSurface`, which
  gave IRAP classic/binary import and export in Phase 0. Removed from v1 by decision D8
  (`docs/PLAN.md` §0). The plan's IRAP formats can be restored from here, together with the
  `irap_ascii`/`irap_binary` entries that `posgridder/io/surfaces.py` held at commit `b2266aa`.
  It targets the Phase 0 `Surface` (mutable, with `provenance`); restoring it needs the import
  to go through `posgridder.io.surfaces.import_surface`, so the source file is kept.
