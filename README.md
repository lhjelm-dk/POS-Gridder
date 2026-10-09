# POS-Gridder

Surfaces, contours and gridded chance of success for prospect mapping. A Streamlit application
with Petrel- and QGIS-style tools: surface import and arithmetic, depth conversion, contouring
and contour editing, closure and GRV, POS attributes on contours, gridding of POS (including a
convergent interpolation), and import of contact distributions from HCWC Builder.

**Status:** Phase 0 of the plan in [`docs/PLAN.md`](docs/PLAN.md): surface import, layer list,
map view and export. The other tools follow phase by phase.

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
| IRAP classic ASCII | ✓ | ✓ | xtgeo |
| IRAP binary | ✓ | ✓ | xtgeo (float32 values) |

CPS-3, GeoTIFF and XYZ points are planned for Phase 1.

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
| `docs/` | the development plan |
| `tests/` | the suite |

## Companions

Standalone for now. Designed to exchange files with HCWC Builder (contact percentiles in,
area–depth out), WellVolPOS and SCOPE-HC, and to merge with them later.

MIT licence.
