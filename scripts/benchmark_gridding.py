"""Run the D9 contours→surface benchmark and write docs/BENCHMARK.md.

    python scripts/benchmark_gridding.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from posgridder import __version__  # noqa: E402
from posgridder.core.benchmark import default_method, judge, run  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "BENCHMARK.md"


def fmt(v, kind="m"):
    if v != v:                      # NaN
        return "–"
    return f"{v:+.1%}" if kind == "rel" else f"{v:.2f}"


def main() -> None:
    f = judge(run())
    lines = [
        "# Contours → surface benchmark (decision D9)",
        "",
        f"*Generated {date.today().isoformat()} by `scripts/benchmark_gridding.py`, POS-Gridder "
        f"{__version__}. Thresholds and method in `posgridder/core/benchmark.py`; plan §7.2.*",
        "",
        "Known surfaces are contoured at Δ from a 10 m sampling and regridded onto 50 m nodes; "
        "errors are against the exact surface on the same nodes. Depth errors are over nodes "
        "between the shallowest and deepest contour. Crest, spill, area and GRV come from the "
        "same closure and volume code the app uses.",
        "",
        "| Case | Δ (m) | Method | RMS (m) | Max (m) | Spurious | Crest (m) | Spill (m) | "
        "Area | GRV | All thresholds |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in f.iterrows():
        lines.append(
            f"| {r['case']} | {r['interval_m']:g} | {r['method'].upper()} | {fmt(r['rms_m'])} | "
            f"{fmt(r['max_m'])} | {fmt(r.get('spurious_closures', float('nan')))} | "
            f"{fmt(r.get('crest_error_m', float('nan')))} | "
            f"{fmt(r.get('spill_error_m', float('nan')))} | "
            f"{fmt(r.get('area_error_rel', float('nan')), 'rel')} | "
            f"{fmt(r.get('grv_error_rel', float('nan')), 'rel')} | "
            f"{'pass' if r['pass_all'] else '**fail**'} |")
    failed = f[~f["pass_all"]]
    lines += ["", f"**Default method: {default_method(f).upper()}.**", ""]
    if len(failed):
        lines.append("Failures:")
        for _, r in failed.iterrows():
            checks = [c[5:] for c in f.columns if c.startswith("pass_") and c != "pass_all"
                      and r[c] is False]
            lines.append(f"- {r['case']}, Δ {r['interval_m']:g} m, {r['method'].upper()}: "
                         + ", ".join(checks))
    lines += ["", "Signed errors are regridded minus exact: a positive crest error is a crest "
              "deeper than the true one (TIN is flat at the innermost contour)."]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
