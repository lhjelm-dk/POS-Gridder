# POS-Gridder — Revised v1 plan (critical review of draft 3)

*Draft 4, 2026-10-09; feasibility results folded in (see `docs/FEASIBILITY.md`). A critical review of draft 3 (archived as `docs/archive/PLAN_draft3.md`),
with the user's decisions D1–D9 recorded in §0 and §9. No implementation has started from this
plan.*

## 0. Decisions recorded (2026-10-09)

| # | Decision | Effect on the plan |
|---|---|---|
| D1 | **Both POS events** can be mapped: "HC with column ≥ h_min" and "any HC column" | Two event types in §5.8. Each map is labelled with its event |
| D2 | **F(h_min) both ways:** typed, or read from a Builder file when one carries it | Typed now. Reading it needs a Builder change, which is a cross-repository item (§9) |
| D3 | **Both anchorings; default "as is"** (absolute contact depths) | Re-anchoring to the map crest is an option. The apex difference is always reported |
| D4 | **The basis comes from the import.** A 101-percentile table can also be pasted, typed or edited in the app | §5.7: basis from the file, else declared. A table editor with the same validation |
| D5 | **Reviewed against HCWC Builder.** It has no contour or geometry import; its only map interface is the area–depth CSV (`depth_m, top_area_km2, base_area_km2`, loose aliases, `#` comments, apex row at zero area, base optional) | Contours come in as GeoPackage/Shapefile/GeoJSON lines with a level attribute (or Z), or as ASCII `x y z line_id`. The Builder's area–depth CSV is read and written exactly (§5.3, §5.10) |
| D6 | **Typed POS-per-contour curves can be mapped either way:** as total POS or as conditional on G (× P(G)) | Each typed curve carries a declared meaning (§5.8) |
| D7 | **Thickness is vertical** (isochore) | No dip correction. Stated on every GRV result |
| D8 | **xtgeo and IRAP removed for now** | ZMAP+ is the only grid format in v1. The IRAP bridge code is moved to an archive folder, not deleted |
| D9 | **Thresholds set by the developer** (this plan) | The values are in §7.2, with their justification |


**Labels used throughout.** **[Fact]** means established from the repository or the sibling apps'
code, with the file named. **[Plan]** means stated in the existing plan. **[Rec]** is an
engineering recommendation. **[Verify]** is an assumption to verify before relying on it.

**Correction to the brief.** The brief says no code exists. **[Fact]** Phase 0 is already
committed (`b2266aa`, pushed to `lhjelm-dk/POS-Gridder`, private). It contains:
- a `Surface`/`Project` model;
- its own ZMAP+ reader and writer, verified against the GEUS grid;
- IRAP via xtgeo;
- a sidebar layer list and a map tab;
- 18 tests.

This review treats Phase 0 as existing work, to be kept, retrofitted or removed. §6.3 lists the
retrofits.

---

## 1. Executive assessment

**What is strong in the current plan**
- The calculation core is kept separate from Streamlit. It is testable and mirrors the sibling apps.
- The surface-guided POS idea is in the plan ("Mode A": POS as a function of local depth). It is
  the right core of the method.
- It identifies HCWC Builder's exceedance convention (P100 = shallowest) and the risk of reversing it.
- It recognises that area–depth exchange with HCWC Builder and SCOPE-HC closes a useful loop.
- It is honest that "convergent" would only be a Petrel-like approximation.

**What is over-scoped or weakly justified**
- **Six POS gridders plus a custom convergent default.** Gridding POS directly is the wrong tool
  when POS is a function of depth (§2, C6). The custom convergent algorithm has no demonstrated
  requirement and no reference to validate it against.
- **Seven grid formats with import and export.** The only real data is one ZMAP+ grid. The user
  has no Petrel, so Petrel-specific formats have no consumer.
- **A free expression calculator and automatic resampling.** These are general-GIS features that
  create silent domain, unit and alignment errors (C9, C10).
- **The dependency list.** It includes xarray, verde, pykrige, pyproj and streamlit-folium, none
  of which a v1 workflow needs.
- **Graphical contour editing** is planned without any check that Streamlit can do it (C12).
- **"101 contours from the HCWC distribution."** These are unnecessary: POS and HCWC-dependent
  area/GRV follow directly from the distribution. Contours at chosen percentiles are a display
  item only.

**Biggest risks (detail in §2)**
1. **The POS formula in the plan is wrong for the file HCWC Builder actually exports.** The
   export contains only realisations whose column reaches the assessment minimum. `P(G) ×
   exceedance` then overstates POS by the factor `1/F(h_min)`. *(Critical)*
2. **Prior and posterior can be mixed.** A given-DHI contact distribution combined with a prior
   P(G) read from `.hcwc.json` gives a number that runs without error and means nothing. *(Critical)*
3. **Anchoring mismatch.** Builder contacts are *sampled apex + column*, while the map crest is
   fixed. A difference between the two shifts every POS value. *(High)*
4. **Spill interpretation defaults.** The plan treats the grid edge and nulls as spill by default,
   which contradicts the requirement for explicit confirmation. It also ignores connectivity and
   node-quantisation effects. *(High)*

---

## 2. Critical findings

Sorted by severity. Each entry gives the finding, the evidence, and why it matters.

### Critical

**C1. POS ignores the assessment-minimum conditioning of the Builder export.**
- **Evidence.** **[Fact]** `HCWC builder/hcwc/ui/export.py`: `samples = result.contact_m[result.above_minimum]`,
  with the caption "h ≥ h_min only". `hcwc/core/pos.py`: Prospect POS = `P(G) × F(h_min)`, where
  `F(h) = P(H ≥ h | G)`.
- **The error.** The exported table describes `C | G, H ≥ h_min`, not `C | G`. The plan computes
  `P(G) × P(C > z | G, H ≥ h_min)`. That omits `F(h_min)` and so inflates POS. With `F(h_min) = 0.7`,
  every POS value is 43 % too high.
- **Consequence.** It cannot be detected from the numbers, and it is exactly the "right code, wrong
  convention" failure the brief warns about.
- **Two consistent definitions exist.** Choosing between them is decision **D1**:
  - Map the event "HC present at (x, y) **and** the accumulation meets the minimum column":
    `P(G) · F(h_min) · P(C > s(x,y) | G, H ≥ h_min)`. This works with today's export, but needs `F(h_min)`.
  - Map the event "any HC column at (x, y)": `P(G) · P(C > s(x,y) | G)`. This needs the unconditioned
    distribution, either a Builder run with `h_min = 0` or a new Builder export.
- **[Fact]** `.hcwc.json` holds inputs only: `play_*`, `cond_*`, `min_column_input`, `apex_p1/p99`
  and the limit PERTs. P(G) can be computed from it (the product of `play × cond`). **F(h_min)
  cannot**; it is an engine result. The plan's "read P(G) from `.hcwc.json`" therefore covers only
  half of the multiplier.

