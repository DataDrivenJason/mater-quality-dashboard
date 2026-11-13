"""Shared by all three pages: load once, sidebar period filter, verdicts."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from . import data, mdc, spc
from .kpis import KPIS, SITE_NAME


@dataclass
class Context:
    flags: pd.DataFrame          # one row per admission, filtered to the period
    tbl: pd.DataFrame            # one row per month, filtered to the period
    results: dict                # key -> ChartResult | None
    verdicts: dict               # key -> MDCVerdict
    los: list                    # ChartResults, one per top diagnosis
    problems: list[str]
    is_demo: bool
    extract_date: pd.Timestamp


@st.cache_data(show_spinner="Loading data…")
def _prepare():
    tables, is_demo = data.load_tables()
    problems: list[str] = []
    if tables["admissions"] is None:
        raise ValueError("there's no admissions file in the data folder.")
    adm = data.clean_admissions(tables["admissions"], problems)
    svc = data.clean_service(tables["service_monthly"], problems)
    clinic = data.clean_clinic(tables["clinic_referrals"], problems)
    for name in ("service_monthly", "clinic_referrals"):
        if tables[name] is None:
            problems.append(f"There's no {name} file, so the KPIs that use it are blank.")
    # The extract date is the day after the last arrival. Outcomes after it
    # are unknown, which is what the 90-day censoring relies on.
    extract_date = adm["arrival_datetime"].max().normalize() + pd.Timedelta(days=1)
    flags = data.patient_flags(adm, extract_date)
    tbl = data.monthly_table(flags, svc, clinic)
    return flags, tbl, problems, is_demo, extract_date


def setup() -> Context:
    try:
        flags, tbl_all, problems, is_demo, extract_date = _prepare()
    except Exception as exc:  # show the reason on the page, not a stack trace
        st.error(f"The data didn't load: {exc}")
        st.stop()

    months = list(tbl_all["period"])
    with st.sidebar:
        st.markdown(f"### {SITE_NAME}")
        default_start = months[max(0, len(months) - 24)]
        start, end = st.select_slider(
            "Months shown", options=months, value=(default_start, months[-1]),
            format_func=lambda d: d.strftime("%b %Y"), key="period")
        if is_demo:
            st.info("This is made-up demo data. Put your own files in the data folder "
                    "and it will switch over (the README explains how).")
        with st.expander(f"Data check ({len(problems)})" if problems else "Data check"):
            st.write(f"{len(flags):,} admissions. Data runs up to {extract_date - pd.Timedelta(days=1):%d %B %Y}.")
            for p in problems:
                st.warning(p)
            if not problems:
                st.write("Everything loaded fine.")

    keep = (tbl_all["period"] >= start) & (tbl_all["period"] <= end)
    tbl = tbl_all[keep].reset_index(drop=True)
    arr_month = flags["arrival_datetime"].dt.to_period("M").dt.to_timestamp()
    flags_f = flags[(arr_month >= start) & (arr_month <= end)]

    results, verdicts = {}, {}
    for k in KPIS:
        try:
            res = data.chart_for(k, tbl)
        except Exception as exc:
            problems.append(f"{k.label} could not be calculated: {exc}")
            res = None
        results[k.key] = res
        if res is not None:
            verdicts[k.key] = mdc.verdict(res)
    los = data.los_panel(flags, tbl["period"]) if len(flags) else []
    return Context(flags_f, tbl, results, verdicts, los, problems, is_demo, extract_date)


def bucket(v: mdc.MDCVerdict) -> str:
    """One group per KPI for the summary tiles, most urgent first."""
    if v.variation.endswith("concern"):
        return "deteriorating"
    if v.variation.endswith("improve"):
        return "improving"
    if v.assurance == "fail":
        return "failing"
    if v.assurance == "hit_miss":
        return "hit_miss"
    return "other"


def latest(res: spc.ChartResult):
    last = res.last_valid()
    return (None, None) if last is None else (float(last["value"]), pd.Timestamp(last["x"]))
