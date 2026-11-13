"""
Mater Hospital stroke service quality framework
===============================================

Three pages: Scorecards, Control charts, Equity.

    Start:  double-click run_dashboard.bat
    or:     .venv\\Scripts\\python.exe -m streamlit run app.py

Layout
------
    app.py              this file: page setup and the menu
    core/kpis.py        the 17 KPIs, targets and definitions  <- edit targets here
    core/data.py        reading files, cleaning, monthly table, charts
    core/spc.py         control chart engine (XmR, p, c) and special-cause rules
    core/mdc.py         Making Data Count variation and assurance verdicts
    core/equity.py      subgroup comparisons, intervals, FDR, suppression
    core/charts.py      Plotly figures
    core/state.py       loading, the sidebar month filter, shared by all pages
    core/demo.py        simulated demonstration data
    views/              one file per page
    data/               your files go here (data/demo holds the demo data)
"""

from __future__ import annotations

import streamlit as st

from core.kpis import SITE_NAME

st.set_page_config(page_title=f"{SITE_NAME} quality", page_icon="◔", layout="wide",
                   initial_sidebar_state="expanded")

pages = [
    st.Page("views/scorecards.py", title="Scorecards", icon=":material/dashboard:", default=True),
    st.Page("views/control_charts.py", title="Control charts", icon=":material/monitoring:"),
    st.Page("views/equity.py", title="Equity", icon=":material/diversity_3:"),
]
st.navigation(pages).run()
