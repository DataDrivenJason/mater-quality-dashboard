"""
From input files to monthly control charts.
=====================================================================

    load_tables()      read data/*.csv (or .xlsx / .parquet); demo data if absent
    clean_*()          parse dates and Yes/No, report anything unreadable
    patient_flags()    who counts for each patient-level KPI (incl. censoring)
    monthly_table()    one row per month, every KPI column
    chart_for()        the control chart for one KPI
    los_panel()        one length-of-stay chart per top-5 diagnosis

Nothing here draws anything, so all of it can be tested without Streamlit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import spc
from .kpis import KPI

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DEMO_DIR = DATA_DIR / "demo"

TABLES = ["admissions", "service_monthly", "clinic_referrals"]
STROKE_DIAGNOSES = {"Ischaemic stroke", "Intracerebral haemorrhage"}
MATURITY_THRESHOLD = 0.95   # share of a month's patients past 90 days before it is shown
MIN_DENOMINATOR = 5         # p-chart months with fewer patients are not plotted

_YES_NO = {"true": True, "t": True, "yes": True, "y": True, "1": True, "1.0": True,
           "false": False, "f": False, "no": False, "n": False, "0": False, "0.0": False}
_ADM_DATES = ["arrival_datetime", "discharge_datetime"]
_ADM_YES_NO = ["died_inpatient", "readmitted_90d", "smoker_at_admission",
               "smoking_followup_90d", "quit_at_90d", "first_language_english", "homeless"]
_ADM_NUMBERS = ["los_days", "door_to_needle_min", "su_bed_days", "doses_missed", "pex_score",
                "age", "deprivation_quintile"]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _read_csv(path: Path) -> pd.DataFrame:
    # CSVs saved from Excel on Windows are often cp1252, not UTF-8.
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""],
                               encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name} is not a readable text file.")


def _read_one(folder: Path, name: str) -> pd.DataFrame | None:
    for ext, reader in ((".csv", _read_csv),
                        (".xlsx", lambda p: pd.read_excel(p, dtype=str)),
                        (".parquet", pd.read_parquet)):
        path = folder / f"{name}{ext}"
        if path.exists():
            return reader(path)
    return None


def load_tables() -> tuple[dict[str, pd.DataFrame | None], bool]:
    """Real files in data/ if there are any, otherwise the demo files."""
    real = {t: _read_one(DATA_DIR, t) for t in TABLES}
    if any(v is not None for v in real.values()):
        return real, False
    if not (DEMO_DIR / "admissions.csv").exists():
        from .demo import write_demo
        write_demo(DEMO_DIR)
    return {t: _read_one(DEMO_DIR, t) for t in TABLES}, True


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def _to_datetime(s: pd.Series) -> pd.Series:
    """ISO dates (2026-01-05) as written; anything else day-first (05/01/2026),
    because 05/01 is 5 January in Ireland and 1 May to a US parser."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.tz_localize(None) if s.dt.tz is not None else s
    text = s.astype("string").str.strip()
    iso = text.str.match(r"^\d{4}-").fillna(False).astype(bool)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    kw = {"format": "mixed"} if int(pd.__version__.split(".")[0]) >= 2 else {}
    if iso.any():
        out[iso] = pd.to_datetime(text[iso], errors="coerce", **kw)
    if (~iso).any():
        out[~iso] = pd.to_datetime(text[~iso], errors="coerce", dayfirst=True, **kw)
    return out


