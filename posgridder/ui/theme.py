"""Tab colours: one accent per numbered tab, as in HCWC Builder, with a palette of its own.

The tint sits in the tab chip's background and the label stays dark ink, so the labels read at
every tint. Low tints — about 18 % unselected, 50 % selected, with a coloured underline on the
selected tab — keep the strip from competing with the maps.

The palette is Paul Tol's "muted" set, colour-blind-safe, in workflow order from cool to warm
(indigo for starting, through the structure greens, to rose for the result). It deliberately
differs from HCWC Builder's, so the two apps are told apart at a glance.

Streamlit gives tabs no documented styling hook. The selectors follow the DOM of Streamlit 1.5x/1.6x
(``[data-testid="stTab"][data-key="N"]``, 0-indexed) with the older baseweb form as a fallback.
If both stop matching, the tabs fall back to Streamlit's default look and nothing else changes;
the numbers in the labels carry the order on their own.
"""
from __future__ import annotations

import streamlit as st

INK = "#1E1B16"

#: Tab number -> (accent colour, name). Order is the tab order.
TAB_COLOURS: dict[int, tuple[str, str]] = {
    1: ("#332288", "Start"),
    2: ("#88CCEE", "Surfaces"),
    3: ("#44AA99", "Contours"),
    4: ("#117733", "Closure"),
    5: ("#999933", "Volumes"),
    6: ("#DDCC77", "Contacts"),
    7: ("#CC6677", "POS & results"),
}


def tab_labels() -> list[str]:
    return [f"{i} {name}" for i, (_, name) in sorted(TAB_COLOURS.items())]


def _css() -> str:
    # The main strip is the one with as many tabs as TAB_COLOURS, so tabs used elsewhere are not
    # painted by position.
    main = f'[role="tablist"]:has([data-testid="stTab"][data-key="{len(TAB_COLOURS) - 1}"])'
    rules = [f"""
      {main} {{ gap: 0.2rem; border-bottom: 1px solid #e6e3da; }}
      {main} [data-testid="stTab"] {{ font-weight: 600; padding: 0.45rem 0.95rem;
                                      border-radius: 6px 6px 0 0; }}
      {main} [data-testid="stTabHighlight"],
      .stTabs [data-baseweb="tab-highlight"] {{ background: transparent !important; }}"""]
    for i, (colour, _) in sorted(TAB_COLOURS.items()):
        current = f'{main} [data-testid="stTab"][data-key="{i - 1}"]'
        legacy = f'.stTabs [data-baseweb="tab-list"] button:nth-child({i})'
        rules.append(f"""
      {current}, {legacy} {{
          background: {colour}2E !important; color: {INK} !important;
          border-bottom: 3px solid transparent;
      }}
      {current}:hover, {legacy}:hover {{ background: {colour}4D !important; }}
      {current}[aria-selected="true"], {legacy}[aria-selected="true"] {{
          background: {colour}80 !important; color: {INK} !important;
          border-bottom: 3px solid {colour} !important;
      }}""")
    return "\n".join(rules)


def apply() -> None:
    """Inject the stylesheet; called once, right after ``st.set_page_config``."""
    st.html(f"<style>{_css()}</style>")
