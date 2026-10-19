# Worked example: Top Gassum, GEUS grid

*POS-Gridder 0.3.0. Uses the GEUS Top Gassum TWT grid
(`HVN_Top Gassum_TWTgrd250m_3xsm_geus2023.dat`) and the HCWC Builder export in
`tests/fixtures/hcwc_builder/`. The same chain runs as a test in `tests/test_acceptance.py`; the
numbers below come from it.*

The Builder export belongs to a different prospect: its apex is near 2050 m, the GEUS closure
near 960 m. It is used here to show the probability chain on real Builder output. That is why
the contacts are re-anchored, and why the app warns that the spills disagree.

The progress strip above the tabs follows the steps below (Surface, Depth, Closure, Volumes,
Contacts, POS) and names the next one.

## 1. Start — tab **1 Start** and the sidebar

- A new session offers **Reopen last project**, since every change is autosaved to
  `~/.pos-gridder/` and the last three sessions are kept. To begin afresh, import a file.
- Sidebar, **Import surfaces**:
  - File: the `.dat` grid. **Domain**: time. **Flip sign**: on (the file stores TWT negative).
  - Result: 217 × 238 nodes at 250 m, 23,784 valid, 945–1549 ms. CRS ED50-UTM32, read from the
    file. Without the flip the import still runs, with a warning that most values are negative.

## 2. Convert to depth — tab **2 Surfaces**, Depth conversion

- **Method**: V0 + kZ, with V0 = 1800 m/s and k = 0.5 /s.
- Result: depth 959.5–1702.5 m.
- **Map** shows the surface with its structure contours (50 m, every 250 m labelled) and the
  area histogram beside the colour bar.
- The lineage under the map reads
  `depth_convert(k=0.5, method=v0k, v0=1800.0) ← import(… flip_sign=True …) ← file (SHA-256 …)`.

## 3. Contours (optional) — tab **3 Contours**

This step is a second way to the structure: needed when the structure exists only as contours,
or to edit it.

- **Make or import** proposes a 50 m interval, chosen from the relief. At 10 m the grid gives
  153 lines.
- **Edit**: a box on the map selects lines, and **Delete selected** makes a new version of the
  set. A confirmed closure is drawn on this map as an orange dashed line.
- **Make surface** with the thin-plate spline reproduces the main closure: crest within 0.2 m,
  the same spill, GRV −0.05 % (`docs/BENCHMARK.md`).

## 4. Interpret the closure — tab **4 Closure**

- **Minimum closure height**: 10 m. The candidates are:

  | Crest (m) | Spill (m) | Height (m) | Spill reaches |
  |---|---|---|---|
  | 959.5 | 1145.1 | 185.6 | data limit |
  | 999.9 | 1055.6 | 55.7 | data limit |
  | 1188.3 | 1202.2 | 13.9 | data limit |

- For the 959.5 m crest, the first spill event is the data limit at 1145.1 m. The saddle
  towards the 999.9 m culmination is at the same depth.
- The preview draws the footprint as the depth contour at the chosen spill.
- **Confirm this interpretation** records the closure: 2,413 nodes, spill resolved to about
  ±1.8 m. The assumptions include the single fill point, 8-connectivity, and the absence of
  faults.

## 5. Area and GRV — tab **5 Volumes**

- **Geometry**: top surface and a constant thickness of 50 m.
- At the spill the area is 150.61 km², the direct GRV 5,626.5 × 10⁶ m³ and the area–depth GRV
  5,622.0 × 10⁶ m³ (0.1 % apart).
- The HCWC Builder CSV export from this tab is accepted by the Builder's own reader, and its GRV
  equals the area–depth GRV.

## 6. Contacts — tab **6 Contacts**

- **Import from HCWC Builder**: CSV `hcwc_percentiles_geological.csv` (basis read from the name)
  plus the prospect file.
  - **Conditioning**: conditioned on H ≥ h_min. **Tails**: truncated.
  - **F(h_min)** = 0.8891, typed from the Builder results. **h_min** = 120 m, typed.
  - These replace the defaults (0 m and 1). The prospect file's inputs say 100 m; its stale
    `resolved` block says 120 m, which is what the export was run with.
  - The prospect file supplies P(G) = 0.40824 (product of the element chances in its inputs),
    the apex (2050.0 m) and the Builder spill (2200 m).
- A table can be pasted instead: either column order, decimal commas accepted.

## 7. POS and the result — tab **7 POS & results**

- **POS map**, event (a), contacts re-anchored to the map crest:
  - Shift −1090.5 m. POS at the crest 0.363, equal to the Prospect POS P(G) · F(h_min).
  - The map shows POS colours inside the trap only, under the structure contours, with the spill
    contour in orange and the crest marked. The histogram beside the colour bar gives the trap
    area per POS interval.
  - The app warns that the map spill (1145.1 m) differs from the Builder spill after the shift
    (1109.5 m) by +35.6 m. The distribution was built for the other spill.
- **Event (b)** from the same conditioned table is equal to (a) deeper than apex + h_min, and
  flagged "not determinable" in the band above it.
- **Area and GRV by percentile**:
  - GRV P90 3,310, P50 4,647, P10 5,626 × 10⁶ m³; area P90 83.7, P50 116.2, P10 150.6 km².
  - 30.4 % of the contacts lie deeper than the map spill and are taken at the spill, which is
    why P10 equals the GRV at the spill.
- **Prospect summary** builds one printable HTML page from the POS map and everything it was
  made from: key facts, the map, the charts, assumptions, warnings, and the source files'
  SHA-256.

## 8. Save and check — tab **1 Start**

- **Download project file** (0.9 MB) keeps a copy outside the autosave. **Open** it in a new
  session, then **Run the replay check** under **Audit**: every object is recomputed from the
  source files and reproduces exactly.

## What to compare on a real prospect

For an external check, the most useful reference is a prospect with an area–depth table or GRV
from GeoX, Petrel or a spreadsheet, together with its depth grid. Repeat steps 1–5 and compare:
- the area at a few contact depths;
- the GRV at the spill;
- the spill depth itself.

A difference is a finding to explain — grid resolution, closure definition, base geometry — not
a number to tune away.
