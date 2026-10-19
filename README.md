# POS-Gridder

Surfaces, contours and spatial chance of success for prospect evaluation. A Streamlit
application for the HCWC/GRV/POS workflow: surface import, depth conversion and arithmetic,
closure and spill interpretation, area–depth and GRV, contact distributions from HCWC Builder,
POS mapped as a function of depth, and area/GRV across the contact percentiles. Every layer
records how it was made and can be recomputed from the imported files.

**Status:** v1 complete, version 0.3.0 (all phases of the plan, plus the workflow changes in `docs/PLAN.md` §8b) in [`docs/PLAN.md`](docs/PLAN.md) (feasibility results in
[`docs/FEASIBILITY.md`](docs/FEASIBILITY.md)):
- import with a declared domain and sign;
- immutable layers with provenance, version history and stale flags;
- depth conversion (constant velocity, velocity surface, V0 + kZ);
- domain-checked arithmetic and explicit resampling;
- project save/load with a replay check;
- crest and spill candidates, a confirmed closure interpretation (priority-flood fill depth,
  boundary types, explicit acceptance);
- area–depth and GRV for top + base, top + constant thickness and top + thickness surface;
- outline clipping;
- HCWC Builder and SCOPE-HC area–depth export;
- contact distributions from the HCWC Builder CSV (or pasted, typed and edited), with P(G),
  h_min and the apex from the .hcwc.json;
- POS maps for event (a), a column of at least h_min, and event (b), any column, read at the
  fill depth, with every non-POS region labelled;
- typed depth→POS curves;
- area and GRV at each contact percentile;
- JSON result reports;
- contour sets made from a surface or imported (GeoPackage, GeoJSON, zipped Shapefile, ASCII);
- line selection by box or lasso on the map or from a table, with delete and restore;
- surfaces made from contours by thin-plate spline (the default, chosen by the benchmark in
  `docs/BENCHMARK.md`) or linear TIN, as a new layer or a new version of the source surface;
- outlines from closed contours, and GeoPackage export.

The tabs follow the workflow: **1 Start** (reopen the autosaved project, the example, open,
save) → **2 Surfaces** → **3 Contours** → **4 Closure** → **5 Volumes** → **6 Contacts** →
**7 POS & results**, where POS is shown on the structure contours. Every change is autosaved to
`~/.pos-gridder/` (the last three sessions are kept; `POSGRIDDER_AUTOSAVE=off` switches it off).

A progress strip above the tabs shows which steps are done and names the next one; the sidebar
lists everything the project holds, stale results marked. Tab 7 builds a one-page prospect
summary (HTML, opens offline, prints to PDF) with the map, the numbers, every assumption and
warning, and the source files' SHA-256.

The example project (tab 1 Start) makes a synthetic two-dome surface for trying the workflow.
The documents that go with v1:
- [`docs/WORKED_EXAMPLE.md`](docs/WORKED_EXAMPLE.md) — the workflow step by step on real data,
  with the numbers to expect;
- [`docs/SAFEGUARDS.md`](docs/SAFEGUARDS.md) — every known way to get a plausible but wrong
  answer, what the app does about it, and the test;
- [`docs/BENCHMARK.md`](docs/BENCHMARK.md) — why the thin-plate spline is the default for
  contours → surface;
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) — timings on a 51,646-node grid.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Tests:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The `render` marker selects the tests that render the whole app; `-m "not render"` is the quick
subset CI runs on pull requests.

## Surface formats

| Format | Read | Write | Through |
|---|---|---|---|
| ZMAP+ ASCII | ✓ | ✓ | own reader (honours the header's null value) |

v1 keeps to ZMAP+ for grids (decision D8). The IRAP bridge from Phase 0 is in `archive/`.
Contour lines: GeoPackage, GeoJSON, zipped Shapefile and ASCII `x y z id` in; GeoPackage out.

## Conventions

- Grids are regular and unrotated; values are `(nrow, ncol)` with row 0 in the south.
- Depth in m TVDSS, positive down; area in km²; GRV in 10⁶ m³.
- Exceedance percentiles as in HCWC Builder: P100 is the shallowest contact.

## Layout

| path | what |
|---|---|
| `app.py` | the Streamlit shell: sidebar layer list and the tabs |
| `posgridder/core/` | the model and the calculations; no Streamlit import |
| `posgridder/io/` | file formats and, later, the exchange files for the companion apps |
| `posgridder/plotting/` | map figures |
| `posgridder/ui/` | the sidebar and one module per tab |
| `docs/` | the development plan and the feasibility results |
| `feasibility/` | the feasibility scripts and the line-selection prototype |
| `archive/` | code moved out of the package (the xtgeo/IRAP bridge) |
| `tests/` | the suite |

## Companions

Standalone for now. Designed to exchange files with HCWC Builder (contact percentiles in,
area–depth out), WellVolPOS and SCOPE-HC, and to merge with them later.

MIT licence.
