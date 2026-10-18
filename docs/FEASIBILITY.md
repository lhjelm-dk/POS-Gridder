# Feasibility phase — results

*2026-10-09. Phase F of `docs/PLAN.md`. Scripts are in `feasibility/`; numbers below are their
output on this machine (Windows 11, Python 3.12.3).*

**Verdict:** every item is feasible. Two plan details change (F2 and F4), and the D9 and T5–T8
tolerances are now grounded in measurements (F3). Phase 1 can start.

---

## F1 — Clean Windows install of the reduced stack

**Method.** A fresh venv with no system site-packages. `pip install --only-binary=:all:` of the
§6.1 list: numpy, pandas, scipy, plotly, streamlit, contourpy, shapely, geopandas, pyogrio, and
pytest. Then a GeoPackage round trip of a 3-D LineString with a level attribute.

**Result:**
- All packages install from wheels in **73 s**. The venv is 679 MB.
- GeoPackage round trip: OK (level kept, Z kept). GDAL 3.12.4 comes bundled in pyogrio.
- A fresh install resolves **newer majors than the dev venv**: numpy 2.5.3, pandas 3.0.6,
  scipy 1.18.1, plotly 7.1.0, streamlit 1.65.0, contourpy 1.4.0, shapely 2.2.0, geopandas 1.2.0,
  pyogrio 0.13.0.
- The Phase 0 suite on these versions: **15 passed, 1 skipped, 2 failed**. The two failures are
  the IRAP round trips (no xtgeo), which is expected under D8. The app render tests pass on
  Streamlit 1.65.

**Consequence.** No install risk for v1. CI installs the newest versions, the dev venv has older
ones, and both pass, so the floors in `requirements.txt` stay as they are without ceilings.

## F2 — Selecting contour lines on the Plotly map in Streamlit

**Method.** Prototype `feasibility/f2_line_selection.py`. Each contour line is its own scatter
trace, with its line id in `customdata`. The map uses
`st.plotly_chart(on_select="rerun", selection_mode=("points", "box", "lasso"))`. It was driven in
the browser pane.

| Trace style | Hover shows the line | Box select returns line ids | Single click returns line ids |
|---|---|---|---|
| `lines` only | yes | **no** | no |
| `lines+markers` | yes | **yes** (ids 2–8 for a box across 7 lines) | no |
| `lines+markers`, markers at opacity 0 | yes | **yes** (same ids); the map looks like plain lines | no |

**Not settled by automation:**
- **Single click.** It returned nothing under synthetic clicks in both modes. It may still work
  with a real mouse.
- **Lasso.** It cannot be drawn with a straight synthetic drag.

Both need a 1-minute manual check: run the prototype, then click and lasso.

**Consequence for the plan:**
- Contour traces carry invisible markers at their vertices.
- Selection is by box, plus lasso if the manual check confirms it.
- **Fallback, always available:** select by level or line id from a table (`st.dataframe`
  selection). This needs no map events.
- Selected markers are highlighted by Plotly. The selected-marker style needs setting so that
  selected lines read clearly.

## F3 — Area and GRV accuracy against analytic answers (sets the T5–T8 bounds)

**Method.** `feasibility/f3_area_grv_convergence.py`:
- A paraboloid `z = z0 + 1e-4·r²` and a cone `z = z0 + 0.1·r`.
- Contact 100 m below the crest. The closure radius is 1000 m in both cases.
- Thickness 50 m for the top+thickness case.
- Relative errors as the cell size halves:

