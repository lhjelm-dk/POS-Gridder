"""The one-page prospect summary: a printable HTML page built from a POS map.

Everything on the page comes from the project's objects and their records: the POS map, the
closure and top surface it was made on, the contact distribution or typed curve, the volume
result on the same closure and, when there is one, the area/GRV-by-percentile result made from
both. Nothing is recomputed here. The figures are interactive Plotly, with plotly.js embedded so
the page opens without a network.
"""
from __future__ import annotations

import html
from datetime import datetime

from posgridder import __version__
from posgridder.core.model import Project
from posgridder.core.pos import EVENTS


def related(project: Project, posmap_uid: str) -> dict:
    """The objects a POS map summary draws on, found from the records."""
    m = project.objects[posmap_uid]
    roles = dict(zip(m.derivation.params.get("roles", []), m.derivation.inputs))
    out = {"map": m}
    for role in ("closure", "top", "hcwc", "curve", "outline"):
        if roles.get(role) in project.objects:
            out[role] = project.objects[roles[role]]
    closure = out.get("closure")
    vols = [project.objects[u] for u in project.current("volumes")
            if closure is not None and closure.uid in project.objects[u].derivation.inputs]
    if vols:
        out["volumes"] = vols[-1]
    if "volumes" in out and "hcwc" in out:
        pv = [project.objects[u] for u in project.current("pctvol")
              if project.objects[u].derivation.inputs[:2] == (out["volumes"].uid,
                                                              out["hcwc"].uid)]
        if pv:
            out["pctvol"] = pv[-1]
    return out


def _e(v) -> str:
    return html.escape(str(v))


def _table(rows: list[tuple[str, str]]) -> str:
    return "<table class='kv'>" + "".join(
        f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in rows) + "</table>"


def _list(items) -> str:
    items = [i for i in items if i]
    return ("<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>") if items else \
        "<p class='muted'>None.</p>"