**C2. Prior/posterior mixing (DHI basis).**
- **Evidence.** **[Fact]** The Builder exports either a *geological* or a *given-DHI* table. Inside
  the CSV both are just `Percentile, Value`. The basis appears only in the filename
  (`hcwc_percentiles_<basis>.csv`) and in the on-screen provenance line.
- **The error.** A given-DHI table pairs with `P(G | s)`. A `.hcwc.json` gives the prior P(G).
  Combining a posterior contact distribution with a prior P(G), or the reverse, is wrong and nothing
  detects it.
- **[Rec]** The importer requires an explicit basis declaration, pre-filled from the filename when
  possible and never defaulted. P(G) from `.hcwc.json` is offered only on the geological basis.
  Whether v1 supports the DHI basis at all is decision **D4**.

### High

**C3. Apex anchoring.**
- **Evidence.** **[Fact]** `hcwc/core/engine.py`: `HCWC = apex + h`, with the apex drawn from its own
  distribution (example: P1/P99 at 2049/2051 m).
- **The problem.** The map's crest is a fixed node depth. If the Builder apex came from a different
  depth conversion or interpretation, the absolute contact depths are inconsistent with the map.
  Every POS value then shifts.
- **[Rec]** Always compare the map crest with the Builder apex (from `.hcwc.json` when it is
  supplied), and warn above a stated tolerance.
- **Choosing the treatment is decision D3.** Either use the absolute contacts as exported, or
  re-anchor them as `C_map = crest_map + (C − apex_median_builder)`.

**C4. The spill interpretation contradicts the requirements and ignores grid effects.**
- **[Plan]** "Touching a null area or the grid edge counts as spilling (default yes)." This
  contradicts requirement 2.3. **[Rec]** The model edge and nulls become *candidate* boundary
  types that require confirmation.
- **Additional failure modes the plan does not cover:**
  - (a) **4- vs 8-connectivity.** With 4-connectivity, a saddle through a cell corner is missed and
    a false closure results. 8-connectivity is the conservative choice.
  - (b) **Node quantisation.** The spill depth is only resolved to node values. The error is up to
    about half a cell times the dip at the saddle: on a 250 m grid at 2°, roughly 4–9 m.
  - (c) **Noise minima.** Small minima create spurious crests and tiny closures, so a minimum
    closure height and area are needed.
  - (d) **Shared saddles.** Multiple culminations behind one saddle mean the local and the combined
    closure differ.
  - (e) **Wrong domain or sign.** A negative-down or time surface makes the deepest point the "crest".
  - (f) **Interior null holes** inside a closure.
  - (g) **Flat crests or plateaus** (ties).
  - (h) **Lowest closing contour.** Taken from contours, it is quantised to the contour interval
    and so biases the spill shallow by up to one interval.

**C5. The Builder's spill is uncertain; the map's spill is fixed.**
- **Evidence.** **[Fact]** In the example, "Closure / spill point" is a depth PERT (2190–2212 m).
- **The problem.** Contacts deeper than the confirmed map spill cannot exist on the fixed map
  structure.
- **[Rec]**
  - For POS this changes nothing inside the trap, which is filled anyway.
  - For area and GRV, cap the contact at the map spill and report the probability mass
    `P(C ≥ spill_map)` as the fill-to-spill probability.
  - Warn when the Builder's spill range and the map spill differ by more than a stated tolerance.

**C6. Gridding POS directly is unnecessary and unsafe.**
- **[Plan]** "Mode B" interpolates POS spatially from attributed contour points, with six gridders.
- **Why it is unsafe.** Spatial interpolation of a probability can overshoot [0, 1], break
  monotonicity with depth, and disagree with the depth it is meant to represent.
- **[Rec]** When only contours exist, interpolate **depth** from the contours (one method, §3),
  then apply the same POS function of depth. This meets the user's wish that POS "follow the
  depths of the surface", works from contours alone, and gives one calculation rule for both
  workflows (requirement 2.2).

**C7. In the contour-only workflow the crest is undefined.**
- **The problem.** Inside the innermost contour there is no data.
  - Linear TIN gives a flat top at the innermost level, so relief and GRV are underestimated.
  - Thin-plate spline extrapolates a dome whose height depends on the method. Crest depth sets the
    top of every GRV.
- **[Rec]**
  - Optional crest input (a point with depth).
  - Report the crest's origin: data, TIN plateau or spline extrapolation.
  - A benchmark that measures crest, spill and GRV error by method (§7).

**C8. GRV with top and base: the plan's area–depth-only approach hides footprint errors.**
- **The convention.** The Builder and SCOPE-HC integrate `A_top(z) − A_base(z)`. This equals the
  true volume only if `A_base` is measured over the **same trap footprint** and `base ≥ top`
  everywhere.
- **The problem.** An independently computed base closure (its own crest or spill) gives a wrong
  volume without any error.
- **[Rec]**
  - Compute GRV by direct column integration on the grid as the primary value.
  - Produce the area–depth table as an exchange product, with `A_base` restricted to the top footprint.
  - Require the two to agree within a stated tolerance.
  - Flag negative thickness, base null where top is valid, and partial coverage.

### Medium

**C9. Domain and unit safety.**
- **Evidence.** **[Fact]** The Phase 0 import form defaults the domain to "depth" and sets the unit
  from the domain. Importing the GEUS file without changing it labels TWT in milliseconds as depth
  in metres.
- **[Plan]** A free-form calculator (`A - B`) with no domain rules.
- **[Rec]** No default domain: the user must choose. Arithmetic follows a small domain table (§5.1),
  and anything outside it is refused.

**C10. Automatic resampling to a reference grid.**
- **The problem.** Resampling smooths values, moves null boundaries, and can shift a 250 m grid
  against a 50 m grid.
- **[Rec]**
  - Identical geometry is required by default.
  - Resampling is a separate, explicit step: target grid and method (nearest or bilinear) are
    shown, and the output is a new derived surface with provenance.

**C11. No contour import is specified.**
- **The problem.** The contour-first workflow is a requirement, but the plan names no format for
  contours that arrive from elsewhere. It lists only grid formats.
- **Consequence.** The contour workflow cannot start. This is decision **D5**.

**C12. The interactive editing assumptions are unverified.**
- **[Verify]** `st.plotly_chart(on_select=…)` returns selected *points*, with curve and point
  indices. Whether click or lasso reliably selects line-only traces (contours) is unverified.
- **Drawing and dragging vertices** is not available through native Streamlit or Plotly selection
  events. **[Rec]** Plan only for select → delete in v1. Anything more is done in QGIS and
  re-imported (§3).