| Case | Cell (m) | Area, polygon (contourpy + shapely) | Area, node count | GRV direct | GRV trapezoid (1 m table) | GRV top+thickness, direct |
|---|---|---|---|---|---|---|
| paraboloid | 100 | −3.2e-3 | +9.0e-3 | −1.3e-3 | −6.7e-3 | −5.9e-4 |
| paraboloid | 50 | −8.0e-4 | +2.9e-4 | −1.6e-4 | −1.7e-3 | −6.1e-5 |
| paraboloid | 25 | −2.0e-4 | −3.1e-4 | −1.6e-5 | −4.2e-4 | −3.1e-7 |
| paraboloid | 12.5 | −5.1e-5 | −1.3e-3 | −6.4e-6 | −1.0e-4 | −1.0e-5 |
| cone | 100 | −2.2e-3 | +9.0e-3 | −7.3e-4 | −6.0e-3 | −1.4e-4 |
| cone | 50 | −5.2e-4 | +2.9e-4 | −9.0e-5 | −1.5e-3 | +1.5e-6 |
| cone | 25 | −1.3e-4 | −3.1e-4 | −8.2e-6 | −3.4e-4 | +3.4e-6 |
| cone | 12.5 | −3.3e-5 | −1.3e-3 | −4.3e-6 | −4.7e-5 | −3.8e-6 |

**Findings:**
- Polygon area is second order: the error falls about 4× per halving. It is always slightly low,
  because linear interpolation cuts inside a convex contour.
- **Node-count area does not converge** (+9e-3, +3e-4, −3e-4, −1.3e-3). This confirms the plan's
  choice of polygon area. Node count is kept only as a coarse check.
- Direct GRV is the most accurate route. The trapezoid route inherits the polygon-area bias, so
  at 10 cells across the closure radius the two differ by about 0.5 %.

**Tolerances adopted** (written as cells per closure radius, `n = R/h`, so they transfer to
other grids):

| Quantity | Tolerance |
|---|---|
| Polygon area | ≤ 0.5 % for n ≥ 10; ≤ 0.1 % for n ≥ 20 |
| Direct GRV | ≤ 0.2 % for n ≥ 10 |
| Agreement check, direct vs trapezoid GRV (§5.6) | 1 %. A warning appears when the closure spans fewer than 10 cells in radius |
| Convergence tests (T5–T8) | Error ratio ≥ 3 per halving, for the polygon area and the trapezoid |

On the GEUS grid (250 m cells) a closure of 2.5 km radius has n = 10. The bounds above apply
there, and smaller closures get the warning.

## F4 — Contours → surface: speed and a first look at accuracy

**Method.** `feasibility/f4_gridding_timing.py`:
- A synthetic two-dome surface on the GEUS geometry (217 × 238 nodes at 250 m).
- Contoured at 10 m, vertices resampled along the lines, then regridded.
- RMS and max error are measured inside the data hull.

| Vertices along lines every | Points | Method | Time (s) | RMS (m) | Max (m) |
|---|---|---|---|---|---|
| 125 m | 63,031 | linear TIN | 1.1 | 0.38 | 7.2 |
| 125 m | 63,031 | thin-plate, 30 neighbours | 1.4 | 0.85 | 8.5 |
| 125 m | 63,031 | thin-plate, 60 neighbours | 4.3 | 0.45 | 8.0 |
| 125 m | 63,031 | thin-plate, 150 neighbours | 22.3 | 0.16 | 2.5 |
| 60 m | 131,235 | linear TIN | 2.6 | 0.38 | 7.2 |
| 60 m | 131,235 | thin-plate, 30 neighbours | 1.3 | 1.48 | 8.6 |
| 60 m | 131,235 | thin-plate, 60 neighbours | 3.9 | 0.88 | 8.5 |
| 60 m | 131,235 | thin-plate, 150 neighbours | 22.4 | 0.31 | 7.2 |

**Findings:**
- **Both methods are fast enough.** At most 22 s on more than 130 k points.
- **A global thin-plate spline is not an option at this size.** Its dense matrix would need
  63 k² × 8 bytes ≈ 32 GB. The local, neighbour-based form is required.
- **Local thin-plate behaves badly with small neighbourhoods.** The nearest points all lie on one
  contour line, so the local fit is poorly conditioned across lines. Denser vertices along the
  lines make this worse, not better: at 30 neighbours RMS goes from 0.85 to 1.48 m.
- **The plan's "densify to about half a cell" is wrong for thin-plate.** It is replaced by:
  vertices at about one cell spacing, and at least 150 neighbours.
