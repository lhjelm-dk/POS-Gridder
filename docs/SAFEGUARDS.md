# Safeguards register

*2026-10-19, POS-Gridder 0.3.0.* Each finding of the plan review (`docs/PLAN.md` §2), what the
app does about it, and the test that holds it there. A result that runs but applies the wrong
convention is the failure this register exists to prevent.

| # | Risk | What the app does | Test |
|---|---|---|---|
| C1 | POS from a Builder export conditioned on H ≥ h_min, without F(h_min) | The conditioning is declared at import. Event (a) refuses to run without F(h_min). POS at the crest is compared with the Prospect POS | `test_pos.py::test_missing_inputs_are_refused`, `::test_crest_value_equals_builder_prospect_pos` |
| C2 | Prior P(G) with a given-the-DHI table | The basis is read from the file name or declared. P(G) from `.hcwc.json` is refused on the DHI basis | `test_hcwc.py::test_prior_p_g_refused_for_a_dhi_table` |
| C3 | Builder apex ≠ map crest | The difference is always reported, with a warning above 5 m. Contacts can be re-anchored to the map crest | `test_pos.py::test_reanchoring` |
| C4 | Spill at an edge, null or hole assumed silently; diagonal saddles; noise crests | Boundaries are candidates. A spill deeper than a boundary requires explicit acceptance. 8-connectivity by default. Minimum closure height. Spill resolution reported | `test_closure.py` (T9–T13, hand-checked prospect, brute-force reference) |
| C4 | Footprint sweeping in a structure beyond the spill | The footprint stops at the spill point: `s < spill` or `z = spill` | `test_closure.py::test_leaking_neighbour_is_not_swept_in` |
| C5 | Contacts below the map spill; Builder spill ≠ map spill | Contacts are capped at the spill for volumes and the fill-to-spill share is reported. The Builder spill from `.hcwc.json` is compared with the map spill (warning above 5 m) | `test_pos.py::test_percentile_volumes`, `test_hcwc.py::test_builder_spill_is_compared` |
| C6 | Gridding POS directly | Not possible: POS is always a function of the fill depth | `test_pos.py::test_invariants` |
| C7 | Crest undefined inside the innermost contour | Crest points are accepted. Flat-top (TIN) and extrapolation (spline) warnings | `test_contours.py::test_regrid_paraboloid_and_crest_point` |
| C8 | Base footprint mismatch, negative thickness, missing base | The base area is taken within the top footprint. Negative thickness and missing base are counted and flagged. Direct and area–depth GRV agree to within 1 % or a warning appears | `test_volumes.py` |
| C9 | A time grid used as depth | The domain is required at import, with no default. Negative values are flagged. Closure refuses non-depth surfaces. Arithmetic follows a domain table | `test_io_surfaces.py`, `test_closure.py::test_time_surface_refused`, `test_operations.py` |
| C10 | Silent resampling | Misaligned grids are refused. Resampling is its own recorded step | `test_operations.py::test_misaligned_grids_refused_with_resample_hint` |
| C11 | No contour input | GeoPackage, GeoJSON, zipped Shapefile, ASCII | `test_contours.py` |
| C12 | Contour selection in Streamlit | Box and lasso on invisible vertex markers, plus table selection. Box selection confirmed in the browser | `test_app_renders.py::test_contour_workflow` |
| C14 | Untraceable edits | Immutable objects, derivations, stale flags, file SHA-256, replay | `test_model.py`, `test_project_file.py`, `test_acceptance.py` |
| C15 | Percentile order, point masses, tails | Validation with reasons; step at duplicate depths; error bound ±0.015 | `test_hcwc.py` (T14–T17) |
| C16 | Closure in time | Refused | `test_closure.py::test_time_surface_refused` |
| C17 | Faults | Not represented, and said so in every closure's assumptions. Manual spill with a reason | `test_contours.py::test_crs_mismatch_refused_for_contours_and_outlines`, `test_closure.py::test_manual_spill_needs_a_reason` |
| C18 | Vertical vs true thickness | Vertical, stated on every GRV result | `test_volumes.py` (assumption text) |
| C20 | Different coordinate systems combined | Refused for surfaces, contours on a template, and outlines on volumes and POS. A missing CRS gives a warning | `test_operations.py::test_different_crs_refused`, `test_contours.py::test_crs_mismatch_refused_for_contours_and_outlines` |
| — | Project file damaged or edited | Every source and object is hash-checked on load | `test_project_file.py::test_tampered_*` |
| — | Older project files after an upgrade | Hashes stay compatible. The replay check names the version that made each object | `test_project_file.py::test_project_file_from_version_0_1_loads` |
| — | Work lost on a restart; one session's autosave overwriting another's | Every change autosaved. A session's first write moves the previous session aside, and the last three are kept. Writes go to a temporary file first, then replace the old one | `test_app_renders.py::test_autosave_reopen_and_rotation`, `::test_autosave_off` |
| — | Default h_min = 0 / F = 1 hiding a conditioned export | Defaults recorded as defaults. A warning appears when the prospect file sets a larger h_min | `test_hcwc.py::test_default_h_min_and_f` |
| — | Decimal commas or swapped columns misread as data | Pasted rows are parsed with decimal commas; the percentile column is detected; a percentile table pasted as a POS curve is refused with where it belongs | `test_hcwc.py::test_paste_formats`, `::test_percentile_table_is_recognised` |
| — | Spill outline drawn on the node edge, not at the spill depth | Drawn as the depth contour at the spill within the footprint | `test_pos.py::test_spill_line_is_a_depth_contour` |

Not covered in v1, by decision: structural uncertainty, faults as barriers, well ties,
reprojection, grid formats other than ZMAP+ (plan §4.2).
