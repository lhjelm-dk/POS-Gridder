"""Tabs 6 Contacts and 7 POS & results: contact distributions and typed curves, then POS maps
and area/GRV by percentile.

Nothing about the probability is defaulted: the basis, the conditioning and the tail treatment
of a table are declared, P(G) and F(h_min) are typed or read from the Builder prospect file
(where each came from is recorded), and every map names its event.
"""
from __future__ import annotations


import numpy as np
import pandas as pd
import streamlit as st

from posgridder.core.hcwc import (BASES, CONDITIONINGS, ERROR_BOUND, TAILS, PosCurve,
                                  TableError, basis_from_filename, looks_like_percentiles,
                                  parse_pasted, parse_rows)
from posgridder.core.model import ProjectError
from posgridder.core.operations import apply, recalculate
from posgridder.core.pos import ANCHORINGS, EVENTS
from posgridder.io.hcwc_files import import_area_depth, import_hcwc
from posgridder.io.report import results_json
from posgridder.io.zmap import write_zmap
from posgridder.plotting.charts import exceedance_figure, percentile_figure
from posgridder.plotting.maps import POS_SCALES, pos_figure
from posgridder.ui.state import notify, project, uid_of

#: The default pair: every successful column counts (h_min 0 m), so every success passes (F 1).
DEFAULT_H_MIN, DEFAULT_F_HMIN = 0.0, 1.0

SECTIONS = ["Contact distribution", "Typed POS curves", "POS map", "Area and GRV by percentile",
            "Prospect summary"]


def _names(kind: str) -> list[str]:
    proj = project()
    return [proj.objects[u].name for u in proj.current(kind)]


def _meta_fields(prefix: str) -> dict:
    c1, c2, c3 = st.columns(3)
    basis = c1.selectbox("Basis", list(BASES), format_func=BASES.get, index=None,
                         placeholder="From the file name, or choose", key=f"{prefix}_basis",
                         help="The Builder names its export hcwc_percentiles_<basis>.csv.")
    conditioning = c2.selectbox("Conditioning", list(CONDITIONINGS), format_func=CONDITIONINGS.get,
                                index=None, placeholder="Required", key=f"{prefix}_cond",
                                help="A current HCWC Builder export holds only the realisations "
                                     "whose column reaches the assessment minimum h_min.")
    tails = c3.selectbox("Tails", list(TAILS), format_func=TAILS.get, index=None,
                         placeholder="Required", key=f"{prefix}_tails")
    c1, c2, c3, c4 = st.columns(4)
    p_g = c1.number_input("P(G)", min_value=0.0, max_value=1.0, value=None, format="%.4f",
                          placeholder="from the .hcwc.json", key=f"{prefix}_pg",
                          help="The geological accumulation chance. On the given-the-DHI basis "
                               "it is P(G | DHI) and must be typed.")
    f_hmin = c2.number_input("F(h_min)", min_value=0.0, max_value=1.0,
                             value=DEFAULT_F_HMIN, format="%.4f", key=f"{prefix}_f",
                             help="The chance, given success, that the column reaches h_min, "
                                  "from the Builder results (Prospect POS ÷ P(G)). The default "
                                  "1 goes with h_min = 0 m: every successful column counts.")
    h_min = c3.number_input("h_min (m)", min_value=0.0, value=DEFAULT_H_MIN, format="%.1f",
                            key=f"{prefix}_hmin",
                            help="The assessment minimum column set in the Builder. The default "
                                 "0 m counts every successful column; clear the field to take "
                                 "it from the .hcwc.json.")
    apex = c4.number_input("Builder apex (m)", value=None, format="%.1f",
                           placeholder="from the .hcwc.json", key=f"{prefix}_apex")
    defaulted = [k for k, v, d in (("h_min", h_min, DEFAULT_H_MIN),
                                   ("f_hmin", f_hmin, DEFAULT_F_HMIN)) if v == d]
    return dict(basis=basis, conditioning=conditioning, tails=tails, p_g=p_g, f_hmin=f_hmin,
                h_min=h_min, apex=apex, defaulted=defaulted)