**C13. Over-scoped dependencies and formats.**
- Each heavy package adds Windows install and CI risk.
- **[Fact]** xtgeo 4.26 installed cleanly on Windows / Python 3.12. Phase 0 already uses it for IRAP.
- **[Verify]** verde's and pykrige's dependency trees; whether pygmt would need a separate GMT
  installation.
- Recommendation in §6.

**C14. Provenance and staleness are not designed.**
- **Evidence.** **[Fact]** The Phase 0 `Surface` is mutable. Flip-sign rewrites the imported
  values in place, and only a free-text provenance string remains. No input file hash is stored.
- **Consequence.** Requirements 2.2 and 2.8 cannot be met by adding fields later; objects need to
  be immutable, with recorded derivations, from the start (§6.2).

**C15. HCWC percentile semantics are unspecified.**
- **[Fact]** Default tail truncation at P99.5/P0.5 (`hcwc/io/geox.py`). The header is `Value` in
  the code, while the docstring mentions `Depth(m)`.
- **What the plan leaves open:**
  - interpolation between percentiles;
  - duplicated depths (point masses, e.g. contacts piling up at a spill or fault limit);
  - behaviour outside the table's range;
  - the strict versus non-strict inequality at `C = z`.
- Defined in §5.7.

**C16. Closure computed in the time domain.**
- **The problem.** Closure and spill in TWT differ from closure and spill in depth wherever
  velocity varies laterally.
- **[Rec]** Closure, GRV and POS run on depth surfaces only. A time surface can be previewed but is
  labelled as such.

**C17. No faults.**
- **The problem.** Fault-dependent traps cannot be represented in v1. Outlines are not spill
  barriers, by decision. A confirmed manual spill depth helps, but if the structure is not
  geometrically closed at that depth, the footprint runs to the model edge.
- **[Rec]** Flag this explicitly. Faults are deferred; the consequence is stated in §4.

### Low

**C18. Thickness definition.**
- Constant or gridded thickness is applied vertically (isochore). True stratigraphic thickness
  (isopach) differs by `1/cos(dip)`: about 1.5 % at 10° dip.
- **[Rec]** Treat thickness as vertical and state it. A user decision is needed only if isopachs
  are expected (**D7**).

**C19. Node versus cell registration.**
- **[Fact]** ZMAP+ is node-registered. GeoTIFF is usually pixel-is-area, so a half-cell shift
  matters when it is added.
- **[Rec]** One convention: node-registered, each node standing for an `xinc × yinc` cell.
  Conversion happens at the format boundary.

**C20. CRS is free text.**
- **[Rec]** v1 does no reprojection. Surfaces whose stated CRS differ are refused together. A
  missing CRS is a warning, not an error.

---

## 3. Alternative approaches

| Question | Options | Trade-off | Recommendation |
|---|---|---|---|
| **Overall shape** | (a) Build every tool in the app (current plan). (b) **Hybrid:** QGIS for drawing and editing vector geometry, POS-Gridder for the geological calculations. (c) Notebook or scripts only | (a) Costly, and Streamlit editing is weak. (b) QGIS is mature and free, and exchange through GeoPackage is simple. (c) No UI for confirmation steps | **(b)**: geometry editing in QGIS; interpretation, confirmation, calculation and provenance in POS-Gridder |
| **POS** | (a) Grid POS spatially from attributed points. (b) **POS = f(fill depth)**, evaluated on a depth surface | (a) Breaks bounds and monotonicity and duplicates interpolation. (b) Exact, monotone and bounded by construction | **(b)**, for both workflows |
| **Contours → surface** | Custom convergent; scipy `RBFInterpolator` thin-plate spline; scipy linear TIN; verde spline; pygmt `surface` (minimum curvature with tension, Smith & Wessel); kriging | Convergent: no reference to validate it, development cost. TPS: smooth, established, can overshoot. TIN: honours data, never overshoots, flat-triangle and plateau artefacts. verde: TPS-like with extra dependencies. pygmt: an established minimum-curvature method, but **[Verify]** a heavy install on Windows. Kriging: needs variogram judgement | **TIN plus TPS (both scipy)**, benchmarked by their effect on crest, spill, area and GRV. Pick the default from the benchmark. Defer the rest |
| **Closure / spill** | (a) Lowest closing contour. (b) Repeated threshold-and-label (`scipy.ndimage.label`) with bisection. (c) **Priority-flood from the crest**, giving a fill-depth surface `s(x,y)` | (a) Quantised to the contour interval. (b) Simple and established, but one labelling per tested level and no per-node fill depth. (c) One pass; exact at node level; gives spill candidates, sub-culminations, area–depth and POS from a single field | **(c)**, a standard algorithm (Barnes et al. 2014 family). Use (b) as an independent check in the tests |
| **GRV** | (a) Area–depth trapezoid. (b) **Direct column integration** on the grid | (a) Needed for exchange; hides footprint errors. (b) Exact for the gridded geometry and checks (a) | **(b) primary, (a) exported, with a mandatory agreement check** |
| **Area/GRV across HCWC percentiles** | (a) Monte Carlo. (b) **Monotone transform** of the contact percentiles | GRV(c) does not decrease as c deepens, so `GRV_P = GRV(c_P)` exactly (with ties, plateaus and the spill cap handled). No sampling noise | **(b)** |

---

## 4. Recommended v1 scope

**The v1 workflow:** import → prepare (domain, sign, depth conversion) → candidate closures →
**confirm** interpretation → area–depth and GRV → import HCWC and the multiplier → POS map →
area/GRV per percentile → export with provenance. The contour workflow joins at "prepare", through
contours → depth surface.

### 4.1 Included in v1

