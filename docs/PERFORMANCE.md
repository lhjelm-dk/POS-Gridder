# Performance on the GEUS grid

*2026-10-19, POS-Gridder 0.2.0, Windows 11, Python 3.12. Measured by `scripts/profile_geus.py`
on the GEUS Top Gassum grid (217 × 238 = 51,646 nodes, 23,784 valid, 250 m).*

| Step | Seconds |
|---|---|
| Import ZMAP+ | 0.01 |
| Depth conversion (V0 + kZ) | < 0.01 |
| Crest candidates | 0.14 |
| Closure (fill depth, events, footprint) | 0.13 |
| Volumes (area–depth at 1 m, three GRV curves) | 0.07 |
| Contact distribution | < 0.01 |
| POS map | < 0.01 |
| Area/GRV by percentile | 0.01 |
| Contours at 10 m | 0.01 |
| **Contours → surface, thin-plate spline** | **10.6** |
| Project save | 0.06 |
| Project load (hash checks) | 0.01 |
| **Replay check (every object)** | **10.8** |
| App, first run with the full project | 2.0 |
| App, rerun without a change | 0.36 |

The project file is 0.9 MB for nine objects.

**Reading the numbers:**
- Every interactive step finishes well under a second.
- The two slow steps are deliberate actions: making a surface from contours with the spline,
  and the replay check, which repeats that step. Both show a progress spinner.
- The spline's time grows with the number of contour vertices (here about 150 contour lines at
  10 m) and with the number of nodes.
- Linear TIN does the same step in about a second, at the accuracy cost recorded in
  `docs/BENCHMARK.md`.
- Streamlit runs every tab on each rerun. With a full project a rerun takes 0.36 s, so running
  only the selected tab (`st.tabs(on_change="rerun")`) is not needed yet. It is the first lever
  if a larger project makes reruns slow.