def _check_meta(meta: dict, filename: str | None) -> str | None:
    if meta["basis"] is None and filename:
        meta["basis"] = basis_from_filename(filename)
    for key, label in (("basis", "basis"), ("conditioning", "conditioning"), ("tails", "tails")):
        if meta[key] is None:
            return f"The {label} is required; it is not inferred."
    return None


def _import_forms() -> None:
    proj = project()
    with st.expander("Import from HCWC Builder", icon=":material/upload_file:",
                     expanded=not _names("hcwc")):
        with st.form("hcwc_import", clear_on_submit=False, border=False):
            c1, c2 = st.columns(2)
            csv = c1.file_uploader("Percentile CSV (Percentile, Value or Depth(m))", type=["csv"])
            js = c2.file_uploader("Prospect file (.hcwc.json), optional", type=["json"],
                                  help="Gives P(G) (product of the element chances in its "
                                       "inputs), h_min and the apex where those are left blank.")
            meta = _meta_fields("imp")
            flip = st.checkbox("Flip the sign of the depths")
            name = st.text_input("Name", placeholder="Default: the file name")
            submitted = st.form_submit_button("Import", type="primary", icon=":material/upload:")
        if submitted:
            if csv is None:
                notify("error", "A percentile CSV is needed.")
            elif (problem := _check_meta(meta, csv.name)) is not None:
                notify("error", problem)
            else:
                try:
                    d = import_hcwc(proj, name=name.strip() or csv.name.rsplit(".", 1)[0],
                                    csv=(csv.name, csv.getvalue()),
                                    json=(js.name, js.getvalue()) if js else None,
                                    flip_sign=flip, **meta)
                    st.session_state["_pending_hcwc"] = d.name
                    notify("success", f"Imported ‘{d.name}’.")
                except (ProjectError, ValueError) as exc:
                    notify("error", str(exc))
            st.rerun()

    with st.expander("Paste or type a table", icon=":material/table_edit:"):
        with st.form("hcwc_paste", clear_on_submit=False, border=False):
            text = st.text_area("Percentile and depth, one row per line, in either column order "
                                "(pasted from a spreadsheet or typed); P100 to P0; decimal "
                                "commas accepted", height=160,
                                placeholder="100\t2126.7\n99\t2139.6\n…\n0\t2377.3")
            js = st.file_uploader("Prospect file (.hcwc.json), optional", type=["json"],
                                  key="paste_json")
            meta = _meta_fields("paste")
            name = st.text_input("Name", value="typed contact distribution")
            submitted = st.form_submit_button("Add table", icon=":material/add:")
        if submitted:
            if (problem := _check_meta(meta, None)) is not None:
                notify("error", problem)
            else:
                try:
                    p, d = parse_pasted(text)
                    dist = import_hcwc(proj, name=name, table={"percentiles": p, "depths": d},
                                       json=(js.name, js.getvalue()) if js else None,
                                       origin="pasted or typed table", **meta)
                    st.session_state["_pending_hcwc"] = dist.name
                    notify("success", f"Added ‘{dist.name}’.")
                except (TableError, ProjectError, ValueError) as exc:
                    notify("error", str(exc))
            st.rerun()


def _stale(uid: str, key: str) -> None:
    proj = project()
    for reason in proj.stale_reasons(uid):
        st.warning(f"Stale: {reason}.", icon=":material/history:")
    if proj.is_stale(uid) and st.button("Recalculate", icon=":material/refresh:", key=key):
        try:
            recalculate(proj, uid)
            notify("success", "Recalculated as a new version.")
        except ProjectError as exc:
            notify("error", str(exc))
        st.rerun()


