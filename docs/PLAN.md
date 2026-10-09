# POS-Gridder — Development Plan

*Status: draft 3, 2026-10-09. Phase 0 done (see §9). Repository and app name: **POS-Gridder**, package `posgridder`.*

A Streamlit app with Petrel/QGIS-style tools for subsurface surfaces: import, arithmetic, depth
conversion, contouring, contour editing, area/GRV, attributed contours (POS), gridding of POS, and
import of the HCWC Builder contact distribution.

---

## 1. What the interview settled

| # | Topic | Decision |
|---|---|---|
| 1 | Formats | Read **and** write ZMAP+, IRAP classic/binary, Petrel, CPS-3, GeoTIFF, XYZ points |
| 2 | Depth conversion | Three methods: constant velocity, velocity surface, V0+kZ |
| 3 | Point data | Scatter-point sets are first-class objects and can be gridded (including points sampled from contour sets) |
| 4 | Grid mismatch | Simplest rule: auto-resample to a chosen reference grid; null in either input gives null out |
| 5 | Contour styling | Major/minor interval, start/stop, labels, smoothing, filled colour map |
| 6 | Contour editing | Minor editing only (see §5.4) |
| 7 | Area | Polygon area **plus** GRV above a contour / closure analysis |
| 8 | POS attribute | One POS value per contour level, because POS is a function of depth |
| 9 | POS gridding | Smooth between contours, following the surface where one exists, and must also work from contours alone |
| 10 | Algorithms | Five gridders plus a Petrel-style default; everything deeper than the spill contour is 0% |
| 11 | HCWC | Import from HCWC Builder (format confirmed below) |
| 12 | HCWC merge | All 101 percentiles, plus an area/probability evaluation (see §8) |
| 13 | Users | Single user, runs locally on Windows (assumed) |
| 14 | Basemap | None. Plain UTM cartesian view |
| 15 | Reference UX | Petrel and QGIS |
| 16 | Outline polygons | Yes. Import, draw and use boundary polygons for area (and clip/mask). Faults are not in scope for v1 |
| 17 | P(G) source | Both: manual entry, or read from the HCWC Builder `.hcwc.json` file |
| 18 | GRV | Both: top + base surface, **and** top + thickness (constant or gridded) |
| 19 | Default gridder | Our own **convergent interpolation**, which is the default (see §7.1) |
| 20 | Ecosystem | Standalone for now. Designed to integrate later with HCWC Builder and WellVolPOS, and perhaps merge with SCOPE-HC (see §11) |
| 21 | Petrel reference | None available. The convergent gridder is validated on synthetic surfaces and against the other gridders only |
| 22 | Outline purpose | Boundary polygons for area. They do not act as spill barriers |
| 23 | Gridded thickness | Built in the calculator (base − top), then used as the thickness surface |
| 24 | Repository | New git repo **POS-Gridder**, same tooling as HCWC Builder (pyproject, devcontainer, CI) |

*Draft 2 (2026-10-09): rows 16–20 added after the second round of answers. Draft 3: rows 21–24.*

---

## 2. Findings from your files

### Test surface
`data/private/HVN_Top Gassum_TWTgrd250m_3xsm_geus2023.dat` (untracked; tests skip without it)
- ZMAP+ ASCII from ZIMS. 238 rows × 217 cols at 250 m. ED50 / UTM32.
- Null value 1E+30. 23,784 of 51,646 nodes are valid.
- **The domain is TWT in ms, negative down (−945 to −1549).** This makes it a natural first test
  for depth conversion.
- **xtgeo does not mask this file's nulls.** It reads the geometry correctly but treats only its
  own 1E+33 as undefined, so the 1E+30 nodes arrive as values. ZMAP+ therefore goes through our
  own reader, which takes the null from the header (Phase 0, verified node for node against
  xtgeo).

