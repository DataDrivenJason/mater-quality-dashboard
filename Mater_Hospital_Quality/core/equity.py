"""
Equity analysis: does quality vary by who the patient is?
=====================================================================

The question is simple to ask and easy to answer badly. Four decisions
here are what separate an equity analysis from a coloured table of
subgroup percentages.

1. Compare each group with everyone else, not with the overall figure
--------------------------------------------------------------------
The overall rate *contains* the group. A group that is 40% of the cohort
pulls the overall towards itself, so "group vs overall" understates every
difference, and understates it more the bigger the group. The comparator
here is the complement: patients in the same indicator cohort who are
*not* in the group. That is also what the significance test compares.

2. Use intervals that are honest at small n
-------------------------------------------
* Proportions: the Wilson score interval. The textbook p ± 1.96·SE
  interval collapses to zero width at 0% or 100% and undercovers badly
  below about n = 40 -- exactly the sizes subgroups come in.
* Medians: the distribution-free order-statistic interval. If the true
  median is m, each observation falls below m with probability one half,
  so the number below m is Binomial(n, ½). Choosing ranks from that
  binomial gives an interval with at least 95% coverage for *any*
  continuous distribution -- no normality, no bootstrap.
* Means (used only for the per-patient stroke-unit share): Student t.

3. Correct for the number of comparisons
----------------------------------------
Ten indicators by thirteen subgroups is 130 tests. At p < 0.05 about six
or seven would be "significant" with no real difference anywhere. The
Benjamini-Hochberg procedure controls the *false discovery rate* -- the
expected share of flagged cells that are false -- rather than the chance
of any single false flag (Bonferroni), which would be so strict that a
genuine gap in a group of 40 could never be detected. A cell is flagged
only when its BH-adjusted q-value is below the chosen rate.

4. Suppress small cells, and the cells that would reveal them
-------------------------------------------------------------
A group with fewer than ``min_n`` patients is not reported (primary
suppression). That is not enough on its own: when the overall figure is
published and only one group in a dimension is hidden, its value can be
recovered by subtraction from the others. So a second group is hidden too
(secondary suppression) -- the same rule national statistics offices use.

What this does NOT do
---------------------
It does not adjust for case mix. Deprived patients are younger at stroke;
older patients have more severe strokes; patients who do not speak English
may arrive by different routes. A crude gap is a reason to look, not a
finding of unequal care. The honest next step for any flagged gap is a
stratified or regression-adjusted comparison, which is a modelling
commitment and deliberately not automated here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .kpis import EQUITY_KPIS, METRICS, metric

# Indicators analysed by default -- patient-level, and the ones where an
# unequal pathway would show up.
DEFAULT_INDICATORS = list(EQUITY_KPIS)

DIMENSION_ORDER = ["Age band", "Sex", "Deprivation", "First language", "Housing"]

GROUP_ORDER = {
    "Age band": ["Under 65", "65 to 79", "80 and over"],
    "Sex": ["Female", "Male"],
    "Deprivation": ["Q1 least deprived", "Q2", "Q3", "Q4", "Q5 most deprived"],
    "First language": ["English", "Not English"],
    "Housing": ["Housed", "Experiencing homelessness"],
}

# Indicators measured at a follow-up point. Patients whose arrival month is
# not yet mature are excluded, by the same rule as the control charts.
_MATURITY = {"readmission_90d": "den_survivors", "quit_smoking_90d": "den_smoker_survivors"}
_MATURE_DEN = {"readmission_90d": "den_readmit_90d_mature",
               "quit_smoking_90d": "den_smoker_mature"}


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------
def dimensions(adm: pd.DataFrame) -> dict[str, pd.Series]:
    """Label each patient in each available dimension. Missing source
    columns simply mean the dimension is not offered."""
    out: dict[str, pd.Series] = {}
    if "age" in adm.columns:
        out["Age band"] = pd.cut(pd.to_numeric(adm["age"], errors="coerce"),
                                 [-np.inf, 65, 80, np.inf], right=False,
                                 labels=GROUP_ORDER["Age band"]).astype(object)
    if "sex" in adm.columns:
        out["Sex"] = adm["sex"].where(adm["sex"].isin(GROUP_ORDER["Sex"]))
    if "deprivation_quintile" in adm.columns:
        q = pd.to_numeric(adm["deprivation_quintile"], errors="coerce")
        out["Deprivation"] = q.map(dict(zip([1, 2, 3, 4, 5], GROUP_ORDER["Deprivation"])))
    if "first_language_english" in adm.columns:
        out["First language"] = adm["first_language_english"].map(
            {True: "English", False: "Not English"})
    if "homeless" in adm.columns:
        out["Housing"] = adm["homeless"].map(
            {False: "Housed", True: "Experiencing homelessness"})
    return {k: out[k] for k in DIMENSION_ORDER if k in out}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def wilson(k: float, n: float, conf: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a proportion, returned as percentages."""
    if n <= 0:
        return (np.nan, np.nan)
    z = stats.norm.ppf(1 - (1 - conf) / 2)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def median_ci(x: np.ndarray, conf: float = 0.95) -> tuple[float, float]:
    """Distribution-free interval for a median from order statistics.

    The count of observations below the true median is Binomial(n, 1/2).
    Take l as the largest rank with P(B <= l - 1) < alpha/2; the interval
    (x_(l), x_(n-l+1)) then covers the median with probability >= conf.
    """
    x = np.sort(np.asarray(x, dtype=float)[np.isfinite(x)])
    n = len(x)
    if n < 6:
        return (np.nan, np.nan)
    a = (1 - conf) / 2
    l = int(stats.binom.ppf(a, n, 0.5))
    l = max(l, 1)
    return (float(x[l - 1]), float(x[n - l]))


