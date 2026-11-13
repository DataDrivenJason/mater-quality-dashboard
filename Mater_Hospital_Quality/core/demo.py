"""
Demonstration data for the Mater Hospital (simulated, not real patients).
=====================================================================

Writes the three input tables in exactly the layout real extracts must
follow, so the files in data/demo double as templates:

    admissions.csv        one row per admission to the stroke service
    service_monthly.csv   one row per month
    clinic_referrals.csv  one row per referral to the new-patient clinic

A few changes are planted so the charts have something to find:
    * door-to-needle improves from month 14 (a new pathway)
    * NCHD overtime steps up from month 18
    * patients whose first language is not English wait longer for
      thrombolysis; patients experiencing homelessness are readmitted more

Run directly to regenerate:  python -m core.demo
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DIAGNOSES = {  # share of admissions, median length of stay (days)
    "Ischaemic stroke": (0.55, 9.0),
    "Intracerebral haemorrhage": (0.10, 14.0),
    "TIA": (0.18, 2.0),
    "Stroke mimic: seizure": (0.06, 3.0),
    "Stroke mimic: migraine": (0.05, 2.0),
    "Stroke mimic: functional": (0.03, 3.0),
    "Other": (0.03, 4.0),
}
STROKE = {"Ischaemic stroke", "Intracerebral haemorrhage"}


def _yn(x: np.ndarray) -> np.ndarray:
    return np.where(x, "Yes", "No")


def make_demo(months: int = 24, end: str = "2026-10-01", seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    month_starts = pd.date_range(end=end, periods=months, freq="MS")
    extract_date = month_starts[-1] + pd.offsets.MonthBegin(1)

    # ---- admissions ---------------------------------------------------
    rows = []
    names = list(DIAGNOSES)
    probs = np.array([v[0] for v in DIAGNOSES.values()])
    for m, start in enumerate(month_starts):
        n = rng.poisson(80)
        days_in_month = (start + pd.offsets.MonthBegin(1) - start).days
        for _ in range(n):
            dx = names[rng.choice(len(names), p=probs / probs.sum())]
            arrival = start + pd.Timedelta(minutes=int(rng.integers(0, days_in_month * 1440)))
            age = int(np.clip(rng.normal(72, 13), 25, 99))
            sex = rng.choice(["Female", "Male"])
            dep = int(rng.choice([1, 2, 3, 4, 5], p=[0.15, 0.18, 0.2, 0.22, 0.25]))
            english = bool(rng.random() > 0.14)
            homeless = bool(rng.random() < 0.04)
            los = max(1.0, round(float(rng.lognormal(np.log(DIAGNOSES[dx][1]), 0.6)), 1))
            stroke = dx in STROKE
            died = bool(stroke and rng.random() < (0.09 if age < 80 else 0.16))
            # Discharge clock time: centred on 14:30.
            disch_hour = float(np.clip(rng.normal(14.5, 2.3), 8, 21.9))
            discharge = (arrival.normalize() + pd.Timedelta(days=int(round(los)))
                         + pd.Timedelta(hours=disch_hour))
            row = {
                "admission_id": f"MAT{start:%y%m}{len(rows):05d}",
                "arrival_datetime": arrival.strftime("%Y-%m-%d %H:%M"),
                "discharge_datetime": discharge.strftime("%Y-%m-%d %H:%M"),
                "los_days": los,
                "diagnosis": dx,
                "died_inpatient": "Yes" if died else "No",
                "age": age, "sex": sex, "deprivation_quintile": dep,
                "first_language_english": "Yes" if english else "No",
                "homeless": "Yes" if homeless else "No",
            }
            if stroke:
                thrombolysed = dx == "Ischaemic stroke" and rng.random() < 0.13
                if thrombolysed:
                    base = 52 if m < 14 else 39
                    row["door_to_needle_min"] = round(float(
                        rng.gamma(9, (base + (12 if not english else 0)) / 9)))
                su_share = float(np.clip(rng.beta(9, 1.3) - (0.06 if age >= 80 else 0), 0, 1))
                row["su_bed_days"] = round(los * su_share, 1)
                p_readmit = 0.12 + (0.15 if homeless else 0)
                row["readmitted_90d"] = "Yes" if (not died and rng.random() < p_readmit) else "No"
                smoker = rng.random() < 0.24
                row["smoker_at_admission"] = "Yes" if smoker else "No"
                followed = smoker and not died and rng.random() < 0.72
                row["smoking_followup_90d"] = "Yes" if followed else "No"
                row["quit_at_90d"] = "Yes" if (followed and rng.random() < 0.38) else "No"
                row["doses_missed"] = int(rng.poisson(1.3))
                if not died and rng.random() < 0.45:
                    row["pex_score"] = int(np.clip(round(rng.normal(8.1, 1.4)), 0, 10))
            rows.append(row)
    adm = pd.DataFrame(rows)

    # Outcomes after the extract date cannot be known yet. In a real
    # extract the 90-day columns simply say "No" for these patients --
    # the dashboard handles that (censoring), so the demo mimics it.
    disch = pd.to_datetime(adm["discharge_datetime"])
    unknown = disch + pd.Timedelta(days=90) > extract_date
    adm.loc[unknown & adm["readmitted_90d"].notna(), "readmitted_90d"] = "No"
    adm.loc[unknown & adm["smoking_followup_90d"].notna(), ["smoking_followup_90d", "quit_at_90d"]] = "No"
    # Patients still in hospital have no discharge yet.
    still_in = disch > extract_date
    adm.loc[still_in, ["discharge_datetime", "los_days", "pex_score"]] = np.nan

    # ---- service_monthly ---------------------------------------------
    m_idx = np.arange(months)
    audits = np.clip(np.round(5 + np.cumsum(rng.normal(0.08, 0.7, months))), 2, 14)
    svc = pd.DataFrame({
        "month": month_starts.strftime("%Y-%m"),
        "incidents_total": rng.poisson(18, months),
        "incidents_mod_severe": rng.poisson(2.2, months),
        "complaints_total": rng.poisson(3.0, months),
        "complaints_mod_severe": rng.poisson(0.6, months),
        "external_test_cost_eur": np.round(rng.normal(11500, 1100, months), -1),
        "external_test_budget_eur": 12000,
        "nchd_overtime_cost_eur": np.round(rng.normal(np.where(m_idx < 18, 23500, 28500), 1800), -1),
        "nchd_overtime_budget_eur": 25000,
        "active_audits": audits.astype(int),
    })

    # ---- clinic_referrals ---------------------------------------------
    crow = []
    for m, start in enumerate(month_starts):
        for _ in range(rng.poisson(42)):
            ref = start + pd.Timedelta(days=int(rng.integers(0, 28)))
            wait = float(rng.gamma(4, (34 if m < 16 else 25) / 4))
            appt = ref + pd.Timedelta(days=int(round(wait)))
            crow.append({"referral_id": f"CLN{len(crow):06d}",
                         "referral_date": ref.strftime("%Y-%m-%d"),
                         "appointment_date": appt.strftime("%Y-%m-%d") if appt < extract_date else ""})
    clinic = pd.DataFrame(crow)
    return {"admissions": adm, "service_monthly": svc, "clinic_referrals": clinic}


def write_demo(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in make_demo().items():
        df.to_csv(folder / f"{name}.csv", index=False)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "demo"
    write_demo(out)
    print(f"Demo tables written to {out}")
