# POS-Gridder

Surfaces, contours and spatial chance of success for prospect evaluation.

POS-Gridder is a Streamlit app for one workflow:
1. import a structure map;
2. interpret its closure and spill;
3. measure area–depth and gross rock volume;
4. bring in the hydrocarbon–water contact distribution from HCWC Builder;
5. map the chance of success (POS) on the structure;
6. read area and GRV at every contact percentile.

Every result records how it was made and can be recomputed from the imported files.

Version 0.3.0 · MIT licence · by Lars Hjelm

## What it does, tab by tab

| Tab | |
|---|---|
| **1 Start** | Reopen the last project (autosaved), load the example, open or save a project file; replay check and history under **Audit** |
| **2 Surfaces** | Map with structure contours and an area histogram; depth conversion (constant velocity, velocity surface, V0 + kZ), domain-checked arithmetic, resampling |
| **3 Contours** | Make contours from a surface or import them (GeoPackage, GeoJSON, zipped Shapefile, ASCII `x y z id`); select and delete lines on the map; make a surface from contours (thin-plate spline or linear TIN) |
| **4 Closure** | Candidate crests and spills (model edge, data limit, interior null, saddle); the interpreter confirms one, accepting each boundary explicitly |
| **5 Volumes** | Area–depth and GRV for top + base, top + constant thickness, top + thickness surface; outline clipping; HCWC Builder and SCOPE-HC area–depth export |
| **6 Contacts** | Contact distributions from the HCWC Builder CSV and `.hcwc.json`, or pasted, typed and edited; typed depth → POS curves |
| **7 POS & results** | POS on the structure contours, for a column of at least h_min or for any column; area and GRV by contact percentile; a one-page prospect summary (HTML, prints to PDF) |

A progress strip above the tabs shows which steps are done and names the next one. The
sidebar holds the surfaces and lists everything in the project, with stale results marked.

## Quick start (local)

Python 3.11 or newer:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the app, go to **1 Start** and click **Load example project**: a synthetic two-dome
surface for trying every step. [`docs/WORKED_EXAMPLE.md`](docs/WORKED_EXAMPLE.md) walks
through a real grid with the numbers to expect.

## Deploy on Streamlit Community Cloud

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with the GitHub account that holds
   this repository, and give Community Cloud access to it.
2. Create a new app from GitHub: repository `lhjelm-dk/POS-Gridder`, branch `main`, main file
   `app.py`. For a private repository, check the app's sharing settings, so only the intended
   viewers can open it.
3. Under **Advanced settings** set **Python 3.12**. It cannot be changed after the app is
   created.
4. **Deploy.** The app installs from `requirements.txt`. Every package ships as a wheel,
   GDAL included (through pyogrio), so no `packages.txt` is needed. The colours come from
   `.streamlit/config.toml`.

**Hosted, the app behaves differently in three ways:**
- **Autosave is off by default.** One server serves every visitor, so a shared autosave folder
  would hand one user's project to the next. Keep work with **Download project file** on
  **1 Start**, and reopen it with **Open**.
- **Uploaded data leaves your machine.** It goes to Streamlit's servers. For confidential
  prospects, run the app locally.
- **Memory is about 1 GB.** That is ample for grids like the 51,646-node GEUS example.
  Making a surface from dense contours with the spline takes about 11 s there
  ([`docs/PERFORMANCE.md`](docs/PERFORMANCE.md)).

## Data and privacy

- Imported files are never sent anywhere by the app.
- When run locally, every change is autosaved to `~/.pos-gridder/`, and the last three
  sessions are kept, so a restart loses nothing. To switch this off, set the environment
  variable `POSGRIDDER_AUTOSAVE=off`; to use another folder, set it to a folder path.
- A project file (`.posgrid.zip`) holds the imported files byte for byte, every version and
  every derivation. The replay check recomputes everything from it.

## File formats

| | Read | Write |
|---|---|---|
| Grids | ZMAP+ ASCII (own reader; honours the header's null value) | ZMAP+ ASCII |
| Contour lines | GeoPackage, GeoJSON, zipped Shapefile, ASCII `x y z id` | GeoPackage |
| Contacts | HCWC Builder percentile CSV (`Percentile`, `Value` or `Depth(m)`), `.hcwc.json`; pasted tables | — |
| Area–depth | HCWC Builder CSV | HCWC Builder CSV, SCOPE-HC CSV |
| Results | — | POS grid (ZMAP+), JSON reports, prospect summary (HTML) |

## Conventions

- Depth in m TVDSS, positive down. Area in km². GRV in 10⁶ m³.
- Contact percentiles follow HCWC Builder's exceedance convention: P100 is the shallowest
  contact.
- Grids are regular and unrotated. Surfaces in different stated coordinate systems are not
  combined; there is no reprojection.

## Documentation

- [`docs/WORKED_EXAMPLE.md`](docs/WORKED_EXAMPLE.md) — the workflow on real data, step by step.
- [`docs/SAFEGUARDS.md`](docs/SAFEGUARDS.md) — every known way to get a plausible but wrong
  answer, what the app does about it, and the test that holds it.
- [`docs/BENCHMARK.md`](docs/BENCHMARK.md) — why the thin-plate spline is the default for
  contours → surface.
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) — timings on a 51,646-node grid.
- [`docs/PLAN.md`](docs/PLAN.md) and [`docs/FEASIBILITY.md`](docs/FEASIBILITY.md) — the
  development plan, the decisions behind it, and the feasibility study.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests that render the whole app carry the `render` marker. `-m "not render"` is the quick
subset that CI runs on pull requests; a push to `main` runs everything.

| Path | What |
|---|---|
| `app.py` | the Streamlit shell: sidebar, progress strip, tabs |
| `posgridder/core/` | the model and the calculations; no Streamlit import |
| `posgridder/io/` | file formats, project files, autosave, reports, the summary |
| `posgridder/plotting/` | maps and charts |
| `posgridder/ui/` | the sidebar and one module per tab |
| `scripts/` | the gridding benchmark, the performance profile and the HCWC Builder fixture generator |
| `tests/` | the test suite |

## Companions

POS-Gridder stands alone. It exchanges files with HCWC Builder (contact percentiles in,
area–depth out), WellVolPOS and SCOPE-HC.

## Licence

MIT — see [`LICENSE`](LICENSE).
