"""
The Mater Hospital quality framework: the 17 KPIs, one place.
=====================================================================

Every KPI is described once here. The pages loop over this list, so a
label, target or direction changed here changes everywhere.

    pillar            which aim of care it serves
    source            which input table it comes from
    chart             p  = proportion (p-chart, Laney-corrected)
                      xmr = a monthly value (individuals chart)
                      c  = a monthly count (c-chart)
    higher_is_better  True / False / None (None = no good direction)
    target            local working default (these need agreeing locally)
"""

from __future__ import annotations

from dataclasses import dataclass

SITE_NAME = "Mater Hospital"

PILLARS = ["Safe", "Effective", "Person-centred", "Timely", "Efficient", "Equitable", "Culture"]


@dataclass(frozen=True)
class KPI:
    key: str
    label: str
    pillar: str
    source: str                       # "admissions" | "service" | "clinic"
    chart: str                        # "p" | "xmr" | "c"
    unit: str
    higher_is_better: bool | None
    target: float | None = None
    numerator: str | None = None      # p-charts
    denominator: str | None = None    # p-charts
    value_col: str | None = None      # xmr / c charts: the monthly column
    target_col: str | None = None     # a target that varies by month (budgets)
    definition: str = ""


KPIS: list[KPI] = [
    # ---- Safe ----------------------------------------------------------
    KPI("incidents_total", "Incident reports (total)", "Safe", "service", "c", "count", None,
        value_col="incidents_total",
        definition="Incident reports per month. No good direction: more reporting is usually "
                   "a sign of a healthy safety culture, not less safety."),
    KPI("incidents_severe", "Incident reports (moderate/severe)", "Safe", "service", "c",
        "count", False, value_col="incidents_mod_severe",
        definition="Incident reports graded moderate or severe, per month."),

    # ---- Effective -----------------------------------------------------
    KPI("readmission_90d", "Readmission within 90 days", "Effective", "admissions", "p", "%",
        False, 18.0, numerator="flag_readmit_90d", denominator="den_readmit_90d_mature",
        definition="Emergency readmission within 90 days of discharge, among stroke patients "
                   "discharged alive whose 90-day window has closed. By month of arrival; a "
                   "month is shown once 95% of its patients have completed follow-up."),
    KPI("su_time_share", "Time spent on a stroke unit", "Effective", "admissions", "xmr", "%",
        True, 90.0, value_col="su_time_share",
        definition="Stroke-unit bed days as a share of all bed days, per month of arrival "
                   "(a ratio of sums, so long stays carry proportionate weight)."),
    KPI("quit_smoking_90d", "Quit smoking at 90 days", "Effective", "admissions", "p", "%",
        True, 40.0, numerator="flag_quit_90d", denominator="den_smoker_followed_up",
        definition="Smokers at admission who report not smoking at 90 days, among those "
                   "alive, past 90 days and reached at follow-up. Complete-case: it "
                   "overstates the true rate, since people not reached are more likely "
                   "to still smoke."),
    KPI("missed_doses_median", "Missed doses of medication (median)", "Effective",
        "admissions", "xmr", "doses", False, 1.0, value_col="doses_missed",
        definition="Median doses missed per stroke admission, excluding clinically "
                   "appropriate omissions."),
    # Length of stay for the top 5 diagnoses is a panel (one chart per
    # diagnosis), built separately in core/data.py. See LOS_KEY.

    # ---- Person-centred ------------------------------------------------
    KPI("pex_median", "Patient experience score at discharge (median)", "Person-centred",
        "admissions", "xmr", "score /10", True, 8.0, value_col="pex_score",
        definition="Median 0-10 rating from the patient experience survey at discharge, "
                   "among surveys returned."),
    KPI("complaints_total", "Complaints (total)", "Person-centred", "service", "c", "count",
        False, value_col="complaints_total", definition="Complaints received per month."),
    KPI("complaints_severe", "Complaints (moderate/severe)", "Person-centred", "service", "c",
        "count", False, value_col="complaints_mod_severe",
        definition="Complaints graded moderate or severe, per month."),

    # ---- Timely --------------------------------------------------------
    KPI("dtn_median", "Door-to-needle time for thrombolysis (median)", "Timely",
        "admissions", "xmr", "minutes", False, 40.0, value_col="door_to_needle_min",
        definition="Median minutes from arrival to IV thrombolysis, thrombolysed patients only."),
    KPI("clinic_wait_median", "Wait for new-patient stroke clinic (median)", "Timely",
        "clinic", "xmr", "days", False, 28.0, value_col="clinic_wait_days",
        definition="Median days from referral to first appointment, by month of appointment. "
                   "Describes patients who were seen; the waiting list is shown alongside."),

    # ---- Efficient -----------------------------------------------------
    KPI("discharge_hour_median", "Time of discharge (median)", "Efficient", "admissions",
        "xmr", "time of day", False, 13.0, value_col="discharge_hour",
        definition="Median clock time of discharge, patients discharged alive."),
    KPI("external_test_cost", "External test cost", "Efficient", "service", "xmr", "€", False,
        value_col="external_test_cost_eur", target_col="external_test_budget_eur",
        definition="Monthly spend on external tests. Target line is the monthly budget."),
    KPI("nchd_overtime_cost", "NCHD overtime cost", "Efficient", "service", "xmr", "€", False,
        value_col="nchd_overtime_cost_eur", target_col="nchd_overtime_budget_eur",
        definition="Monthly NCHD overtime spend. Target line is the monthly budget."),

    # ---- Culture -------------------------------------------------------
    KPI("active_audits", "Active clinical audits", "Culture", "service", "xmr", "count", True,
        value_col="active_audits",
        definition="Clinical audits in progress at month end (a stock, not a flow)."),
]

LOS_KEY = "los_top5"
LOS_LABEL = "Length of stay, top 5 diagnoses (median)"
LOS_TARGET = None
EQUITY_LABEL = "Key quality indicators by subgroup"

KPI_BY_KEY = {k.key: k for k in KPIS}

# Every KPI in pillar order, with the two special ones slotted in.
PILLAR_LAYOUT: dict[str, list[str]] = {p: [k.key for k in KPIS if k.pillar == p] for p in PILLARS}
PILLAR_LAYOUT["Effective"].insert(1, LOS_KEY)
PILLAR_LAYOUT["Equitable"] = ["equity"]

# Patient-level KPIs analysed on the Equity page.
EQUITY_KPIS = ["readmission_90d", "su_time_share", "quit_smoking_90d", "missed_doses_median",
               "pex_median", "dtn_median", "discharge_hour_median"]


# ---------------------------------------------------------------------------
# Compatibility layer for core/equity.py (copied from the original app,
# which expects a METRICS registry and a metric() accessor).
# ---------------------------------------------------------------------------
METRICS = KPI_BY_KEY


def metric(key: str, standard: str | None = None):
    return KPI_BY_KEY[key], None
