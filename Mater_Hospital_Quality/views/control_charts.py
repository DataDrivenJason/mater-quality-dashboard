"""Control charts: the monthly chart behind every scorecard."""

from __future__ import annotations

import streamlit as st

from core import mdc
from core.charts import control_chart, fmt
from core.kpis import KPI_BY_KEY, LOS_LABEL, PILLAR_LAYOUT, PILLARS, SITE_NAME
from core.state import setup

ctx = setup()

st.title(f"{SITE_NAME} control charts")
st.caption("The blue line is the monthly figure and the grey line is the average. The dashed "
           "lines are the limits we'd expect month to month, and the dotted line is the target. "
           "A diamond means something has genuinely changed: blue for better, orange for worse, "
           "purple where there's no better or worse. Anything inside the limits is normal "
           "variation.")

chart_pillars = [p for p in PILLARS if p != "Equitable"]
choice = st.radio("Pillar", ["All"] + chart_pillars, horizontal=True, key="cc_pillar",
                  label_visibility="collapsed")
show = chart_pillars if choice == "All" else [choice]


def verdict_line(v: mdc.MDCVerdict) -> None:
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown(mdc.icon_pair_html(v, size=26), unsafe_allow_html=True)
    with c2:
        st.caption(v.action)


for pillar in show:
    st.header(pillar)
    for key in PILLAR_LAYOUT[pillar]:
        if key == "los_top5":
            st.subheader(LOS_LABEL)
            st.caption("There's a separate chart for each diagnosis, so a busy month for TIAs "
                       "doesn't look like shorter stays overall. These are the five most common "
                       "diagnoses, grouped by the month the patient went home.")
            if not ctx.los:
                st.info("No data yet.")
            for res in ctx.los:
                st.plotly_chart(control_chart(res, res.label, height=240), key=f"los_{res.label}")
                verdict_line(mdc.verdict(res))
            continue
        kpi = KPI_BY_KEY[key]
        st.subheader(kpi.label)
        st.caption(kpi.definition)
        res = ctx.results.get(key)
        if res is None:
            st.info("No data yet.")
            continue
        st.plotly_chart(control_chart(res), key=f"cc_{key}")
        verdict_line(ctx.verdicts[key])
        notes = []
        if res.meta.get("laney_applied"):
            notes.append("The limits have been widened a little because the months vary more than "
                         "a simple percentage would (Laney adjustment).")
        if res.meta.get("rule_note"):
            notes.append(res.meta["rule_note"])
        if key == "clinic_wait_median" and "clinic_waiting_list" in ctx.tbl.columns:
            wl = ctx.tbl["clinic_waiting_list"].dropna()
            if len(wl):
                notes.append(f"{int(wl.iloc[-1]):,} people were on the waiting list at the end of "
                             "the latest month. It's worth reading this alongside the median, "
                             "because the median only counts people who have been seen.")
        if kpi.chart == "p":
            notes.append("Months with fewer than 5 patients aren't shown. The most recent months "
                         "appear once everyone has had their 90-day follow-up.")
        for n in notes:
            st.caption(n)
