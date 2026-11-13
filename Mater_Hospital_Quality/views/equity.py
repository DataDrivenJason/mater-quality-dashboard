"""Equity: do the patient-level KPIs differ by who the patient is?"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import equity
from core.charts import equity_plot, fmt
from core.kpis import KPI_BY_KEY, SITE_NAME
from core.state import setup

ctx = setup()

st.title(f"{SITE_NAME} equity")
st.caption("Each group is compared with everyone else, not with the overall figure, since the "
           "overall figure already includes the group. The ranges shown are 95% confidence "
           "intervals. We use Fisher's exact test for percentages and Mann-Whitney for medians, "
           "then a Benjamini-Hochberg correction so that only about 1 in 20 flags is a false "
           "alarm. Groups with fewer than 10 patients are hidden, along with one other group "
           "where needed so the hidden figure can't be worked out.")

dims_all = list(equity.dimensions(ctx.flags))
if not dims_all:
    st.info("The admissions file doesn't have any of the group columns (age, sex, "
            "deprivation_quintile, first_language_english, homeless).")
    st.stop()


@st.cache_data(show_spinner="Comparing subgroups…")
def _analyse(flags: pd.DataFrame) -> pd.DataFrame:
    return equity.analyse(flags)


result = _analyse(ctx.flags)
if result.empty:
    st.info("There isn't enough data to compare groups yet.")
    st.stop()

dims = st.multiselect("Groups", dims_all, default=dims_all, key="eq_dims")
view = result[(result["dimension"] == "Overall") | result["dimension"].isin(dims)]

# ---- what was flagged -------------------------------------------------------
flag = view[view["status"].isin(["worse", "better"])].copy()
st.subheader("Differences found")
if flag.empty:
    st.success("No group stands out from everyone else on any KPI in these months.")
else:
    flag["Gap"] = flag.apply(equity.describe_gap, axis=1)
    flag["Group value"] = [fmt(v, u) for v, u in zip(flag["value"], flag["unit"])]
    flag["Everyone else"] = [fmt(v, u) for v, u in zip(flag["rest_value"], flag["unit"])]
    table = flag.rename(columns={"indicator": "KPI", "dimension": "Category", "group": "Group",
                                 "status": "Direction", "n": "Patients", "q": "q-value"})
    table = table.sort_values(["Direction", "q-value"], ascending=[False, True])
    st.dataframe(table[["KPI", "Category", "Group", "Direction", "Group value", "Everyone else",
                        "Gap", "Patients", "q-value"]],
                 hide_index=True, column_config={"q-value": st.column_config.NumberColumn(format="%.3f")})
st.caption("These figures aren't adjusted for case mix. For example, people from more deprived "
           "areas tend to have strokes younger, and older patients tend to have more severe "
           "strokes. So a difference here is a reason to look closer, not proof of unequal care.")

# ---- one plot per KPI ---------------------------------------------------------
st.subheader("All comparisons")
for key in view["key"].unique():
    rows = view[view["key"] == key]
    overall = rows[rows["dimension"] == "Overall"]
    groups = rows[rows["dimension"] != "Overall"]
    if overall.empty or groups.empty:
        continue
    kpi = KPI_BY_KEY[key]
    ov = float(overall["value"].iloc[0])
    with st.expander(f"{kpi.label}: {fmt(ov, kpi.unit)} overall", expanded=False):
        st.plotly_chart(equity_plot(groups, ov, kpi.unit), key=f"eq_{key}")
        st.caption(f"The vertical line is all patients: {fmt(ov, kpi.unit)} from "
                   f"{int(overall['n'].iloc[0]):,} patients. "
                   f"{'Higher' if kpi.higher_is_better else 'Lower'} is better.")
