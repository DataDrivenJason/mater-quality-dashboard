"""Scorecards: every KPI on one page, grouped by the aim of care it serves."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import equity, mdc
from core.charts import fmt
from core.kpis import EQUITY_LABEL, KPI_BY_KEY, LOS_LABEL, PILLAR_LAYOUT, PILLARS, SITE_NAME
from core.state import bucket, latest, setup

ctx = setup()

st.title(f"{SITE_NAME} quality scorecards")
st.caption("The left icon on each card shows whether anything has changed recently. The right "
           "icon shows whether we can expect to hit the target. These are the NHS Making Data "
           "Count icons. We don't use red, amber and green because one month above or below "
           "target is usually just normal variation.")

buckets = pd.Series({k: bucket(v) for k, v in ctx.verdicts.items()}, dtype=object)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Getting worse", int((buckets == "deteriorating").sum()),
          help="Something has changed for the worse. Worth looking into now.")
c2.metric("Steady but missing target", int((buckets == "failing").sum()),
          help="Steady, but the target is out of reach as things stand. The process "
               "needs to change. Chasing individual months won't fix it.")
c3.metric("Hit and miss", int((buckets == "hit_miss").sum()),
          help="Some months meet the target and some don't, mostly by chance.")
c4.metric("Improving", int((buckets == "improving").sum()),
          help="Something has changed for the better.")


def kpi_card(key: str) -> None:
    kpi = KPI_BY_KEY[key]
    res = ctx.results.get(key)
    with st.container(border=True):
        st.markdown(f"**{kpi.label}**")
        if res is None:
            st.markdown("### No data")
            st.caption(f"Add the {kpi.source.replace('service', 'service_monthly').replace('clinic', 'clinic_referrals')} file to see this." if kpi.source != "admissions" else "The columns for this are missing from the admissions file.")
            return
        value, when = latest(res)
        st.markdown(f"### {fmt(value, kpi.unit)}")
        tgt = "No target" if res.target is None else f"Target {fmt(res.target, kpi.unit)}"
        extra = ""
        if key == "clinic_wait_median" and "clinic_waiting_list" in ctx.tbl.columns:
            wl = ctx.tbl["clinic_waiting_list"].dropna()
            if len(wl):
                extra = f", waiting list {int(wl.iloc[-1]):,}"
        st.caption(f"{when:%B %Y}. {tgt}, average {fmt(res.centre, kpi.unit)}{extra}")
        v = ctx.verdicts[key]
        st.markdown(mdc.icon_pair_html(v, size=28), unsafe_allow_html=True)


def los_card() -> None:
    with st.container(border=True):
        st.markdown(f"**{LOS_LABEL}**")
        if not ctx.los:
            st.markdown("### No data")
            return
        lines = []
        for res in ctx.los:
            value, _ = latest(res)
            v = mdc.verdict(res)
            flag = {"improve": ", improving", "concern": ", getting worse", "neutral": ", changed"}.get(
                v.variation.split("_")[-1], "")
            lines.append(f"- {res.label}: **{fmt(value, 'days')}**{flag}")
        st.markdown("\n".join(lines))
        st.caption("Median for patients discharged last month. The charts are on the Control charts page.")


@st.cache_data(show_spinner=False)
def _equity_summary(flags: pd.DataFrame) -> tuple[int, int, int]:
    res = equity.analyse(flags)
    if res.empty:
        return 0, 0, 0
    groups = res[res["dimension"] != "Overall"]
    return (int((groups["status"] == "worse").sum()), int((groups["status"] == "better").sum()),
            int((groups["status"] != "suppressed").sum()))


def equity_card() -> None:
    with st.container(border=True):
        st.markdown(f"**{EQUITY_LABEL}**")
        worse, better, tested = _equity_summary(ctx.flags)
        st.markdown(f"### {worse} difference{'s' if worse != 1 else ''} found")
        st.caption(f"Groups doing worse than everyone else, out of {tested} comparisons "
                   f"({better} doing better). Details on the Equity page.")


for pillar in PILLARS:
    keys = PILLAR_LAYOUT[pillar]
    st.subheader(pillar)
    cols = st.columns(3)
    for i, key in enumerate(keys):
        with cols[i % 3]:
            if key == "los_top5":
                los_card()
            elif key == "equity":
                equity_card()
            else:
                kpi_card(key)