### HCWC Builder (`../HCWC builder`)
- **Export file:** `hcwc/io/geox.py`, CSV with columns `Percentile`, `Value`. The GeoX variant
  uses the header `Depth(m)`. It has 101 rows running from **P100 down to P0**.
- **The convention is exceedance:** P100 is the *shallowest* contact and P0 the deepest. The tails
  are truncated at P99.5/P0.5 by default. The importer must assert this order, because getting it
  backwards inverts everything without any error.
- **The POS model** in the Builder is `POS(h) = P(G) × F(h)`, with `F(h) = P(contact deeper than h | G)`.
  So POS at depth d = **P(G) × exceedance(d) / 100**. This matches what you assumed in Q11.
- **P(G) is not in the CSV.** The map tool must take it as an input, either typed in or read from
  the `.hcwc.json` prospect file or the one-page report.
- The Builder already has an **`AreaDepthTable`** (depth, top area km², base area km²) and offers
  "Two mapped surfaces / Top surface and a thickness". The map tool can **produce that table**, so
  the loop closes: map → area-depth → HCWC Builder → percentiles → back to map.
- The project layout should be copied: `core/` with no Streamlit import, plus `io/`, `ui/`, `tests/`
  and the pytest render marker. That keeps your apps consistent.

---

## 3. Library stack

| Layer | Library | Role |
|---|---|---|
| Surfaces + I/O | **xtgeo** 4.x (own ZMAP+ reader) | IRAP classic/binary and other Petrel-family formats; ZMAP+ by our own code |
| Fallback I/O | zmapio, rasterio/rioxarray | ZMAP+ edge cases, GeoTIFF |
| Arrays | numpy, xarray | Masked arithmetic |
| Expression calculator | `ast`-whitelisted evaluator (or numexpr) | `thick_AB = A - B` safely |
| Contouring | **contourpy** | Open and closed lines, filled bands |
| Vector geometry | **shapely 2, geopandas** | Area, closed tests, edit ops, GeoPackage/Shapefile export |
| Closure / spill | scipy.ndimage, scikit-image | Flood-fill / connected regions for the spill point |
| Gridding | scipy.interpolate, **verde**, **pykrige** | See §7 |
| CRS | pyproj | Stored per object; no reprojection needed with no basemap |
| Map view | **Plotly** (`st.plotly_chart(on_select=…)`) | Heatmap + contours, click/lasso selection |
| Digitising (optional) | streamlit-folium + Draw plugin | Only if hand-drawn polygons are needed (needs WGS84 reprojection) |
| Tables / editing | `st.data_editor` | Contour attribute table (POS per level) |

---

## 4. Architecture

```
POS-Gridder/
├─ app.py                     # Streamlit shell: sidebar layer tree + tabs
├─ posgridder/
│  ├─ core/                   # no Streamlit import, fully testable
│  │  ├─ model.py             # Surface, PointSet, ContourSet, PolygonSet, Project
│  │  ├─ calculator.py        # expression parser, scalar & surface arithmetic
│  │  ├─ resample.py          # reference-grid alignment, null rules
│  │  ├─ depthconv.py         # const V, V-surface, V0+kZ
│  │  ├─ contouring.py        # contourpy → shapely, smoothing, labels
│  │  ├─ editing.py           # delete / close / join / split / simplify
│  │  ├─ closure.py           # spill point, closure polygon, area-depth, GRV
│  │  ├─ gridding.py          # the 6 gridders behind one interface
│  │  ├─ pos.py               # POS(depth) curves, surface-guided POS map
│  │  └─ hcwc.py              # HCWC CSV/JSON import, exceedance → POS
│  ├─ io/                     # readers/writers per format, project save/load
│  ├─ plotting/               # map figures
│  └─ ui/                     # sidebar + one module per tab
├─ tests/
├─ docs/                      # this plan
└─ data/private/              # local test data, untracked
```