def _distribution_section() -> None:
    proj = project()
    _import_forms()
    names = _names("hcwc")
    if not names:
        return
    pending = st.session_state.pop("_pending_hcwc", None)
    if pending in names:
        st.session_state["hcwc_view"] = pending
    name = st.selectbox("Contact distribution", names, key="hcwc_view")
    d = proj.objects[uid_of(name)]
    for w in d.warnings:
        st.warning(w, icon=":material/warning:")
    left, right = st.columns([2, 3])
    with left:
        st.dataframe(pd.DataFrame({"Property": [
            "Basis", "Conditioning", "Tails", "P(G)", "F(h_min)", "h_min", "Builder apex",
            "Rows", "Origin"], "Value": [
            BASES[d.basis], CONDITIONINGS[d.conditioning], TAILS[d.tails],
            "—" if d.p_g is None else f"{d.p_g:.4f}",
            "—" if d.f_hmin is None else f"{d.f_hmin:.4f}",
            "—" if d.h_min is None else f"{d.h_min:g} m",
            "—" if d.apex is None else f"{d.apex:.1f} m", str(len(d.depths)), d.origin]}),
            hide_index=True)
        if d.sources:
            st.caption("Where the values came from: " + "; ".join(d.sources) + ".")
        st.caption(f"The exceedance is read linearly between rows, to within ±{ERROR_BOUND:.3f}.")
    with right:
        z = np.linspace(d.depths[0] - 0.05 * (d.depths[-1] - d.depths[0]),
                        d.depths[-1] + 0.05 * (d.depths[-1] - d.depths[0]), 400)
        mult = None
        if d.p_g is not None:
            mult = d.p_g * (d.f_hmin if d.conditioning == "h_min" and d.f_hmin is not None
                            else 1.0)
        marks = {}
        if d.apex is not None:
            marks["apex"] = d.apex
            if d.h_min is not None:
                marks["apex + h_min"] = d.apex + d.h_min
        st.plotly_chart(exceedance_figure(z, d.exceedance()(z), multiplier=mult, marks=marks),
                        key="exceedance_chart")

    with st.expander("Edit the table", icon=":material/edit:"):
        frame = pd.DataFrame({"Percentile": d.percentiles, "Depth (m)": d.depths})
        edited = st.data_editor(frame, hide_index=True, disabled=["Percentile"], height=300,
                                key=f"editor_{d.uid}")
        if st.button("Save the edits as a new version", icon=":material/save:", key="hcwc_save"):
            new = edited["Depth (m)"].to_numpy(float)
            changed = np.flatnonzero(~np.isclose(new, d.depths, rtol=0, atol=1e-9))
            if not changed.size:
                notify("info", "No row was changed.")
                st.rerun()
            rows = ", ".join(f"P{d.percentiles[k]:g} ({d.depths[k]:g} → {new[k]:g} m)"
                             for k in changed)
            old = d.derivation
            params = {k: v for k, v in old.params.items() if k not in ("roles", "table", "origin")}
            roles = old.params.get("roles", [])
            inputs = [u for r, u in zip(roles, old.inputs) if r == "json"]
            params.update(roles=["json"] * len(inputs), flip_sign=False,
                          table={"percentiles": d.percentiles.tolist(), "depths": new.tolist()},
                          origin=f"edited from '{d.name}': {rows}")
            try:
                apply(proj, "hcwc", inputs, params, name=d.name, supersedes=d.uid)
                notify("success", f"Saved a new version of ‘{d.name}’ ({len(changed)} rows "
                                  "changed). Maps made from the earlier one are now stale.")
            except ProjectError as exc:
                notify("error", str(exc))
            st.rerun()


def _curves_section() -> None:
    proj = project()
    st.caption("A depth → POS table typed by the interpreter, such as a POS for each contour "
               "level. Between rows it is linear in depth; it is forced to 0 at the spill.")
    with st.form("pos_curve", clear_on_submit=False, border=False):
        text = st.text_area("Depth (m) and POS (%), one row per line; decimal commas accepted",
                            height=120,
                            placeholder="2300 24\n2400 13")
        meaning = st.radio("The values are", list(PosCurve.MEANINGS),
                           format_func=PosCurve.MEANINGS.get, index=None, horizontal=True)
        name = st.text_input("Name", value="typed POS curve")
        submitted = st.form_submit_button("Add curve", icon=":material/add:")
    if submitted:
        if meaning is None:
            notify("error", "State whether the values include P(G) or are conditional on G.")
        else:
            try:
                arr = parse_rows(text, 2)
                if len(arr) > 20 and (looks_like_percentiles(arr[:, 0])
                                      or looks_like_percentiles(arr[:, 1])):
                    raise ValueError("this is a contact percentile table (one column runs from "
                                     "100 to 0); it belongs under Contact distribution → "
                                     "Paste or type a table")
                depths = arr[:, 0].tolist()
                values = (arr[:, 1] / 100.0).tolist()
                c = apply(proj, "pos_curve", [], {"depths": depths, "values": values,
                                                  "meaning": meaning}, name=name)
                notify("success", f"Added ‘{c.name}’.")
            except (ValueError, IndexError, ProjectError) as exc:
                notify("error", f"Curve not added: {exc}")
        st.rerun()
    uids = proj.current("poscurve")
    if uids:
        st.dataframe(pd.DataFrame([{
            "Name": proj.objects[u].name, "Meaning": PosCurve.MEANINGS[proj.objects[u].meaning],
            "Rows": "; ".join(f"{dd:g} m: {vv:.0%}" for dd, vv in
                              zip(proj.objects[u].depths, proj.objects[u].values))}
            for u in uids]), hide_index=True)