def build(project: Project, posmap_uid: str, *, scale: str = "Blues") -> str:
    """The summary page for one POS map, as an HTML string."""
    from posgridder.plotting.charts import area_depth_figure, percentile_figure
    from posgridder.plotting.maps import pos_figure

    r = related(project, posmap_uid)
    m, closure, top = r["map"], r.get("closure"), r.get("top")
    vol, dist, curve, pv = r.get("volumes"), r.get("hcwc"), r.get("curve"), r.get("pctvol")
    s = m.summary

    facts = []
    if top is not None:
        facts += [("Top surface", f"{top.name} ({top.domain}, {top.crs or 'CRS not stated'})")]
    if closure is not None:
        facts += [("Crest", f"{closure.crest_depth:.1f} m TVDSS"),
                  ("Spill", f"{closure.spill_depth:.1f} m ({closure.spill_type})"),
                  ("Closure height", f"{closure.height:.1f} m")]
    if vol is not None:
        vs = vol.summary
        facts += [("Area at spill", f"{vs['area_at_spill_km2']:.3f} km²"),
                  ("GRV at spill", f"{vs['grv_direct_at_spill_1e6m3']:,.1f} × 10⁶ m³"),
                  ("Geometry", vol.assumptions[1] if len(vol.assumptions) > 1 else vol.geometry)]

    pos_rows = []
    if "event" in s:
        pos_rows.append(("Event", f"({s['event']}) {EVENTS[s['event']]}"))
    pos_rows.append(("Multiplier", f"{s['multiplier']:.4f}"))
    if s.get("p_g") is not None:
        pos_rows.append(("P(G)", f"{s['p_g']:.4f}"))
    if s.get("f_hmin") is not None:
        pos_rows.append(("F(h_min)", f"{s['f_hmin']:.4f}"))
    if s.get("prospect_pos") is not None:
        pos_rows.append(("Prospect POS", f"{s['prospect_pos']:.2%}"))
    if s.get("pos_at_crest") is not None:
        pos_rows.append(("POS at the crest", f"{s['pos_at_crest']:.2%}"))
    pos_rows.append(("Highest POS on the map", f"{s['max_pos']:.2%}"))
    if s.get("shift_m"):
        pos_rows.append(("Contact shift", f"{s['shift_m']:+.1f} m ({s.get('anchoring')})"))
    if dist is not None:
        pos_rows.append(("Contacts", f"{dist.name}: {dist.basis}, {dist.conditioning}, "
                                     f"tails {dist.tails}"))
    if curve is not None:
        pos_rows.append(("Typed curve", f"{curve.name} ({curve.meaning})"))

    pct_html = ""
    if pv is not None:
        ps = pv.summary
        pct_html = "<h2>Volumes by contact percentile</h2>" + _table([
            ("GRV P90 / P50 / P10", f"{ps['grv_P90_1e6m3']:,.1f} / {ps['grv_P50_1e6m3']:,.1f} / "
                                    f"{ps['grv_P10_1e6m3']:,.1f} × 10⁶ m³"),
            ("Area P90 / P50 / P10", f"{ps['area_P90_km2']:.3f} / {ps['area_P50_km2']:.3f} / "
                                     f"{ps['area_P10_km2']:.3f} km²"),
            ("Contacts below the spill", f"{ps['p_contact_below_spill']:.1%}"),
            ("Contacts above the crest", f"{ps['p_contact_above_crest']:.1%}"),
        ]) + percentile_figure(pv.table).to_html(full_html=False, include_plotlyjs=False)

    figs = pos_figure(m, scale=scale, structure=top, closure=closure, height=560).to_html(
        full_html=False, include_plotlyjs=True)
    if vol is not None:
        figs += area_depth_figure(vol.table, vol.summary["spill_depth_m"]).to_html(
            full_html=False, include_plotlyjs=False)

    assumptions, warnings = [], []
    for obj in (closure, vol, dist, curve, m, pv):
        if obj is not None:
            assumptions += list(getattr(obj, "assumptions", ()))
            warnings += [f"{obj.name}: {w}" for w in obj.warnings]
    if dist is not None:
        assumptions += [f"{dist.name}: {src}" for src in dist.sources]
    stale = [project.objects[u].name for u in (o.uid for o in r.values()) if
             u in project.layers and project.is_stale(u)]
    sources = "".join(f"<tr><td>{_e(src.filename)}</td><td><code>{src.sha256}</code></td></tr>"
                      for src in project.sources.values())

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{_e(m.name)} — prospect summary</title>
<style>
body {{ font-family: system-ui, sans-serif; color: #1e1b16; max-width: 1100px; margin: 2em auto;
       padding: 0 1em; line-height: 1.45; }}
h1 {{ font-size: 1.6em; margin-bottom: 0.1em; }} h2 {{ font-size: 1.15em; margin-top: 1.6em;
     border-bottom: 1px solid #d9d5c9; padding-bottom: 0.2em; }}
.muted {{ color: #7a776f; }} .warn {{ background: #fff4e5; padding: 0.6em 1em; }}
table.kv th {{ text-align: left; padding: 0.15em 1.5em 0.15em 0; font-weight: 600; }}
table.kv td {{ padding: 0.15em 0; }} code {{ font-size: 0.85em; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2em; }}
@media print {{ body {{ margin: 0; }} .noprint {{ display: none; }} }}
</style></head><body>
<h1>{_e(m.name)}</h1>
<p class="muted">Prospect summary · POS-Gridder {__version__} ·
{datetime.now():%Y-%m-%d %H:%M}</p>
{f'<p class="warn">Stale: {_e(", ".join(stale))} — made from inputs that have since changed.</p>' if stale else ''}
<div class="cols"><div><h2>Structure and volume</h2>{_table(facts)}</div>
<div><h2>Chance of success</h2>{_table(pos_rows)}</div></div>
<h2>POS on the structure</h2>{figs}
{pct_html}
<h2>Assumptions</h2>{_list(assumptions)}
<h2>Warnings</h2>{_list(warnings)}
<h2>Provenance</h2><p>Every number above is recomputable from these files with the project file
and the replay check.</p><table>{sources}</table>
</body></html>"""