### Data model (all objects live in a `Project` held in `st.session_state`)
- **Surface** (built in Phase 0): a masked numpy array `(nrow, ncol)`, row 0 in the south, plus
  `xori, yori, xinc, yinc`, `name`, `domain` (depth/time/thickness/velocity/pos/other), `unit`,
  `crs`, `provenance` (e.g. `"A - B"` or `"depthconv(V0=1800,k=0.6)"`). xtgeo is used only at
  the file boundary, through `io/xtgeo_bridge.py`.
- **PointSet**: DataFrame with x, y, z plus attributes.
- **ContourSet**: GeoDataFrame with `level`, `geometry`, `is_closed`, `is_major`, `deleted`,
  `source_surface`, and user attributes such as `POS` and `percentile`. POS is stored **per level**
  in a separate level table, which matches Q8.
- **PolygonSet**: closure polygons, outlines, and hand-made polygons.
- **Project save**: a folder or zip containing `project.json` (manifest + provenance), surfaces as
  IRAP binary, and contours and polygons as GeoPackage.

### Conventions, fixed once
- Depth is stored internally as **positive down, m TVDSS**. The sign flips on import and export
  according to each file's setting. The GEUS TWT file is negative, so the import dialog asks
  about the sign.
- Exceedance percentiles follow the HCWC Builder convention: P100 is the shallowest.

---

## 5. Feature specifications

### 5.1 Surface manager (sidebar, QGIS layer-tree style)
List of surfaces, point sets and contour sets with: visibility, rename, **copy**, delete, info
(geometry, min/max, null count, provenance), and a colour map per surface.

### 5.2 Calculator
- Scalar operations on one surface: `+ − × ÷` with a constant.
- Surface arithmetic as expressions over layer names: `thick_AB = B - A`,
  `avg = (A + B) / 2`, `iso = (B - A) * 1.0`.
- Inputs are auto-resampled to the reference grid (the first operand by default). Nulls
  propagate. Division by zero gives null.
- Optional helpers: clip min/max, fill nulls, smooth (n passes).
- The same operators work on point sets when the operands are scalars.

### 5.3 Depth conversion
For a TWT surface (one-way time t = TWT/2):
- **Constant velocity:** Z = V · t
- **Velocity surface** (average velocity): Z = Vavg(x,y) · t. The velocity grid is resampled to
  the TWT grid.
- **V0 + kZ:** Z = (V0/k) · (e^(k·t) − 1). V0 can be a constant or a surface.
- Optional well-tie correction (residual gridding) can be added later.

### 5.4 Contouring and editing
- Interval, start, stop, major every n, labels, optional smoothing (pre-smoothing the grid
  and/or Chaikin smoothing of the lines), filled colour map underneath.
- **Extract a single level** (e.g. 2310 m) into its own contour set.
- **Minor editing:** select (click or lasso) → delete, undelete, close an open line (straight
  segment), join two lines, split at a vertex, simplify. Deleting is a flag, not a removal, so it
  can be undone.
- Open and closed status is computed automatically and shown in the attribute table.

### 5.5 Area, closure, spill point, GRV
- Area of each closed polygon in km² (and m²).
- **Spill point / lowest closing contour:** pick a crest (or let the tool find the local minimum
  depth). Flood-fill the region connected to the crest at increasing depths. The spill depth is
  the last depth before the region touches the grid edge or a null area. This works even when
  contourpy splits lines, and it is the same "lowest closing contour" Petrel shows.
- **Area–depth table** from crest to spill. **GRV** comes from trapezoidal integration, exactly as
  `AreaDepthTable` does. There are two methods, as in the Builder and SCOPE-HC:
  - **Top + base surface:** the base area comes from the base surface's own closure.
  - **Top + thickness:** either a constant (base = top shifted down, as in SCOPE-HC's
    `compute_dgrv_top_plus_thickness`) or a thickness surface built in the calculator
    (`thick = base - top`), so base = top + thickness.
