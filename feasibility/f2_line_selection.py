"""F2: can a contour line on a Plotly map be selected (click, box, lasso) in Streamlit?

Run: streamlit run feasibility/f2_line_selection.py
Each contour line is its own scatter trace carrying its line id in customdata. The selection
event is printed below the map, so a click or lasso shows which line ids come back.
"""
from __future__ import annotations

import contourpy
import numpy as np
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="F2 line selection", layout="wide")

x = np.linspace(0, 10_000, 81)
xx, yy = np.meshgrid(x, x)
z = (2000 + 2e-5 * ((xx - 3500) ** 2 + (yy - 5000) ** 2)
     - 120 * np.exp(-(((xx - 7500) / 1200) ** 2 + ((yy - 6000) / 1500) ** 2)))

mode = st.segmented_control("Trace mode", ["lines", "lines+markers", "hidden markers"],
                            default=st.query_params.get("mode", "lines"))
hidden = mode == "hidden markers"
gen = contourpy.contour_generator(x, x, z, line_type=contourpy.LineType.Separate)

fig = go.Figure(go.Heatmap(z=z, x=x, y=x, colorscale="Viridis", showscale=False,
                           hoverinfo="skip"))
line_id = 0
for level in np.arange(2000, 2400, 20):
    for line in gen.lines(level):
        fig.add_trace(go.Scatter(
            x=line[:, 0], y=line[:, 1], mode="lines+markers" if hidden else mode,
            line=dict(color="white", width=2),
            marker=dict(size=4, color="white", opacity=0.0 if hidden else 1.0),
            customdata=np.full(len(line), line_id), name=f"{level:.0f} m #{line_id}",
            hovertemplate=f"{level:.0f} m, line {line_id}<extra></extra>", showlegend=False))
        line_id += 1
fig.update_layout(height=600, yaxis=dict(scaleanchor="x"), dragmode=st.query_params.get("drag", "select"),
                  margin=dict(l=0, r=0, t=0, b=0))

event = st.plotly_chart(fig, key="map", on_select="rerun",
                        selection_mode=("points", "box", "lasso"))
sel = event.selection if event else None
ids = sorted({int(p["customdata"]) if not isinstance(p["customdata"], list) else int(p["customdata"][0])
              for p in (sel.points if sel else []) if "customdata" in p})
st.write(f"**{line_id} lines drawn.** Selected line ids: {ids or 'none'}")
st.json(sel.points[:5] if sel else [], expanded=False)
