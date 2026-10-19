"""A real HCWC Builder export, made by the Builder's own code, as a test fixture.

Runs the limit set stored in the Builder's example file ``example_prospect_spill.hcwc.json``
(its ``resolved`` block; h_min = 120 m, so F(h_min) < 1 and the conditioning is visible), with
the Builder's default trial count and seed, and writes:
  - hcwc_percentiles_geological.csv  : the tab 7.0 export, h >= h_min only (exactly as shipped)
  - hcwc_percentiles_unconditioned.csv: every success realisation, for event (b)
  - builder_reference.json           : F(h_min), h_min, apex median, P10/P50/P90 contacts
This is a one-off generator. POS-Gridder never imports the Builder; only the files are used.

Run with an interpreter that has the Builder's requirements, from anywhere:
    python scripts/make_builder_fixture.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

BUILDER = Path(__file__).resolve().parents[2] / "HCWC builder"
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hcwc_builder"
sys.path.insert(0, str(BUILDER))

from hcwc.core import engine, limits  # noqa: E402
from hcwc.io import geox  # noqa: E402


def main() -> None:
    doc = json.loads((BUILDER / "reference" / "defaults" / "example_prospect_spill.hcwc.json")
                     .read_text(encoding="utf-8"))
    limit_set = limits.LimitSet.from_dict(doc["resolved"])
    inputs = doc["inputs"]
    elements = ("Charge", "Reservoir", "Closure", "Retention")
    p_g = float(np.prod([inputs[f"play_{e}"] * inputs[f"cond_{e}"] for e in elements]))
    result = engine.run(limit_set)                      # Builder defaults: n = 10 000, its seed
    OUT.mkdir(parents=True, exist_ok=True)

    conditioned = geox.percentile_table(result.contact_m[result.above_minimum])
    conditioned.to_csv(OUT / "hcwc_percentiles_geological.csv")
    unconditioned = geox.percentile_table(result.contact_m, basis="unconditioned")
    unconditioned.to_csv(OUT / "hcwc_percentiles_unconditioned.csv")

    reference = {
        "source": "HCWC Builder example_prospect_spill.hcwc.json (resolved limit set), engine.run defaults",
        "note": "the file's resolved block is named 'Tofte North' while its inputs say 'Vestre Low'",
        "P_G_from_inputs": p_g,
        "n_trials": int(result.n),
        "h_min_m": float(limit_set.min_column_m),
        "F_h_min": float(result.above_minimum.mean()),
        "apex_median_m": float(np.median(result.apex_m)),
        "apex_p1_p99_m": [float(v) for v in np.percentile(result.apex_m, [1, 99])],
        "contact_m_conditioned_exceedance_P10_P50_P90": [
            float(v) for v in engine.weighted_percentiles(
                result.contact_m[result.above_minimum], None, [10, 50, 90])],
        "conditioned_provenance": conditioned.provenance,
        "unconditioned_provenance": unconditioned.provenance,
    }
    (OUT / "builder_reference.json").write_text(json.dumps(reference, indent=2), encoding="utf-8")
    print(json.dumps(reference, indent=2))


if __name__ == "__main__":
    main()
