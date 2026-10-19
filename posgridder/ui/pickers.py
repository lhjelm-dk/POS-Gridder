"""A colour-scale picker shared by every map: the same ten scales and a Reverse switch."""
from __future__ import annotations

import streamlit as st

from posgridder.plotting.maps import COLORSCALES


def scale_picker(key: str, default: str = "Viridis") -> tuple[str, bool]:
    """Colour scale and reverse flag, each kept per map under ``key``."""
    scale = st.selectbox("Colour scale", COLORSCALES, index=COLORSCALES.index(default),
                         key=f"{key}_scale", width=200)
    reverse = st.toggle("Reverse", key=f"{key}_reverse")
    return scale, reverse