| Feature | What it enables | Essential | Main risk | Acceptance (detail in §7) | Depends on |
|---|---|---|---|---|---|
| ZMAP+ grid read/write *(done)* | The real data | Yes | Header variants | GEUS exact; round trip | – |
| Domain, unit and sign declared at import; immutable originals | Safe calculations | Yes | User friction | GEUS cannot be used as depth without an explicit conversion | model |
| Provenance and derivation records; stale flags | Reproducibility (2.8), editing rules (2.2) | Yes | Over-design | A changed input marks dependents stale; a reload reproduces identical results | model |
| Depth conversion: constant V, V0+kZ, average-velocity grid | Real data is TWT | Yes, for the GEUS-type inputs | Datum assumptions | Analytic values | domain rules |
| Limited arithmetic (A±B, A×k, A+k, clip) with a domain table; explicit resampling | Thickness = base − top; corrections | Yes | Domain leaks | Refusal tests | alignment rules |
| Candidate crests and spills (priority-flood), **confirmation**, boundary types | Closure interpretation (2.3) | Yes | Saddle and edge misclassification | Synthetic saddles, edges and holes | depth surface |
| Area–depth (sub-cell, from contouring the fill-depth surface) | Exchange, volumes | Yes | Discretisation | Paraboloid and cone, with convergence | closure |
| GRV: top+base, top+constant thickness, top+gridded thickness; direct integration with area–depth cross-check | Volumes (2.4) | Yes | Footprint mismatch | Analytic; agreement check | closure, arithmetic |
| HCWC CSV import (basis, order, tails, duplicate depths) plus multiplier inputs (P(G), F(h_min)); 101-row table editor (paste, type, edit) | Core (2.1) | Yes | C1–C3 | Synthetic distributions; T26 | – |
| Builder area–depth CSV import (map-free percentile area/GRV) | Map-free evaluation, round-trip check | Useful, low cost | Column aliases | T25 | – |
| POS maps for both events (D1), with region categories and anchoring options (D3) | Core output | Yes | Semantics | Bounds, monotonicity, crest value; T27 | closure, HCWC |
| Area/GRV at each percentile (monotone transform), spill mass reported | Area/GRV vs percentile | Yes | Spill capping | Analytic | GRV, HCWC |
| Typed depth→POS curves (e.g. 2300 m → 24 %), each declared total or conditional (D6) | The user's original request; works without HCWC | Useful, low cost | Mislabelled meaning | Same tests as HCWC | POS |
| Contour display with interval, start and stop; extract a level as polygons with area; export GeoPackage | Contour view, QGIS exchange | Yes | – | Areas match area–depth | contourpy, shapely |
| Contour import (format per **D5**); select → delete; contours → surface (TIN, TPS) as an explicit reconciliation | Contour workflow (2.2) | Yes | C7, C11, C12 | Benchmark | vectors |
| Outline polygon (import) clipping area and GRV; outside shown as "not evaluated" | Boundary area | Yes | Conflated with spill | Clip tests | vectors |
| Exports: area–depth CSV in Builder and SCOPE-HC column sets, POS and derived grids as ZMAP+, results report (CSV/JSON) | Exchange, reproducibility | Yes | Column drift | Fixture files | all |
| Project save/load (manifest + arrays) | Reproducibility | Yes | Integrity | Hash-identical recompute | provenance |

### 4.2 Deferred, with the consequence of deferring

| Feature | Consequence of deferring |
|---|---|
| IRAP (removed by D8), CPS-3, GeoTIFF, XYZ points as grids | Only ZMAP+ grids move in and out. **[Verify]** that the user's other software (ZIMS/GEUS, and Petrel if it ever appears) reads ZMAP+. The archived IRAP bridge can be restored if needed |
| Additional gridders (kriging, IDW, Clough-Tocher, verde, pygmt) | One fewer comparison. The benchmark shows whether any adds value |
| Custom convergent interpolation | Nothing is lost as long as TIN/TPS pass the benchmark. Revisit only on a documented failure |
| In-app digitising and vertex editing | Edits are made in QGIS and re-imported. That is slower for small fixes, but reliable |
| Faults as barriers | Fault-dependent traps are handled only through a manual spill with a visible warning (C17) |
| Structural uncertainty (depth-conversion and surface uncertainty) | POS reflects HCWC uncertainty only, as decided for v1. The POS map must say so |
| Well ties and residual correction in depth conversion | Depth conversion is a stated assumption, not a calibrated model |
| Reprojection and basemap | Data must share a CRS |
| DHI basis (if not chosen under D4) | Only geological-basis POS |
| Shared package or merge with HCWC Builder, WellVolPOS, SCOPE-HC | File exchange only, which is enough for v1 |

### 4.3 Removed

| Removed | Reason |
|---|---|
| POS "Mode B" (gridding POS points) with six algorithms | Replaced by POS = f(depth) on a contour-derived surface (C6) |
| Convergent as the default | No requirement or reference justifies it (2.5) |
| 101 HCWC contours as objects | Unnecessary. Percentile contours are drawn on request for display |
| Free-form expression parser | Replaced by a small domain-checked set of operations (C9) |
| Automatic resampling | Replaced by an explicit resampling step (C10) |
| Outline as an "outside = 0 %" boundary | Conflates an area boundary with probability; outside the outline is "not evaluated" |
| Spill at edge or null "by default" | Contradicts 2.3 (C4) |
| xarray, verde, pykrige, pyproj, streamlit-folium in v1 | Unused by the v1 workflow |

---

## 5. Calculation contracts

**Conventions everywhere:**
- Depth `z` is in m TVDSS, positive down.
- Area is in km². GRV is in 10⁶ m³ (= km²·m), matching the Builder and SCOPE-HC.
- Probabilities are fractions in [0, 1], shown as %.
- Grids are node-registered and unrotated; values are `(nrow, ncol)` with row 0 in the south.

**Statuses:** "Definable now" means the contract can be fixed now. "Needs D#" means a user
decision (§9) is required first.

### 5.1 Surface arithmetic and alignment — *definable now*

- **Inputs:** surfaces with `domain` (depth, time, thickness, velocity, probability, other), unit
  and CRS; scalars.
- **Allowed operations:**

  | Operation | Result domain |
  |---|---|
  | depth − depth | thickness (m) |
  | depth ± thickness | depth |
  | thickness ± thickness | thickness |
  | any × or + scalar | same domain |
  | clip, smooth | same domain |

  Anything else (time with depth, probability arithmetic, mixed units or CRS) is refused with the
  reason given. "Other" is allowed only with "other" and gives "other".
- **Alignment:** nodes must be identical to within 1e-6 of a cell. Otherwise the operation is
  refused, with an offer to resample explicitly (target grid, nearest or bilinear). Resampling
  creates a new derived surface.
- **Nulls:** a null in any input gives null. Division by zero gives null and is counted.
- **Output:** a new surface plus a derivation record (operation, inputs with version ids, parameters).
- **Failure conditions:** domain, unit or CRS mismatch; empty overlap; all-null result.

### 5.2 Depth conversion — *definable now*

- **Input:** a time surface, with its sign declared and the datum stated as MSL (an assumption
  shown to the user). One-way time is `t = |TWT| / 2000` s.
- **Methods:**
  - Constant average velocity: `z = V · t`.
  - Average-velocity grid: `z = V(x,y) · t`. Same geometry is required (5.1).
  - **V0+kZ:** `z = (V0/k)(e^{k t} − 1)`, which satisfies `dz/dt = V0 + kz`. V0 and k are constants
    in v1; `k → 0` falls back to `V0 · t`.
- **Output:** a depth surface, positive down, with provenance.
- **Failure conditions:** non-time input, `V ≤ 0`, a sign not declared.
- **Explicit assumptions:** no water layer, no well tie, no structural uncertainty.

### 5.3 Contouring and contour-derived geometry — *definable now*

- **Engine:** contourpy on node values (linear marching squares). Lines carry `level`,
  `open/closed`, `source surface + version` and `derived=true`.