- **Boundary polygons:** an outline limits the area and GRV, can mask surfaces and POS maps, and
  can serve as the "outside = 0 %" boundary. It never acts as a spill barrier.
- Export the table as CSV in HCWC Builder and SCOPE-HC column formats (see §11).

### 5.6 Outline polygons
- Import Shapefile, GeoPackage, GeoJSON or CSV/XY. Create a polygon from any closed contour or
  from the computed closure. Simple digitising comes later (see §10.1).
- Operations: area, clip a surface or contour set, mask outside, intersection/union of two
  outlines, and area per outline.

---

## 6. POS on contours
- Attribute table per level, e.g. `2300 m → 24 %` and `2400 m → 13 %`. Values come from manual
  entry or from HCWC (§8).
- **Rule:** POS is 0 at and below the spill contour. A spill row with 0% is inserted
  automatically, and the user is warned if a level deeper than the spill has POS > 0.
- Check: POS must not increase with depth (warn, don't block).

---

## 7. POS gridding

### Mode A — surface-guided (preferred when a surface exists)
POS(x,y) = interp₁D(depth(x,y)) over the level table, masked to the **closure polygon**
(crest-connected region above the spill), and 0 outside it. This follows the surface exactly
between contours, as asked for in Q9. It is not really "gridding", so it is shown as the reference
answer.

### Mode B — contours only (no surface)
Contour lines are densified to points carrying POS, plus the spill contour at 0%, and gridded
spatially. Results are clamped to [0, 1] and set to 0 outside the spill polygon. Algorithms
behind one interface, so they can be compared side by side:

| # | Algorithm | Library | Character |
|---|---|---|---|
| 0 | **Convergent (default)** | own implementation, §7.1 | Coarse-to-fine multi-resolution refinement. Honours data, keeps trends in sparse areas, extrapolates sensibly |
| 1 | Linear TIN | scipy `griddata(linear)` | Exact, faceted, no overshoot |
| 2 | Clough-Tocher (cubic TIN) | scipy `griddata(cubic)` | Smooth, honours data, can overshoot (clamped) |
| 3 | Thin-plate spline / RBF | scipy `RBFInterpolator` | Smooth minimum curvature, with a smoothing parameter |
| 4 | Bi-harmonic spline (Green's functions) | **verde** `Spline` | Minimum curvature, with damping and cross-validation |
| 5 | Ordinary kriging | **pykrige** | Variogram-based. Points are subsampled for speed |
| (6) | Inverse distance | own / scipy KDTree | Simple and fast. A spare option |

Mode B can optionally use the surface as a trend ("depth-guided"): grid the residual
POS − interp₁D(depth). This bridges modes A and B.

Outputs: a POS surface (0–1, or %), with cross-validation RMS per algorithm and a side-by-side map view.

The same gridding module also serves the general **points → surface** case (Q3: scatter points
and contour sets gridded into a depth surface). Convergent is the default there too.

### 7.1 Convergent interpolation (our own implementation)
**Yes, we can build it.** SLB publishes what the method does, though not its source code:
- It works from the control points, not the grid nodes.
- It starts on a coarse grid and **halves the grid spacing at each iteration** until it reaches
  the final grid.
- At each level it maps the residuals at the control points onto nearby nodes.
- The result keeps general trends where data is sparse and honours detail where data is dense.
- It handles points, lines (contours), dense grids, or combinations of these.

The closest well-documented algorithm is the **multilevel B-spline approximation** (Lee, Wolberg
& Shin, 1997), which behaves the same way. The plan:

1. **Prepare the data.** Densify line data (contours and outlines) to points at roughly half a
   cell. Block-average duplicates per final cell.
2. **Start coarse.** The coarsest grid spacing is the final spacing × 2ⁿ, chosen so that about
   4–8 cells span the data extent. Initialise with the data mean or a planar trend.
3. **Refine at each level:**
   1. Compute the residuals at the control points (data − bilinear value of the current grid).
   2. Spread the residuals to nodes within an influence radius (about 1.5–2 cells) using
      distance weights, i.e. a B-spline kernel.
   3. Add the correction. Optionally relax it with a few Laplacian/biharmonic smoothing passes.
   4. Repeat a few iterations until the RMS residual stops falling.
4. **Halve the spacing.** Upsample bilinearly and go back to step 3, until the final grid is
   reached.
5. **Finish.** Optionally snap nodes that hold data so data is honoured exactly. Optionally apply
   final smoothing. Set the null mask from a distance-to-data limit, an outline polygon, or none
   (extrapolate).

**User parameters:** refinement levels (auto), iterations per level, influence radius,
smoothing, honour data on/off, extrapolation limit.

**Validation** (no Petrel reference is available):
- Synthetic surfaces, where the true values are known: planes and quadratics (should be
  reproduced almost exactly), domes, and the GEUS grid subsampled to points and contours and
  re-gridded against the original.
- Leave-one-out cross-validation against the other five gridders.

**Cost:** pure numpy/scipy. Each level is O(points + nodes), so it is fast enough for the GEUS
grid size (about 50k nodes) and for densified contours with tens of thousands of points.

---

## 8. HCWC integration (answer to Q12: do both)

**Import:** the HCWC CSV (`Percentile` + `Value`/`Depth(m)`, 101 rows). The importer asserts P100
is the shallowest and offers a sign flip.

**P(G), both options:**
- Typed in by hand.
- Read from a `.hcwc.json` prospect file, which holds the element chances. P(G) is their product,
  as in `hcwc.core.pos.accumulation_chance`. That logic is re-implemented locally, not imported,
  so the apps stay independent.
- When both are present, the tool shows them side by side and the user picks one.

**A. Contours from the distribution:** POS(d) = P(G) × Pexc(d)/100.
- Internally all 101 values are kept as the **continuous POS–depth curve**. That curve drives
  Mode A directly.
- For display and for Mode B, contours are extracted at a chosen subset (P90/P50/P10, every 10th,
  or all 101 with duplicate depths collapsed). Each contour carries `percentile` and `POS`.
- Merge with custom contours: HCWC levels and manual levels share one level table. Where they
  overlap, the user picks which value wins.

**B. Area and probability evaluation:**
- Area and GRV at each percentile contact give **P90/P50/P10 area and GRV** (an area-vs-exceedance
  curve).
- Consistency check: if the HCWC deepest contacts lie below the map spill point, flag it (the
  Builder's spill limit and the map disagree). Map-derived spill and area-depth can be exported
  back to the Builder.

---


## 9. Phases

| Phase | Content | Done when |
|---|---|---|
| **0 Setup** ✅ | Repo, package skeleton, requirements/pyproject, CI, devcontainer, venv with xtgeo 4.26. `Surface`/`Project` model, own ZMAP+ reader/writer, IRAP via xtgeo, sidebar layer list (import, copy, rename, delete), map tab with export | Done 2026-10-09: GEUS grid loads, matches xtgeo node for node, round-trips; 18 tests pass |
| **1 Surfaces** | CPS-3, GeoTIFF, XYZ point sets; point display; map polish (hover, colour range, nulls) | Every format round-trips; points shown over a surface |
| **2 Calculator** | Scalar and surface arithmetic, resampling, null rules | `thick = B - A` on mismatched grids gives the expected values (tests) |
| **3 Depth conversion** | Three methods + sign handling | Known synthetic cases match analytically |
| **4 Contours** | contourpy, styling, single-level extraction, attribute table, minor editing, export GPKG/SHP | 2310 m contour extracted; open/closed flagged; delete/undo works |
| **5 Closure & outlines** | Spill finder, closure polygon, outline import and use, area, area–depth, GRV (top+base and top+thickness), HCWC/SCOPE-HC export | Matches a hand-checked synthetic dome |
| **6 Gridding engine** | **Convergent interpolation** + five other gridders behind one interface, points/contours → surface, cross-validation view | Convergent reproduces synthetic surfaces; leave-one-out comparison table |
| **7 POS** | Level table, Mode A, Mode B on the gridding engine, 0% at and below spill, outline masking | POS maps for all gridders; spill rule enforced |
| **8 HCWC** | CSV import, P(G) typed or from `.hcwc.json`, 101-level curve, contour merge, area/GRV percentiles, consistency check | Round trip with a real HCWC Builder export |
| **9 Polish** | Project save/load, PNG/PDF map export, simple digitising | Session survives a restart |

Phases 0–2 give a usable surface calculator early. Phases 4–5 give the core mapping tool.
Phase 6 is the largest single piece of work. Phases 7–8 are the novel POS/HCWC part.

---

## 10. Risks and open points
1. **Interactive editing in Streamlit is limited.** Plotly returns *selections* but not drawn
   shapes. Selecting, deleting, closing and joining are fine. Digitising outlines needs
   streamlit-folium (with reprojection from ED50/UTM to WGS84) or a small custom component, so it
   is in Phase 9. Outlines can be imported or made from contours before then.
2. **The convergent gridder is our own implementation.** It is close to Petrel in behaviour but
   will not match it node for node, and no Petrel grid is available to tune against.
3. **Kriging scales badly.** Densified contours can produce tens of thousands of points, so
   subsampling or a block mean is needed.
4. ~~xtgeo wheels on Windows~~: confirmed, xtgeo 4.26 installs on Python 3.12/Windows. Its
   ZMAP+ null handling is the one gap, covered by our own reader.
5. **Spill-point definition at the grid edge, nulls and outline boundaries:** the default is that
   touching a null area or the grid edge counts as spilling. An outline does not count as a spill
   barrier unless the user says it does.

---

## 11. Ecosystem: standalone now, integration-ready later

The tool stays a **separate app**. These choices keep a later integration cheap:

- **Same layout as the sibling apps.** The `posgridder/core` package has no Streamlit import, the UI
  sits in `posgridder/ui`, and each tab is its own module. That way the core can later be imported
  as a library by HCWC Builder, WellVolPOS or SCOPE-HC, or tabs can be lifted across into a
  merged app.
- **Shared conventions:** depth in m TVDSS positive down, area in km², GRV in 10⁶ m³ (km²·m),
  and exceedance percentiles with P100 as the shallowest. These match HCWC Builder and
  WellVolPOS.
- **No cross-imports for now.** Exchange goes through files, with readers and writers in
  `posgridder/io/exchange.py`:

| To / from | Exchange | Columns / format |
|---|---|---|
| HCWC Builder → map | Contact percentiles | `Percentile`, `Value` or `Depth(m)`, 101 rows, P100 shallowest |
| HCWC Builder → map | Prospect file (P(G)) | `.hcwc.json` element chances |
| Map → HCWC Builder | Area–depth (charge/spill tab) | depth m, top area km², base area km² (the `AreaDepthTable` fields) |
| Map → SCOPE-HC | Area–depth for dGRV | `Depth`, `Top area (km2)` (+ base) as in `scopehc/geom_depth.py` |
| Map → WellVolPOS | Area–depth curve, spill, crest | Its `AreaDepth` structure; the exact columns are to be confirmed when integrating |

- **Future merge path:**
  1. File exchange (v1).
  2. Shared `core` installed as a package in each app.
  3. One multi-page app (map → HCWC → volumetrics → WellVolPOS) with one shared project object.

### Answered in draft 3
- a) No Petrel available → validation on synthetic data only (§7.1).
- b) Outlines are boundary polygons for area, never spill barriers (§5.5).
- c) Gridded thickness is built in the calculator (§5.5).
- d) New repo POS-Gridder with HCWC Builder tooling → Phase 0 done.