- **Max errors of 7–9 m sit at the crests**, inside the innermost contour. That is case C7: the
  data says nothing there. The D9 max-error rule must exclude the area inside the innermost
  contour, as §7.2 already intends ("between contours").

**Consequence.** Linear TIN becomes the working default until the D9 benchmark decides. It is
accurate, fast, and never overshoots. Thin-plate stays a candidate with k ≥ 150; it was the most
accurate here, at 0.16 m RMS.

## F5 — A real HCWC Builder export as a fixture

**Method.** `feasibility/f5_builder_fixture.py` runs the Builder's own engine on the limit set
stored in `HCWC builder/reference/defaults/example_prospect_spill.hcwc.json` (h_min = 120 m),
with its default 10,000 trials and seed. It writes the tab 7.0 export exactly as shipped, an
unconditioned table, and reference values to `tests/fixtures/hcwc_builder/`.

**Reference values:**
- P(G) from `inputs` = **0.4082**.
- F(h_min) = **0.8891**.
- Apex median 2049.99 m (P1–P99: 2049.0–2051.0).
- Conditioned contacts at exceedance P90 / P50 / P10: 2182.5 / 2217.2 / 2266.3 m.

**C1 confirmed on real Builder output.** Using P(G) without F(h_min) would overstate POS by
1/0.8891, i.e. **+12.5 %** for this prospect.

**Event equivalence confirmed** (plan §5.8, T27):

| z (m) | F·E_min(z) (event a) | E_all(z) (event b) | Difference |
|---|---|---|---|
| 2100 (band) | 0.8891 | 1.0000 | −0.111 |
| 2150 (band) | 0.8891 | 0.9712 | −0.082 |
| 2180 | 0.8194 | 0.8195 | −0.0001 |
| 2200 | 0.6322 | 0.6320 | +0.0001 |
| 2250 | 0.1694 | 0.1697 | −0.0003 |
| 2300 | 0.0191 | 0.0197 | −0.0006 |

Deeper than apex + h_min (2170 m) the two events agree to within 0.0006. That is
percentile-interpolation noise, within the §5.7 bound of 0.015. Inside the band they differ by
up to 0.11.

**Finding about HCWC Builder (not this repository).** In `example_prospect_spill.hcwc.json`, the
`resolved` block is named "Tofte North (worked example)" while `inputs.prospect_name` is "Vestre
Low (spill-limited example)", and `min_column_input` (100) differs from `resolved.min_column_m`
(120).
- The `resolved` copy can be stale relative to `inputs`.
- **POS-Gridder therefore computes P(G) from `inputs` only** (the product of `play_* × cond_*`).
  It never uses `resolved` for anything that matters.
- The fixture was generated from `resolved`. Its F(h_min) therefore belongs to the 120 m case,
  and that is what it is labelled as.

---

## Changes to the plan from this phase

1. §5.4: contour vertices at about one cell spacing (not half a cell). Thin-plate uses k ≥ 150
   neighbours. Linear TIN is the working default until the D9 benchmark.
2. §5.6 / T5–T8: tolerances as in the F3 table, expressed as cells per closure radius. The
   direct-vs-trapezoid agreement check is 1 %, with a warning below 10 cells radius.
3. §5.7: P(G) from `.hcwc.json` `inputs` only, never from `resolved`.
4. §6.4 / Phase 4: contour selection is box (and lasso, if confirmed) on invisible markers, with a
   table-based fallback.
5. Requirements: floors unchanged. The stack runs on the newest releases (pandas 3, Plotly 7,
   Streamlit 1.65).

## Open items from this phase

- **Manual check (1 minute):** single click and lasso on contour lines in the F2 prototype:
  `streamlit run feasibility/f2_line_selection.py`. Box selection was confirmed again in the
  real app in Phase 4 (tab 6.0: a box returned two lines, which were then deleted).
- **Builder example-file inconsistency** (`resolved` vs `inputs`), to be fixed in HCWC Builder.