def _to_bool(s: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(s):
        return s.astype(object)
    return s.astype("string").str.strip().str.lower().map(_YES_NO).astype(object)


def _blank(s: pd.Series) -> pd.Series:
    return s.isna() | s.astype("string").str.strip().isin(["", "nan", "None", "NaT", "<NA>"]).fillna(True)


def _convert(df: pd.DataFrame, dates, yes_no, numbers, table: str, problems: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col, fn in ([(c, _to_datetime) for c in dates] + [(c, _to_bool) for c in yes_no]
                    + [(c, lambda x: pd.to_numeric(x, errors="coerce")) for c in numbers]):
        if col not in df.columns:
            continue
        raw = df[col]
        df[col] = fn(raw)
        lost = int((pd.isna(df[col]) & ~_blank(raw)).sum())
        if lost:
            problems.append(f"{lost:,} values in the {col} column of {table} couldn't be read, so they were left blank.")
    return df


def clean_admissions(adm: pd.DataFrame, problems: list[str]) -> pd.DataFrame:
    if "arrival_datetime" not in adm.columns:
        raise ValueError("the admissions file needs an arrival_datetime column.")
    d = _convert(adm, _ADM_DATES, _ADM_YES_NO, _ADM_NUMBERS, "admissions", problems)
    d = d[d["arrival_datetime"].notna()].reset_index(drop=True)
    if "diagnosis" not in d.columns:
        d["diagnosis"] = "Ischaemic stroke"
        problems.append("The admissions file has no diagnosis column, so every row is treated "
                        "as a stroke.")
    if "los_days" not in d.columns and "discharge_datetime" in d.columns:
        d["los_days"] = (d["discharge_datetime"] - d["arrival_datetime"]).dt.total_seconds() / 86400
    return d


def clean_service(svc: pd.DataFrame | None, problems: list[str]) -> pd.DataFrame | None:
    if svc is None:
        return None
    d = svc.copy()
    d["month"] = _to_datetime(d["month"].astype("string").str.slice(0, 7) + "-01")
    numbers = [c for c in d.columns if c != "month"]
    d = _convert(d, [], [], numbers, "service_monthly", problems)
    return d[d["month"].notna()].rename(columns={"month": "period"})


def clean_clinic(clinic: pd.DataFrame | None, problems: list[str]) -> pd.DataFrame | None:
    if clinic is None:
        return None
    return _convert(clinic, ["referral_date", "appointment_date"], [], [], "clinic_referrals",
                    problems)


# ---------------------------------------------------------------------------
# Patient-level flags
# ---------------------------------------------------------------------------
def _yes(d: pd.DataFrame, col: str) -> pd.Series:
    if col not in d.columns:
        return pd.Series(False, index=d.index)
    return d[col].fillna(False).astype(bool)


def patient_flags(adm: pd.DataFrame, extract_date: pd.Timestamp) -> pd.DataFrame:
    """Numerators and denominators for each stroke patient.

    90-day outcomes are right-censored: anyone discharged in the last 90
    days of the extract has an *unknown* outcome, although the raw column
    says "No". They are kept out of the denominator until discharge + 90
    days has passed, or every recent month would look better than it is.
    """
    d = adm.copy()
    d["is_stroke"] = d["diagnosis"].isin(STROKE_DIAGNOSES)
    stroke = d["is_stroke"]
    survived = ~_yes(d, "died_inpatient")
    if "discharge_datetime" in d.columns:
        discharge = d["discharge_datetime"]
    else:
        discharge = d["arrival_datetime"] + pd.to_timedelta(d["los_days"], unit="D")
    discharged_alive = stroke & survived & discharge.notna()
    window_closed = (discharge + pd.Timedelta(days=90)) <= extract_date

    d["den_survivors"] = discharged_alive
    d["den_readmit_90d_mature"] = discharged_alive & window_closed
    d["flag_readmit_90d"] = d["den_readmit_90d_mature"] & _yes(d, "readmitted_90d")

    smoker = stroke & _yes(d, "smoker_at_admission")
    d["den_smoker_survivors"] = smoker & discharged_alive
    d["den_smoker_mature"] = d["den_smoker_survivors"] & window_closed
    d["den_smoker_followed_up"] = d["den_smoker_mature"] & _yes(d, "smoking_followup_90d")
    d["flag_quit_90d"] = d["den_smoker_followed_up"] & _yes(d, "quit_at_90d")

    los = pd.to_numeric(d["los_days"], errors="coerce").clip(lower=1)
    if "su_bed_days" in d.columns:
        su = np.minimum(pd.to_numeric(d["su_bed_days"], errors="coerce").clip(lower=0), los)
        d["su_days_calc"] = su.where(stroke)
        d["los_su_known"] = los.where(stroke & d["su_days_calc"].notna())
        d["su_time_share_pt"] = 100 * d["su_days_calc"] / d["los_su_known"]

    if "discharge_datetime" in d.columns:
        hour = discharge.dt.hour + discharge.dt.minute / 60.0
        d["discharge_hour"] = hour.where(discharged_alive)

    for col in ("door_to_needle_min", "doses_missed", "pex_score"):
        if col in d.columns:
            d[col] = d[col].where(stroke)
    return d


# ---------------------------------------------------------------------------
# One row per month
# ---------------------------------------------------------------------------
_SUM = ["den_survivors", "den_readmit_90d_mature", "flag_readmit_90d", "den_smoker_survivors",
        "den_smoker_mature", "den_smoker_followed_up", "flag_quit_90d", "su_days_calc",
        "los_su_known"]
_MEDIAN = ["door_to_needle_min", "doses_missed", "pex_score", "discharge_hour"]


def monthly_table(flags: pd.DataFrame, service: pd.DataFrame | None,
                  clinic: pd.DataFrame | None) -> pd.DataFrame:
    month = flags["arrival_datetime"].dt.to_period("M").dt.to_timestamp()
    starts = [month.min()]
    if service is not None and len(service):
        starts.append(service["period"].min())
    ends = [month.max()] + ([service["period"].max()] if service is not None and len(service) else [])
    months = pd.date_range(min(starts), max(ends), freq="MS")
    tbl = pd.DataFrame({"period": months}).set_index("period")

    for c in _SUM:
        if c in flags.columns:
            tbl[c] = flags[c].astype(float).groupby(month).sum().reindex(months)
    for c in _MEDIAN:
        if c in flags.columns:
            tbl[c] = pd.to_numeric(flags[c], errors="coerce").groupby(month).median().reindex(months)
    tbl["admissions"] = flags.groupby(month).size().reindex(months)

    # A month's 90-day rate is shown only when almost all of its patients
    # have completed follow-up. In a partly mature month the ones counted
    # are those discharged earliest, so shorter stays and milder strokes.
    for mature, cohort, dependants in (
            ("den_readmit_90d_mature", "den_survivors", ["flag_readmit_90d"]),
            ("den_smoker_mature", "den_smoker_survivors", ["den_smoker_followed_up", "flag_quit_90d"])):
        if mature in tbl.columns:
            share = tbl[mature] / tbl[cohort].replace(0, np.nan)
            immature = ~(share >= MATURITY_THRESHOLD)
            for c in [mature] + dependants:
                tbl[c] = tbl[c].where(~immature)

    if "su_days_calc" in tbl.columns:
        tbl["su_time_share"] = 100 * tbl["su_days_calc"] / tbl["los_su_known"].replace(0, np.nan)

    if service is not None and len(service):
        tbl = tbl.join(service.groupby("period").last(), how="left")

    if clinic is not None and len(clinic):
        c = clinic.copy()
        c["wait"] = (c["appointment_date"] - c["referral_date"]).dt.days
        seen = c[c["appointment_date"].notna()]
        appt_month = seen["appointment_date"].dt.to_period("M").dt.to_timestamp()
        tbl["clinic_wait_days"] = seen["wait"].groupby(appt_month).median().reindex(months)
        ends_ = months + pd.offsets.MonthEnd(0)
        tbl["clinic_waiting_list"] = [
            int(((c["referral_date"] <= e) & (c["appointment_date"].isna()
                                                | (c["appointment_date"] > e))).sum())
            for e in ends_]
    return tbl.reset_index()


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def c_rule_set(counts: pd.Series) -> tuple[str, str]:
    """Run rules assume a point is equally likely either side of the centre
    line. For a Poisson count with a small mean that is false (mean 1.1:
    a 0 or 1, both below the line, happens 70% of the time), so only
    the single-point rule is used when P(count < mean) is far from ½."""
    c = pd.to_numeric(counts, errors="coerce").dropna()
    if c.empty:
        return "nhs", ""
    cbar = float(c.mean())
    if cbar <= 0:
        return "core", "Every month is zero, so only a single unusual month would count as a change."
    p_below = float(stats.poisson.cdf(np.ceil(cbar) - 1, cbar))
    if abs(p_below - 0.5) > 0.15:
        return "core", (f"With only about {cbar:.1f} a month, most months fall below the "
                        "average by chance, so runs of low months aren't treated as a change. "
                        "Only a single unusually high or low month is.")
    return "nhs", ""


def chart_for(kpi: KPI, tbl: pd.DataFrame) -> spc.ChartResult | None:
    x = tbl["period"]
    if kpi.chart == "p":
        if kpi.numerator not in tbl.columns or kpi.denominator not in tbl.columns:
            return None
        den = tbl[kpi.denominator].astype(float)
        keep = den >= MIN_DENOMINATOR
        num = tbl[kpi.numerator].astype(float).where(keep)
        den = den.where(keep)
        if not keep.any():
            return None
        res = spc.p_chart(num, den, x, target=kpi.target, higher_is_better=kpi.higher_is_better,
                          unit="%", label=kpi.label)
        res.meta["denominator"] = den.to_numpy()
        return res
    col = kpi.value_col
    if col not in tbl.columns or tbl[col].notna().sum() == 0:
        return None
    values = tbl[col].astype(float)
    target = kpi.target
    if kpi.target_col and kpi.target_col in tbl.columns:
        budget = tbl[kpi.target_col].dropna()
        target = float(budget.iloc[-1]) if len(budget) else None
    if kpi.chart == "c":
        rules, note = c_rule_set(values)
        res = spc.c_chart(values, x, target=target, higher_is_better=kpi.higher_is_better,
                          rule_set=rules, unit=kpi.unit, label=kpi.label)
        res.meta["rule_note"] = note
        return res
    upper = 100.0 if kpi.unit == "%" else (24.0 if kpi.unit == "time of day" else None)
    lower = 0.0 if kpi.unit != "time of day" else None
    return spc.xmr(values, x, target=target, higher_is_better=kpi.higher_is_better,
                   lower_bound=lower, upper_bound=upper, unit=kpi.unit, label=kpi.label)


def top_diagnoses(adm: pd.DataFrame, n: int = 5) -> list[str]:
    return adm["diagnosis"].dropna().value_counts().head(n).index.tolist()


def los_panel(adm: pd.DataFrame, months: pd.Series, n: int = 5) -> list[spc.ChartResult]:
    """One XmR chart of monthly median length of stay per top diagnosis.

    One chart per diagnosis rather than one pooled median: a month with more
    TIAs (two-day stays) pulls a pooled median down with nothing in the
    service having changed. Stratifying is the simplest case-mix control.

    Months are months of *discharge*, not arrival. By arrival month, the
    latest months would only contain patients already discharged (the
    short stays) and length of stay would always seem to be falling."""
    out = []
    a = adm[adm["los_days"].notna()]
    if "discharge_datetime" in a.columns:
        discharged = a["discharge_datetime"]
    else:
        discharged = a["arrival_datetime"] + pd.to_timedelta(a["los_days"], unit="D")
    a = a[discharged.notna()]
    month = discharged[a.index].dt.to_period("M").dt.to_timestamp()
    for dx in top_diagnoses(adm, n):
        sel = a["diagnosis"] == dx
        med = a.loc[sel, "los_days"].groupby(month[sel]).median().reindex(months)
        res = spc.xmr(med.to_numpy(dtype=float), list(months), higher_is_better=False,
                      lower_bound=0.0, unit="days", label=dx)
        out.append(res)
    return out