- **Extract level:** filled polygons with holes at the level, restricted to a chosen region
  (closure footprint or outline). Polygon area comes from shapely.
- **Contours derived from a surface are never independent evidence.** They are regenerated or
  marked stale when the surface changes.
- **Imported or edited contour sets** are their own objects. They change a surface only through
  5.4.
- **Contour import (D5):**
  - GeoPackage, Shapefile or GeoJSON LineString/LineStringZ. The level comes from a chosen
    attribute or from Z. Every vertex of a line must share one level, else the line is rejected.
  - ASCII `x y z line_id`.
  - Units, sign and CRS are declared at import, as for grids.

### 5.4 Contours → surface (reconciliation) — *definable now; default chosen by benchmark*

- **Inputs:**
  - the contour set, with vertices resampled to about one cell spacing (F4: denser vertices degrade a
    local thin-plate fit);
  - optional crest points;
  - the target grid geometry;
  - the method: linear TIN (`scipy` Delaunay; the working default after F4) or thin-plate spline
    (`scipy.interpolate.RBFInterpolator`, local, with at least 150 neighbours). F4 measured 1–3 s
    for TIN and about 22 s for thin-plate on 63–131 k points;
  - an extrapolation limit (distance to data).
- **Output:** a new depth surface with provenance. The source surface, if any, is unchanged.
- **Checks reported:**
  - overshoot (values shallower than the shallowest contour or deeper than the deepest, inside the
    data hull);
  - origin of the crest (data, plateau or extrapolated);
  - misfit at the contours.
- **Failure conditions:** fewer than three non-collinear vertices; levels that are not numeric.

### 5.5 Closure and spill interpretation — *definable now*

- **Inputs:**
  - a depth surface;
  - a seed crest (a candidate or a user-picked node);
  - connectivity (default 8);
  - boundary types: model edge, null cell, outline (area clipping only, never a barrier);
  - minimum closure height and area for candidates.
- **Algorithm:** priority-flood from the crest. The **fill depth** `s(x)` is the depth at which an
  accumulation filling from the crest first reaches node `x`: the smallest achievable maximum depth
  along any path from the crest. `s ≥ z` everywhere, and `s = z` on a simple dome.
- **Candidate spill events are recorded in order of depth:**
  - `saddle-to-neighbour-structure`: the flood starts descending towards another culmination;
  - `reaches-model-edge`;
  - `reaches-null`.
- **Confirmation:** the user confirms one spill depth and the treatment of the boundary types:
  - "edge/null = unknown, treat as leak" (conservative);
  - "assume closed beyond (unverified)";
  - or a manual spill depth, recorded with a reason.

  The confirmation is stored as an interpretation record. Results that depend on an unconfirmed
  candidate are labelled *provisional*.
- **Outputs:** confirmed crest, spill depth, spill type, footprint `F = {x : s(x) ≤ spill}`,
  sub-culminations inside the footprint, and the field `s`.
- **Warnings:**
  - closure height below the minimum;
  - interior null holes in the footprint;
  - spill resolution (the node spacing times the gradient at the saddle);
  - footprint touching the edge at the confirmed spill;
  - a time-domain input (refused).
- **Assumption, shown to the user:** a single fill point at the crest. Sub-culminations fill only
  through their connection to it.

### 5.6 Area–depth and GRV — *definable now* (thickness definition: D7)

- **Area:** `A_top(c)` is the area of `{s ≤ c} ∩ outline`, from contouring `s` at `c`. It is
  sub-cell and connected-component-consistent. The node-count area is reported as a check.
- **GRV, direct column integration:**
  - Top+base: `GRV(c) = Σ_{x∈F} [min(base(x), c) − top(x)]⁺ · cell area`, restricted to
    `s(x) ≤ c`.
  - Top+thickness: `base = top + t`, where `t` is a constant or a grid. Thickness is vertical (C18).
- **Area–depth export:** depths from the crest to the confirmed spill, in steps of ≤ 1 m (or a
  user-set step).
  - `A_base(c)` = area of `{base ≤ c}` *within the top footprint F*.
  - Trapezoid `∫(A_top − A_base) dz` must match direct GRV within the tolerance in §7.
- **Fields that must match the companion apps:**

  | App | Depth | Areas | Required order and checks | GRV unit |
  |---|---|---|---|---|
  | HCWC Builder `AreaDepthTable` | depths strictly increasing, starting at the apex | top and base area (km²), `base ≤ top` | depth ascending from the apex | km²·m |
  | SCOPE-HC `geom_depth` | `Depth` | `Top area (km2)`, `Base area (km2)` | constant step expected for the top+thickness route | km²·m |

  Depth reference (m TVDSS, positive down) and units must be identical.
- **Flags:**
  - negative thickness (count, area);
  - base null where top is valid;
  - top and base footprints, spills or extents differ (reported, not reconciled silently);
  - outline clipping applied.
- **Choices recorded:** geometry route; intersection of top and base footprints if used (an
  option, labelled as an interpretation).

### 5.7 HCWC import and percentile handling — *definable now (D4 decided)*

- **Input:** CSV with `Percentile` and `Value` or `Depth(m)`, 101 rows (or a subset), exceedance
  convention.
- **Validation (rejected on failure):**
  - percentiles strictly decreasing, 100 → 0, as stored;
  - depth non-decreasing as the percentile falls (P100 shallowest);
  - finite values;
  - depth sign positive down. A negative-depth file is refused unless flipped explicitly.
- **Basis (D4):** read from the import. The Builder's filename `hcwc_percentiles_<basis>.csv`
  gives `geological` or `Given_DHI`. When the file does not say, the basis must be declared.
- **Conditioning** (`H ≥ h_min` or unconditioned) and **tail treatment** (truncated or raw) are
  declared at import and never defaulted. For a current Builder export they are `H ≥ h_min` and
  as chosen on Builder tab 7.0.
- **Table editor (D4):** a 101-row Percentile/Depth table that can be:
  - pre-filled from an imported file and edited;
  - pasted from a spreadsheet;
  - typed in.

  A pasted or typed table must have its basis and conditioning declared. It passes the same
  validation, and its provenance records "typed/pasted" together with the edited rows against the
  file it started from.
- **Exceedance function** `E(z) = P(C > z | ·)`:
  - piecewise linear in depth between table points;
  - `E = 1` above the shallowest row and `E = 0` below the deepest;
  - duplicated depths form a step: the higher exceedance is taken just above the depth, the lower
    at and below it.
  - The inequality is strict: a contact exactly at the structural depth means no column.
- **Error bound, stated:** at most one percentile step (0.01) against the underlying distribution,
  plus the tail truncation (≤ 0.005).

### 5.8 Spatial POS — *definable now (D1, D2, D3, D6 decided)*

