# Contours → surface benchmark (decision D9)

*Generated 2026-10-18 by `scripts/benchmark_gridding.py`, POS-Gridder 0.1.0. Thresholds and method in `posgridder/core/benchmark.py`; plan §7.2.*

Known surfaces are contoured at Δ from a 10 m sampling and regridded onto 50 m nodes; errors are against the exact surface on the same nodes. Depth errors are over nodes between the shallowest and deepest contour. Crest, spill, area and GRV come from the same closure and volume code the app uses.

| Case | Δ (m) | Method | RMS (m) | Max (m) | Spurious | Crest (m) | Spill (m) | Area | GRV | All thresholds |
|---|---|---|---|---|---|---|---|---|---|---|
| plane | 10 | TIN | 0.00 | 0.00 | – | – | – | – | – | pass |
| plane | 10 | TPS | 0.00 | 0.00 | – | – | – | – | – | pass |
| plane | 25 | TIN | 0.00 | 0.00 | – | – | – | – | – | pass |
| plane | 25 | TPS | 0.00 | 0.00 | – | – | – | – | – | pass |
| paraboloid | 10 | TIN | 0.38 | 5.00 | 0.00 | 10.00 | 5.00 | -0.2% | -0.3% | pass |
| paraboloid | 10 | TPS | 0.01 | 0.04 | 0.00 | 0.30 | -0.02 | -0.1% | -0.0% | pass |
| paraboloid | 25 | TIN | 0.79 | 6.25 | 0.00 | 25.00 | 0.00 | -0.3% | -1.5% | pass |
| paraboloid | 25 | TPS | 0.02 | 0.10 | 0.00 | -3.23 | -0.00 | -0.1% | -0.1% | pass |
| cone | 10 | TIN | 0.28 | 2.42 | 0.00 | 10.00 | 0.00 | -0.2% | -0.1% | pass |
| cone | 10 | TPS | 0.02 | 0.27 | 0.00 | 5.99 | 0.00 | -0.1% | -0.0% | pass |
| cone | 25 | TIN | 0.87 | 5.88 | 0.00 | 25.00 | 0.00 | -0.2% | -0.5% | pass |
| cone | 25 | TPS | 0.13 | 0.72 | 0.00 | 15.12 | 0.00 | -0.1% | -0.1% | pass |
| two domes | 10 | TIN | 0.38 | 5.15 | 0.00 | 10.00 | -2.25 | -0.5% | -4.7% | **fail** |
| two domes | 10 | TPS | 0.10 | 2.44 | 0.00 | 0.30 | -1.38 | -0.0% | -0.1% | pass |
| two domes | 25 | TIN | 1.37 | 21.00 | 0.00 | 25.00 | -2.25 | -100.0% | -26.5% | **fail** |
| two domes | 25 | TPS | 0.39 | 5.68 | 0.00 | -4.77 | -1.79 | -0.1% | -0.6% | pass |

**Default method: TPS.**

Failures:
- two domes, Δ 10 m, TIN: max, grv
- two domes, Δ 25 m, TIN: max, area

Signed errors are regridded minus exact: a positive crest error is a crest deeper than the true one (TIN is flat at the innermost contour).