def mean_ci(x: np.ndarray, conf: float = 0.95) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return (np.nan, np.nan)
    m, se = float(np.mean(x)), float(np.std(x, ddof=1) / np.sqrt(n))
    t = stats.t.ppf(1 - (1 - conf) / 2, n - 1)
    return (m - t * se, m + t * se)


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """BH-adjusted q-values. NaNs are left as NaN and do not count as tests."""
    p = np.asarray(p, dtype=float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return q
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    # step-up: enforce monotonicity from the largest p downwards
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(ranked, 1.0)
    q[ok] = out
    return q


# ---------------------------------------------------------------------------
# Indicator cohorts
# ---------------------------------------------------------------------------
@dataclass
class Cohort:
    key: str
    method: str            # "prop" | "median" | "mean"
    mask: pd.Series        # who is in the indicator's cohort
    values: pd.Series      # 0/1 for proportions, the measurement otherwise


def method_for(key: str) -> str | None:
    spec = METRICS.get(key)
    if spec is None or spec.source != "admissions":
        return None
    if key == "su_time_share":
        return "mean"
    if spec.chart == "p":
        return "prop"
    if spec.chart == "xmr" and spec.value_col:
        return "median"
    return None


def cohort(adm: pd.DataFrame, key: str) -> Cohort | None:
    method = method_for(key)
    if method is None:
        return None
    spec = METRICS[key]
    if method == "prop":
        if spec.numerator not in adm.columns or spec.denominator not in adm.columns:
            return None
        mask = adm[spec.denominator].fillna(False).astype(bool)
        if key in _MATURITY and _MATURITY[key] in adm.columns:
            mask &= _mature_months(adm, key)
        values = adm[spec.numerator].fillna(False).astype(float)
        return Cohort(key, method, mask, values)
    col = "su_time_share_pt" if key == "su_time_share" else spec.value_col
    if col not in adm.columns:
        return None
    values = pd.to_numeric(adm[col], errors="coerce")
    return Cohort(key, method, values.notna(), values)


def _mature_months(adm: pd.DataFrame, key: str, threshold: float = 0.95) -> pd.Series:
    """True for patients whose arrival month has completed follow-up."""
    month = adm["arrival_datetime"].dt.to_period("M")
    base = adm[_MATURITY[key]].fillna(False).astype(bool)
    mature = adm[_MATURE_DEN[key]].fillna(False).astype(bool)
    share = mature.groupby(month).sum() / base.groupby(month).sum().replace(0, np.nan)
    ok_months = set(share[share >= threshold].index)
    return month.isin(ok_months)


def _summarise(c: Cohort, sel: pd.Series) -> dict:
    v = c.values[sel & c.mask]
    n = int(len(v))
    if c.method == "prop":
        k = float(v.sum())
        lo, hi = wilson(k, n)
        return {"n": n, "events": k, "value": 100 * k / n if n else np.nan,
                "lo": lo, "hi": hi, "_x": v.to_numpy()}
    arr = v.to_numpy(dtype=float)
    if c.method == "median":
        lo, hi = median_ci(arr)
        val = float(np.median(arr)) if n else np.nan
    else:
        lo, hi = mean_ci(arr)
        val = float(np.mean(arr)) if n else np.nan
    return {"n": n, "events": np.nan, "value": val, "lo": lo, "hi": hi, "_x": arr}


def _test(method: str, a: dict, b: dict) -> tuple[float, float]:
    """Two-sided p-value and the direction of the difference.

    Direction is returned as a signed effect: the difference in value for
    proportions and means, and for medians the probability of superiority
    minus one half -- P(a random patient in the group has a higher value
    than a random patient outside it) - 0.5, read straight off the
    Mann-Whitney U statistic as U / (n1 n2).

    That matters for medians of small counts (missed doses, a 0-10 score).
    Mann-Whitney compares whole distributions, so it can detect a real
    shift while both medians sit on the same integer. Taking the direction
    from the medians would then label a significant difference with a
    difference of zero; taking it from the test keeps the two consistent.
    """
    if a["n"] < 2 or b["n"] < 2:
        return np.nan, np.nan
    if method == "prop":
        table = [[a["events"], a["n"] - a["events"]], [b["events"], b["n"] - b["events"]]]
        return float(stats.fisher_exact(table)[1]), a["value"] - b["value"]
    if method == "median":
        r = stats.mannwhitneyu(a["_x"], b["_x"], alternative="two-sided")
        return float(r.pvalue), float(r.statistic) / (a["n"] * b["n"]) - 0.5
    r = stats.ttest_ind(a["_x"], b["_x"], equal_var=False)
    return float(r.pvalue), a["value"] - b["value"]


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------
def analyse(adm: pd.DataFrame, keys: list[str] | None = None,
            dims: list[str] | None = None, *, min_n: int = 10,
            fdr: float = 0.05, standard: str = "SSNAP") -> pd.DataFrame:
    """Every indicator x subgroup comparison, tidy, with suppression applied.

    Suppressed rows keep their identifiers but carry no value, interval, n
    or comparator -- so the table can be downloaded as it stands without
    leaking anything that was hidden on screen.
    """
    keys = keys or DEFAULT_INDICATORS
    all_dims = dimensions(adm)
    dims = [d for d in (dims or list(all_dims)) if d in all_dims]
    rows = []
    for key in keys:
        c = cohort(adm, key)
        if c is None or not c.mask.any():
            continue
        spec, _thr = metric(key, standard)
        everyone = pd.Series(True, index=adm.index)
        overall = _summarise(c, everyone)
        rows.append({"key": key, "indicator": spec.label, "unit": spec.unit,
                     "higher_is_better": spec.higher_is_better, "method": c.method,
                     "dimension": "Overall", "group": "All patients",
                     **{k: v for k, v in overall.items() if k != "_x"},
                     "rest_n": np.nan, "rest_value": np.nan, "diff": np.nan,
                     "effect": np.nan, "p": np.nan})
        for dim in dims:
            labels = all_dims[dim]
            known = labels.notna()
            for g in [x for x in GROUP_ORDER[dim] if (labels == x).any()]:
                in_g = labels == g
                a = _summarise(c, in_g)
                b = _summarise(c, known & ~in_g)
                p, effect = _test(c.method, a, b)
                rows.append({"key": key, "indicator": spec.label, "unit": spec.unit,
                             "higher_is_better": spec.higher_is_better, "method": c.method,
                             "dimension": dim, "group": g,
                             **{k: v for k, v in a.items() if k != "_x"},
                             "rest_n": b["n"], "rest_value": b["value"],
                             "diff": a["value"] - b["value"],
                             "effect": effect, "p": p})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return _finalise(out, min_n=min_n, fdr=fdr)


def _finalise(out: pd.DataFrame, *, min_n: int, fdr: float) -> pd.DataFrame:
    out = out.copy()
    groups = out["dimension"] != "Overall"
    out["suppressed"] = False
    out["reason"] = ""

    primary = groups & (out["n"] < min_n)
    out.loc[primary, ["suppressed", "reason"]] = [True, f"fewer than {min_n} patients"]

    # Secondary suppression: one hidden group per dimension can be recovered
    # from the overall figure and the others, so hide the next smallest too.
    for (_k, _d), idx in out[groups].groupby(["key", "dimension"]).groups.items():
        block = out.loc[idx]
        if block["suppressed"].sum() == 1 and len(block) > 1:
            j = block[~block["suppressed"]]["n"].idxmin()
            out.loc[j, ["suppressed", "reason"]] = [
                True, "hidden so a suppressed group cannot be recovered by subtraction"]

    # The comparator for any group in a two-group dimension *is* the other
    # group, so it goes when that group goes.
    hidden = out["suppressed"]
    out.loc[hidden, ["n", "events", "value", "lo", "hi", "rest_n", "rest_value",
                     "diff", "effect", "p"]] = np.nan

    out["q"] = np.nan
    testable = groups & ~hidden & out["p"].notna()
    out.loc[testable, "q"] = benjamini_hochberg(out.loc[testable, "p"].to_numpy())

    def status(r) -> str:
        if r["dimension"] == "Overall":
            return "reference"
        if r["suppressed"]:
            return "suppressed"
        if not np.isfinite(r["q"]) or r["q"] >= fdr:
            return "no clear difference"
        hib = r["higher_is_better"]
        if hib is None or (isinstance(hib, float) and np.isnan(hib)):
            return "different"
        worse = (r["effect"] < 0) if hib else (r["effect"] > 0)
        return "worse" if worse else "better"

    out["status"] = out.apply(status, axis=1)
    return out.reset_index(drop=True)


_UNIT_WORD = {"minutes": "min", "days": "days", "doses": "doses", "score /10": "points",
              "%": "pts"}


def describe_gap(row: pd.Series) -> str:
    """The gap in words, signed as group minus everyone else.

    For medians of small whole numbers the two medians are often equal
    even when the test finds a real shift; saying "0" there would
    contradict the flag, so the direction of the shift is given instead.
    """
    if not np.isfinite(row.get("diff", np.nan)):
        return ""
    unit = _UNIT_WORD.get(row["unit"], row["unit"])
    if row["method"] == "median" and row["diff"] == 0:
        eff = row.get("effect", np.nan)
        if not np.isfinite(eff):
            return "same median"
        side = "higher" if eff > 0 else "lower"
        return f"same median; values tend {side} (P = {0.5 + eff:.2f})"
    d = row["diff"]
    return f"{d:+.1f} {unit}" if abs(d) < 100 else f"{d:+,.0f} {unit}"


def flagged(result: pd.DataFrame, which: str = "worse") -> pd.DataFrame:
    """Flagged cells, largest relative gap first."""
    f = result[result["status"] == which].copy()
    if f.empty:
        return f
    f["_rel"] = (f["diff"].abs() / f["rest_value"].abs().replace(0, np.nan)).fillna(0)
    return f.sort_values("_rel", ascending=False).drop(columns="_rel")


# ---------------------------------------------------------------------------
# A gap over time
# ---------------------------------------------------------------------------
def gap_over_time(adm: pd.DataFrame, key: str, dim: str, group: str, *,
                  freq: str = "auto", min_n: int = 10) -> pd.DataFrame:
    """Subgroup vs everyone else, period by period.

    Quarterly where the group is big enough, yearly where it is not
    (``freq="auto"``): a series that is mostly suppressed is no series at
    all. Periods where either side has fewer than ``min_n`` patients are
    blanked rather than plotted from a handful of cases. The chosen
    frequency is returned in ``.attrs["freq"]``.
    """
    if freq == "auto":
        q = gap_over_time(adm, key, dim, group, freq="QS", min_n=min_n)
        if q.empty:
            return q
        ok = q.pivot_table(index="period", columns="series", values="value",
                           aggfunc="first").notna().all(axis=1)
        if ok.mean() >= 0.6:
            return q
        return gap_over_time(adm, key, dim, group, freq="YS", min_n=min_n)
    c = cohort(adm, key)
    dimlab = dimensions(adm).get(dim)
    if c is None or dimlab is None:
        return pd.DataFrame()
    pfreq = {"QS": "Q", "MS": "M", "YS": "Y"}.get(freq, "Q")
    period = adm["arrival_datetime"].dt.to_period(pfreq).dt.to_timestamp()
    rows = []
    for p in sorted(period[c.mask].unique()):
        in_p = period == p
        a = _summarise(c, in_p & (dimlab == group))
        b = _summarise(c, in_p & dimlab.notna() & (dimlab != group))
        rows.append({"period": p, "series": group,
                     "value": a["value"] if a["n"] >= min_n else np.nan, "n": a["n"]})
        rows.append({"period": p, "series": "Everyone else",
                     "value": b["value"] if b["n"] >= min_n else np.nan, "n": b["n"]})
    out = pd.DataFrame(rows)
    out.attrs["freq"] = freq
    return out