def _map_section() -> None:
    proj = project()
    closures, dists, curves = _names("closure"), _names("hcwc"), _names("poscurve")
    if not closures:
        st.info("A POS map is drawn on a confirmed closure (tab **4 Closure**).",
                icon=":material/info:")
    elif not dists and not curves:
        st.info("A POS map needs a contact distribution or a typed POS curve.",
                icon=":material/info:")
    else:
        kinds = [k for k, have in (("Contact distribution", dists), ("Typed curve", curves))
                 if have]
        source = st.segmented_control("From", kinds, default=kinds[0], key="pos_from") or kinds[0]
        with st.form("pos_map", border=False):
            closure = st.selectbox("Closure", closures)
            params: dict = {}
            if source == "Contact distribution":
                src = st.selectbox("Contact distribution", dists)
                c1, c2 = st.columns(2)
                params["event"] = c1.radio("Event", list(EVENTS), index=None,
                                           format_func=lambda k: f"({k}) {EVENTS[k]}")
                params["anchoring"] = c2.radio("Contact depths", list(ANCHORINGS), index=0,
                                               format_func=ANCHORINGS.get)
                role = "hcwc"
            else:
                src = st.selectbox("Typed curve", curves)
                params["p_g"] = st.number_input("P(G), for a curve conditional on G",
                                                min_value=0.0, max_value=1.0, value=None,
                                                format="%.4f")
                role = "curve"
            outline = st.selectbox("Outline", ["None", *_names("outline")])
            name = st.text_input("Name", placeholder="Default: describes the map")
            submitted = st.form_submit_button("Map POS", type="primary", icon=":material/map:")
        if submitted:
            if role == "hcwc" and params["event"] is None:
                notify("error", "Choose the event the map shows.")
                st.rerun()
            c = proj.objects[uid_of(closure)]
            roles = ["closure", "top", role]
            inputs = [c.uid, c.surface_uid, uid_of(src)]
            if outline != "None":
                roles.append("outline")
                inputs.append(uid_of(outline))
            params["roles"] = roles
            label = f"event ({params['event']})" if role == "hcwc" else "typed"
            try:
                m = apply(proj, "pos_map", inputs, params,
                          name=name.strip() or f"POS {label} · {src} · {closure}")
                st.session_state["_pending_map"] = m.name
                notify("success", f"Mapped ‘{m.name}’.")
            except ProjectError as exc:
                notify("error", str(exc))
            st.rerun()

    maps = _names("posmap")
    st.subheader("POS maps", divider="gray")
    if not maps:
        st.caption("None yet.")
        return
    pending = st.session_state.pop("_pending_map", None)
    if pending in maps:
        st.session_state["map_view"] = pending
    m = proj.objects[uid_of(st.selectbox("Map", maps, key="map_view"))]
    _stale(m.uid, "map_recalc")
    s = m.summary
    with st.container(horizontal=True):
        if "event" in s:
            st.metric("Event", f"({s['event']})", help=EVENTS[s["event"]], border=True)
        st.metric("Multiplier", f"{s['multiplier']:.4f}", border=True,
                  help="P(G) · F(h_min) for event (a) from a conditioned table; P(G) otherwise; "
                       "1 or P(G) for a typed curve.")
        st.metric("Highest POS", f"{s['max_pos']:.1%}", border=True)
        if s.get("pos_at_crest") is not None:
            st.metric("POS at the crest", f"{s['pos_at_crest']:.2%}",
                      delta=f"{s['pos_at_crest'] - s['prospect_pos']:+.2%} vs Prospect POS",
                      delta_color="off", border=True)
        if s.get("shift_m"):
            st.metric("Contact shift", f"{s['shift_m']:+.1f} m", border=True)
    for w in m.warnings:
        st.warning(w, icon=":material/warning:")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        scale = st.selectbox("Colour scale", list(POS_SCALES), key="pos_scale", width=180)
        reverse = st.toggle("Reverse", key="pos_scale_reverse")
        hist = st.toggle("Histogram", value=True, key="pos_hist",
                         help="Trap area in each POS interval, beside the colour bar.")
        structure_on = st.toggle("Structure contours", value=True, key="pos_structure",
                                 help="Depth contours of the top surface over the POS colours, "
                                      "with the spill contour and the crest.")
    roles = dict(zip(m.derivation.params.get("roles", []), m.derivation.inputs))
    top = proj.objects.get(roles.get("top"))
    closure = proj.objects.get(roles.get("closure"))
    st.plotly_chart(pos_figure(m, scale=scale, reverse=reverse, histogram=hist,
                               structure=top if structure_on else None,
                               closure=closure if structure_on else None),
                    key="pos_map_chart")
    left, right = st.columns(2)
    with left:
        st.markdown("Assumptions:\n\n" + "\n".join(f"- {a}" for a in m.assumptions))
    with right:
        st.dataframe(pd.DataFrame([{"Region": k, "Area (km², node count)": round(v, 3)}
                                   for k, v in s["area_km2_by_category"].items() if v > 0]),
                     hide_index=True)
    with st.container(horizontal=True):
        st.download_button("POS grid (ZMAP+)", write_zmap(m).encode(), file_name=f"{m.name}.dat",
                           icon=":material/download:", on_click="ignore",
                           help="POS as a fraction; null wherever no POS is mapped.")
        st.download_button("Report (JSON)", results_json(proj, m.uid),
                           file_name=f"{m.name} report.json", mime="application/json",
                           icon=":material/description:", on_click="ignore")


