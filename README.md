# POS-Gridder

Surfaces, contours and spatial chance of success for prospect evaluation. A Streamlit
application for the HCWC/GRV/POS workflow: surface import, depth conversion and arithmetic,
closure and spill interpretation, area–depth and GRV, contact distributions from HCWC Builder,
POS mapped as a function of depth, and area/GRV across the contact percentiles. Every layer
records how it was made and can be recomputed from the imported files.

**Status:** Phase 1 of the plan in [`docs/PLAN.md`](docs/PLAN.md) (feasibility results in
[`docs/FEASIBILITY.md`](docs/FEASIBILITY.md)):
- import with a declared domain and sign;
- immutable layers with provenance, version history and stale flags;
- depth conversion (constant velocity, velocity surface, V0 + kZ);
- domain-checked arithmetic and explicit resampling;
- project save/load with a replay check.

Closure and volumes come next.

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
Contour import (GeoPackage, Shapefile, GeoJSON, ASCII) arrives with the contour phase.

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