- **Events (D1); each map names its event:**
  - **(a) HC with column ≥ h_min:** `POS_a(x) = P(G) · F(h_min) · E_min(s(x))`.
  - **(b) any HC column:** `POS_b(x) = P(G) · E_all(s(x))`.
  - Both apply only for `x ∈ F`, the trap footprint, and are evaluated on the fill depth `s`
    rather than the raw depth `z`, so sub-culminations are handled.
- **Which table supports which event:**

  | Table supplied | Event (a) | Event (b) |
  |---|---|---|
  | Conditioned on `H ≥ h_min` (today's Builder export) | Yes, with F(h_min) | Only where `s(x)` is deeper than apex + h_min, where it equals (a). In the band from the crest to h_min below it, (b) is shown as **not determinable from this table** |
  | Unconditioned | Only if h_min is given: `E_min` is derived by renormalising the part deeper than apex + h_min | Yes |

- **Inputs:**
  - P(G): from `.hcwc.json` **`inputs`** (product of `play_* × cond_*`; never from `resolved`,
    which F5 found can be stale) on the geological basis only, or typed.
  - F(h_min): typed, or read from a Builder file when one carries it (D2).
  - h_min, needed for the band.
  - The apex, for the band and for the anchoring check.
- **Anchoring (D3):** the default is absolute contact depths ("as is"). Option: re-anchor as
  `C_map = crest_map + (C − apex_median_builder)`. The difference between map crest and Builder
  apex is always reported, and a warning appears above 5 m.
- **Region categories, kept separate and never collapsed into one 0:**
  - inside the trap with `POS > 0`;
  - inside the trap, deeper than all contacts;
  - the event (b) band where it is not determinable;
  - outside the trap footprint;
  - outside the outline (not evaluated);
  - null data.
- **Invariants:**
  - `0 ≤ POS ≤ multiplier`;
  - non-increasing with `s`;
  - the crest value of event (a) equals the Builder's Prospect POS `P(G)·F(h_min)` when the crest
    is above every contact.
- **Typed depth→POS curves (D6):** a table of depth and value, interpolated linearly in depth and
  forced to 0 at the spill. Each curve declares one of:
  - **total POS** (P(G) included), mapped as typed;
  - **conditional on G**, mapped as `P(G) × value`.

  Both kinds can be mapped side by side. The declared meaning appears in the layer name and in
  the provenance.

### 5.9 Area and GRV across HCWC percentiles — *definable now* (inherits D1, D3)

- For each table row, `c_P' = min(c_P, spill)`. Then `A_P = A_top(c_P')` and `GRV_P = GRV(c_P')`.
- The result is exact because both A and GRV are non-decreasing in `c`.
- **Reported:**
  - `P(C ≥ spill)`, the fill-to-spill mass;
  - `P(C ≤ crest)`, contacts above the crest, which give zero volume;
  - the conditioning label.

### 5.10 Exports — *definable now*

- Area–depth CSV in the Builder column set and in the SCOPE-HC column set:
  - **Builder:** `depth_m,top_area_km2,base_area_km2`, with `#` comment lines carrying provenance.
    The first row is the crest at zero area; depths are strictly increasing and base ≤ top. An
    optional `grv_1e6m3_cached` column carries the direct-integration GRV for checking.
  - **SCOPE-HC:** `Depth`, `Top area (km2)`, `Base area (km2)`.
- **Area–depth CSV import** in the Builder format, with the same loose column matching. It allows
  area/GRV-versus-percentile evaluation (§5.9) when only a table exists and no map, and it gives a
  round-trip test.
- POS, fill-depth and derived grids as ZMAP+.
- Contours and polygons as GeoPackage.
- A results JSON/CSV containing: crest, spill, spill type, boundary assumptions, GRV route,
  multiplier and its sources, table basis and conditioning, percentile area/GRV, warnings, and all
  input hashes and parameters.

---

## 6. Revised architecture and technology choices

### 6.1 Dependencies for v1

| Keep | Purpose |
|---|---|
| numpy, scipy | Arrays, Delaunay/TIN, RBF thin-plate spline, `ndimage` (cross-checks) |
| pandas | Tables and CSV exchange |
| contourpy | Contour lines and filled polygons |
| shapely 2 | Polygon area, clipping, containment |
| plotly, streamlit | UI and map |
| geopandas + pyogrio | GeoPackage/Shapefile I/O only. Added in the contour phase. **[Fact]** Already present in the user's Anaconda |
Removed (D8): **xtgeo**, together with IRAP. Also removed from the requirements: verde and
pykrige. Do not add xarray, pyproj, scikit-image or streamlit-folium.

**[Verify]** in the feasibility phase: a clean-venv install of exactly this list on Windows; that
`RBFInterpolator` with neighbours performs on about 20 k points onto about 50 k nodes; that Plotly
selection events work on line traces.

### 6.2 Data model

Objects are immutable. A change creates a new version. This alone makes staleness and
reproducibility tractable, without an undo system.

- **Source** — an imported file: name, SHA-256 hash, import parameters (domain, unit, sign, CRS).
  Never modified.
- **Surface / ContourSet / Polygon** — data plus an `id`, a `version` and a `derivation`. The
  derivation is the operation, the input ids and versions, the parameters and the app version.
- **Interpretation** — confirmed crest, spill, boundary choices and manual overrides, each with a
  reason.
- **Result** — area–depth, GRV, POS and percentile tables, with input ids and versions. It is
  **stale** when any input has a newer version. Recalculation is a button, never automatic.
- **Project file** — a zip containing the manifest JSON and the arrays (npz). Reload verifies the
  hashes and reproduces results exactly.

### 6.3 Retrofits to Phase 0 (existing code)

1. Domain: no default; the user must choose. Unit is set from the domain and editable.
2. Sign flip becomes an import parameter applied on a copy. The source values are kept.
3. Record the file hash and import parameters.
4. Make `Surface` immutable (frozen); rename and copy become new versions.
5. Remove xtgeo and IRAP (D8): move `io/xtgeo_bridge.py` and the IRAP entries to
   `archive/` (moved, not deleted). Remove verde and pykrige from the requirements.
6. Keep: the ZMAP+ reader/writer, its tests, CI and the layout.

### 6.4 UI (tabs)

1. **Data** — import, declare, layer list.
2. **Prepare** — depth conversion, arithmetic, resampling.
3. **Closure** — candidates, confirmation, warnings.
4. **Volumes** — area–depth and GRV routes.
5. **HCWC & POS** — import, multiplier, map, percentile table.
6. **Contours** — display, import, delete, reconcile.
7. **Export & project.**

Stale results are badged throughout.

---

## 7. Validation and acceptance plan

**Tolerance policy:**
- Closed-form arithmetic: ≤ 1e-9 relative.
- Discretised geometry: judged by convergence. The error must fall at least ×3 when the cell size
  is halved (consistent with second order), with a fixed bound at a stated resolution.
- Probability lookups: exact for piecewise-linear cases; ≤ 0.01 + 0.005 against continuous truth.
- Node-quantised spill: within the theoretical bound of the cell size times the saddle gradient.

### 7.1 Analytic and synthetic tests (known answers)

| # | Calculation | Case | Expected | Tolerance |
|---|---|---|---|---|
| T1 | ZMAP+ | GEUS grid | 217 × 238, 23,784 valid, min −1548.941, max −945.1266, ED50-UTM32 | exact *(passes today)* |
| T2 | Depth conversion, constant V | GEUS, V = 2500 m/s | z = 1.25 · \|TWT\| → 1181.41–1936.18 m | 1e-9 rel |
| T3 | V0+kZ | V0 = 1800 m/s, k = 0.5 s⁻¹, t = 0.5 s | z = 3600(e^0.25 − 1) = 1022.49 m; dz/dt = V0 + kz | 1e-6 m |
| T4 | Arithmetic and refusals | depth − depth; time + depth; mismatched grids | thickness; refused; refused with a resample offer | exact |
| T5 | Area–depth, paraboloid | z = z0 + a·r², a = 1e-4 m⁻¹ | A(z0 + 100) = π·10⁶ m² = 3.1416 km² | convergence; ≤ 0.5 % at 25 m cells **[Verify the bound in feasibility]** |
| T6 | GRV top-only, paraboloid | contact 100 m below the crest | π·(100)²/(2a) = 157.08 × 10⁶ m³ | as T5 |
| T7 | GRV top + constant thickness | t = 50 m, contact 100 m below the crest | (π/a)(5000 − 1250) = 117.81 × 10⁶ m³ | as T5; direct and trapezoid agree within 0.5 % |
| T8 | GRV, cone | z = z0 + s·r | A = π((c − z0)/s)², GRV = π(c − z0)³/(3s²) | as T5 |
| T9 | Spill at a saddle | two domes joined at a saddle node of known depth | spill type "saddle", depth = the saddle node | exact at node level |
| T10 | Connectivity | saddle through a diagonal corner | 8-connected: spill at the corner; 4-connected: later (documented) | exact |
| T11 | Edge and null | a tilted dome reaching the edge; a hole inside the closure | candidate "reaches-model-edge"; warning "interior null" | exact |
| T12 | Plateau and noise | a flat crest; added noise | a single crest after the prominence filter | exact |
| T13 | Sub-culmination | two crests above a common saddle | `s` = saddle depth over the second crest; POS there = `M·E(saddle)` | exact |
| T14 | HCWC lookup | C ~ U(2100, 2200), 101 rows, M = 0.3 | POS(2150) = 0.15; POS(2050) = 0.3; POS(2200) = 0 | 1e-12 |
| T15 | HCWC validation | reversed order; ascending depth with P; negative depths; mixed headers | rejected / rejected / refused unless flipped / both accepted | exact |
| T16 | Point mass | 30 % of contacts at 2200 m | E(2199.99) ≥ 0.30; E(2200) = 0 | exact step |
| T17 | Tails | normal distribution, truncated table | E within 0.015 of the exact CDF | 0.015 |
| T18 | Conditioning (C1) | synthetic run with known F(h_min) = 0.7 | conditioned table × P(G)·F(h_min) reproduces the unconditioned `P(G)·P(C > z \| G)` for every z deeper than apex + h_min (there, C > z implies H > h_min); shallower, it is lower by design | 1e-3 |
| T19 | Percentile GRV | uniform C on the paraboloid | GRV_P = π(c_P − z0)²/(2a); spill cap and spill mass correct | as T6 |
| T20 | POS invariants | any of the above | 0 ≤ POS ≤ M; monotone in s; region categories disjoint | exact |
| T21 | Contours → surface | plane; paraboloid and cone at Δ = 10 and 25 m; two-dome saddle | thresholds in §7.2 | §7.2 |
| T25 | Builder area–depth CSV | export, then re-import (aliases, `#` comments, apex row) | identical table; GRV matches `grv_1e6m3_cached` | 1e-9 |
| T26 | Percentile table editor | paste with reversed order; edit one row | rejected; provenance lists the edited row | exact |
| T27 | Event (b) from a conditioned table | conditioned table with h_min = 100 m | (b) = (a) deeper than apex + h_min; the band is flagged not determinable | exact |
| T22 | Reproducibility | save → load → recompute | identical results and hashes | exact |
| T23 | Staleness | edit an input | every dependent result is marked stale, none recalculated | exact |
| T24 | Exchange files | area–depth export | passes the Builder's `AreaDepthTable` rules (increasing depth, base ≤ top), mirrored as tests without importing the Builder | exact |

### 7.2 Acceptance thresholds for contour-derived surfaces (D9)

**The test bench:** the analytic paraboloid and cone from §7.1, and a two-dome saddle case. Each
is contoured at interval Δ = 10 m (and also 25 m), then regridded to a 50 m grid. Results are
compared with the analytic answers.

| Quantity | Threshold | Justification |
|---|---|---|
| Plane | Reproduced to 1e-6 m | Both methods are exact for linear data; anything else is a bug |
| Spurious closures | **None** with height > Δ/2 | A false closure changes the trap interpretation itself; this is the hard rule that disqualifies a method |
| Depth at nodes between contours, inside the data hull | RMS ≤ Δ/4, max ≤ Δ/2 | The contours fix depth only to within Δ between levels; a method should resolve it to a fraction of Δ |
| Spill depth | Error ≤ Δ/2 plus the node-quantisation bound (§5.5) | The contour data cannot locate a saddle more precisely than half an interval |
| Crest depth, if not supplied | Reported only; error ≤ Δ on the paraboloid | Inside the innermost contour the data says nothing, so this is a sanity bound, not accuracy. A supplied crest point removes it |
| Area at a contoured level | Within 1 % of analytic | The contour itself defines the area, so only discretisation remains |
| GRV to spill | Within 3 % of analytic for a closure of ≥ 5Δ relief | Small against typical HCWC-driven P90/P10 GRV spreads, which are usually tens of percent, so method error does not drive the volume range. Below 5Δ relief a warning appears that the closure is poorly resolved by the contour interval |
| POS at nodes | Follows from the depth error: \|ΔPOS\| ≤ multiplier × max slope of E × depth error. Reported, not separately thresholded | POS is a function of depth, so depth accuracy governs it |

**Default method:** thin-plate spline if it meets every threshold, because it gives smooth,
realistic structure between contours. Otherwise linear TIN, which honours the contours and never
overshoots. The benchmark report is kept in `docs/` and re-run in CI.

### 7.3 Hand-checked geological examples

- A small synthetic prospect (e.g. 9 × 9 nodes) with hand-computed crest, spill, footprint area,
  area–depth and GRV, kept in the repository as a worked example.
- **GEUS grid:** import, sign, depth conversion (T2), and an internal-consistency test:
  1. extract contours from the depth-converted grid;
  2. regrid them (TIN and TPS);
  3. compare crest, spill, area and GRV with the original grid.

  This tests the method's self-consistency, **not** geological truth.

### 7.4 External comparisons (useful, not prerequisites)

- Any past prospect where the user has an area–depth table or GRV from GeoX, Petrel or a
  spreadsheet, together with its depth grid. One such case would add the most confidence.
- A real HCWC Builder export (geological basis), with the Prospect POS and F(h_min) noted, to
  check the crest value in §5.8.
- Agreement with external results is evidence, not proof; any difference is investigated, not
  tuned away.

---

## 8. Revised phased development plan

| Phase | Objective | Deliverables | Depends on | Acceptance | Main risks | Deferred |
|---|---|---|---|---|---|---|
| **F. Feasibility** ✅ done 2026-10-09 (`docs/FEASIBILITY.md`) | Remove technical unknowns | Clean-venv Windows install of the §6.1 list; Plotly line-selection prototype; contourpy → shapely area convergence on the paraboloid (sets the T5 bound); RBF/TIN timing on 20 k → 50 k; a real Builder CSV and `.hcwc.json` in hand | – | Each item gives a written yes or no with numbers | Selection on lines fails → fall back to choosing by table or list | Everything else; no xtgeo (D8) |
| **1. Data integrity** | Safe inputs and traceability | Phase 0 retrofits (§6.3); Source/derivation/version model; depth conversion; domain-checked arithmetic; explicit resampling; project save/load | F | T1–T4, T22, T23 | Model over-design | Formats beyond ZMAP+ |
| **2. Closure and volumes** | Correct trap geometry and GRV | Priority-flood `s`, candidates, confirmation records, boundary types; area–depth (sub-cell); GRV via three routes with cross-check; outline clipping; Builder/SCOPE-HC area–depth export | 1 | T5–T13, T24; the hand-checked prospect | Saddle and edge cases; convergence | Faults |
| **3. HCWC and POS** | The core probability output | CSV import with validation and the table editor; basis, conditioning and multiplier inputs; anchoring (default as is); POS maps for both events with categories; percentile area/GRV; typed depth→POS curves (total or conditional); Builder area–depth import; results report | 2 | T14–T20, T25–T27; crest POS = Builder Prospect POS on a real export | Semantics (C1–C3) | DHI basis (if deferred) |
| **4. Contour workflow** | Contour-first parity | Contour import (GeoPackage/Shapefile/GeoJSON, ASCII x y z id); select → delete; contours → surface (TIN and TPS) as reconciliation; benchmark report; stale propagation into phases 2–3 | 2 (needs 3 for the full POS chain) | T21 plus GEUS self-consistency; D9 thresholds met | Crest extrapolation (C7); selection UX | More gridders, digitising |
| **5. Hardening** | v1 release | Warnings review, worked-example documentation, performance on the GEUS grid, user test on a real prospect | 1–4 | A real-prospect run reproduced from the saved project | – | All of §4.2 |

Phase 4 could run in parallel with phase 3 after phase 2. It is sequenced after phase 3 only
because the full end-to-end check of the contour-first path needs POS.

---

## 9. Decisions and remaining open items

D1–D9 are decided (§0). What remains:

| # | Item | Why it is still open | Impact |
|---|---|---|---|
| R1 | **F(h_min) in a Builder export** (D2, second route) | It needs a change to HCWC Builder: an extra line or column in the export, or a field in `.hcwc.json` results. That is outside this repository and was not to be implemented here | Until then F(h_min) is typed, and the crest-value check against Prospect POS guards against a typing error |
| R2 | **Unconditioned table from the Builder** (event (b) in the crest band) | Today it is available only by re-running the Builder with h_min = 0 | Event (b) near the crest is flagged as not determinable from a conditioned table |
| R3 | **Confirm the contour import formats** (D5) | The Builder has no contour format, so the choice in §5.3 is a recommendation | If the contours come from other software in another format, one reader is added in Phase 4 |

## 10. Change log against `docs/PLAN.md` (draft 3)

1. **POS formula** changed from `P(G) × exceedance` to `M × E(s)`, where `M` depends on the
   conditioning of the table (C1). It is evaluated on the fill depth `s`, not the raw depth, so
   sub-culminations are handled.
2. **Mode B (gridding POS) and the six-gridder menu removed.** Contour-only POS now goes through
   contours → depth surface → the same POS rule.
3. **Convergent interpolation** demoted from default to "not planned". The default is chosen
   between scipy TIN and thin-plate spline by a geological benchmark.
4. **Spill:** "edge/null = spill by default" replaced by candidate boundary types with mandatory
   confirmation. The algorithm is a priority-flood fill-depth surface instead of
   flood-fill/lowest closing contour.
5. **GRV:** direct column integration is primary. Area–depth is an exchange product with an
   agreement check and the base area restricted to the top footprint.
6. **HCWC:** basis, conditioning and tail treatment declared at import. The anchoring check is
   added. Contacts are capped at spill for volumes, with the spill mass reported. 101-contour
   objects removed.
7. **Data model:** immutable objects with sources, derivations, versions, interpretation records
   and stale results, instead of mutable surfaces with free-text provenance.
8. **Arithmetic:** the free expression parser and automatic resampling replaced by a domain table
   and explicit resampling.
9. **Formats:** v1 is ZMAP+ grids plus vector import/export (D5) and the exchange CSVs. IRAP is
   optional. CPS-3, GeoTIFF, Petrel and XYZ are deferred.
10. **Dependencies:** verde, pykrige, xarray, pyproj and streamlit-folium removed. geopandas and
    pyogrio are only for vector I/O.
11. **Editing:** in-app editing limited to select → delete. Drawing and vertex edits go through QGIS.
12. **Outlines:** area clipping only. Outside an outline is "not evaluated", not "0 %".
13. **Phases:** ten phases replaced by feasibility plus five dependency-ordered phases, with
    validation tests defined before implementation.
14. **Brief correction:** Phase 0 code exists; the retrofits are listed in §6.3.
15. **Draft 4 decisions:**
    - D1: both POS events.
    - D2: F(h_min) typed now, from the Builder later.
    - D3: both anchorings, default as is.
    - D4: basis from the import, plus a table editor for percentiles.
    - D5: vector contour formats, plus the Builder area–depth CSV read and written.
    - D6: typed curves mapped as total or conditional.
    - D7: thickness vertical.
    - D8: xtgeo and IRAP removed.
    - D9: thresholds in §7.2.