def _percentile_section() -> None:
    proj = project()
    with st.expander("Import an area–depth table (HCWC Builder format)", icon=":material/upload:"):
        with st.form("ad_import", clear_on_submit=True, border=False):
            up = st.file_uploader("Area–depth CSV: depth, top area (km²), optional base area",
                                  type=["csv"])
            ok = st.form_submit_button("Import", icon=":material/upload:")
        if ok and up is not None:
            try:
                v = import_area_depth(proj, up.name, up.getvalue())
                notify("success", f"Imported ‘{v.name}’.")
            except (ProjectError, ValueError) as exc:
                notify("error", str(exc))
            st.rerun()
    vols, dists = _names("volumes"), _names("hcwc")
    if vols and dists:
        with st.form("pctvol", border=False):
            c1, c2, c3 = st.columns(3)
            vol = c1.selectbox("Volumes", vols)
            dist = c2.selectbox("Contact distribution", dists, key="pv_dist")
            anchoring = c3.radio("Contact depths", list(ANCHORINGS), format_func=ANCHORINGS.get)
            submitted = st.form_submit_button("Evaluate", type="primary",
                                              icon=":material/stacked_line_chart:")
        if submitted:
            try:
                pv = apply(proj, "percentile_volumes", [uid_of(vol), uid_of(dist)],
                           {"anchoring": anchoring}, name=f"{dist} on {vol}")
                st.session_state["_pending_pv"] = pv.name
                notify("success", f"Evaluated ‘{pv.name}’.")
            except ProjectError as exc:
                notify("error", str(exc))
            st.rerun()
    else:
        st.info("Needs a volume result (tab **5 Volumes**, or an imported area–depth table) "
                "and a contact distribution.", icon=":material/info:")
    results = _names("pctvol")
    if not results:
        return
    pending = st.session_state.pop("_pending_pv", None)
    if pending in results:
        st.session_state["pv_view"] = pending
    pv = proj.objects[uid_of(st.selectbox("Result", results, key="pv_view"))]
    _stale(pv.uid, "pv_recalc")
    s = pv.summary
    with st.container(horizontal=True):
        for p in (90, 50, 10):
            st.metric(f"GRV P{p}", f"{s[f'grv_P{p}_1e6m3']:,.1f} × 10⁶ m³",
                      help=f"Area P{p}: {s[f'area_P{p}_km2']:.3f} km²", border=True)
        st.metric("Contacts below the spill", f"{s['p_contact_below_spill']:.1%}", border=True)
        st.metric("Contacts above the crest", f"{s['p_contact_above_crest']:.1%}", border=True)
    for w in pv.warnings:
        st.warning(w, icon=":material/warning:")
    st.markdown("Assumptions:\n\n" + "\n".join(f"- {a}" for a in pv.assumptions))
    st.plotly_chart(percentile_figure(pv.table), key="pct_chart")
    st.dataframe(pv.table.rename(columns={
        "percentile": "Percentile", "contact_m": "Contact (m)", "contact_used_m": "Used (m)",
        "area_km2": "Area (km²)", "grv_1e6m3": "GRV (10⁶ m³)",
        "grv_single_fill_1e6m3": "GRV single fill (10⁶ m³)"}), hide_index=True, height=260)
    with st.container(horizontal=True):
        st.download_button("Table (CSV)", pv.table.to_csv(index=False), file_name=f"{pv.name}.csv",
                           mime="text/csv", icon=":material/download:", on_click="ignore")
        st.download_button("Report (JSON)", results_json(proj, pv.uid),
                           file_name=f"{pv.name} report.json", mime="application/json",
                           icon=":material/description:", on_click="ignore")


CONTACT_SECTIONS = SECTIONS[:2]
RESULT_SECTIONS = SECTIONS[2:]


def render_contacts() -> None:
    """Tab 6 Contacts: contact distributions from HCWC Builder, and typed POS curves."""
    section = st.segmented_control("Section", CONTACT_SECTIONS, default=CONTACT_SECTIONS[0],
                                   key="contacts_section",
                                   label_visibility="collapsed") or CONTACT_SECTIONS[0]
    if section == CONTACT_SECTIONS[0]:
        _distribution_section()
    else:
        _curves_section()


def render_results() -> None:
    """Tab 7 POS & results: the POS map on the structure, and area and GRV by percentile."""
    section = st.segmented_control("Section", RESULT_SECTIONS, default=RESULT_SECTIONS[0],
                                   key="results_section",
                                   label_visibility="collapsed") or RESULT_SECTIONS[0]
    if section == RESULT_SECTIONS[0]:
        _map_section()
    elif section == RESULT_SECTIONS[1]:
        _percentile_section()
    else:
        _summary_section()


def _summary_section() -> None:
    from posgridder.io.summary import build, related

    proj = project()
    maps = _names("posmap")
    if not maps:
        st.info("The summary is built from a POS map; none has been made yet.",
                icon=":material/info:")
        return
    st.caption("One printable page: the structure and volume, the chance of success, the POS "
               "map on the structure, the volumes by percentile, every assumption and warning, "
               "and the source files with their SHA-256.")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        name = st.selectbox("POS map", maps, key="summary_map", width=420)
        scale = st.selectbox("Colour scale", list(POS_SCALES), key="summary_scale", width=180)
    uid = uid_of(name)
    parts = related(proj, uid)
    found = [label for key, label in (("closure", "closure"), ("top", "top surface"),
                                      ("volumes", "volumes"), ("hcwc", "contacts"),
                                      ("curve", "typed curve"),
                                      ("pctvol", "volumes by percentile")) if key in parts]
    st.write("Draws on: " + ", ".join(found) + ".")
    if "pctvol" not in parts and "hcwc" in parts:
        st.caption("No area/GRV-by-percentile result was made from this closure's volumes and "
                   "these contacts; the page leaves that section out.")
    if st.button("Build the summary", type="primary", icon=":material/description:"):
        with st.spinner("Building the page…"):
            st.session_state["_summary"] = (uid, scale, build(proj, uid, scale=scale))
    built = st.session_state.get("_summary")
    if built and built[0] == uid and built[1] == scale:
        st.download_button("Download the summary (HTML)", built[2].encode("utf-8"),
                           file_name=f"{name} summary.html", mime="text/html",
                           icon=":material/download:", on_click="ignore")
        st.caption("Opens in any browser, without a network; print it from there for a PDF.")
