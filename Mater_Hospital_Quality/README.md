# Mater Hospital stroke service quality dashboard

There are three pages:

- **Scorecards** has a card for each of the 17 KPIs, grouped by pillar (Safe, Effective, Person-centred, Timely, Efficient, Equitable and Culture).
- **Control charts** shows the monthly chart behind each card.
- **Equity** compares the patient KPIs across age, sex, deprivation (based on address), first language and housing.

## Starting it

1. The first time, double-click `setup.bat`. It sets up Python for this folder and downloads the packages, which takes a few minutes and needs the internet. Until you do this, the dashboard borrows the Python setup in `C:\Users\jason\stroke_quality_dashboard`, so don't delete that folder yet.
2. Double-click `run_dashboard.bat`. Your browser will open at http://localhost:8501.
3. Leave the black window open while you're using it. Closing it stops the dashboard.

It only runs on this computer, and no data leaves the machine.

You might see `ConnectionResetError` messages in the black window. They're harmless and just mean a browser tab was closed.

If it won't start, whatever the window printed is saved in `dashboard_log.txt`.

## Using your own data

At the moment it shows made-up demo data from the `data\demo` folder. To use real data, save your files in the `data` folder with the names below. They can be CSV, Excel (.xlsx) or parquet. As soon as one of them is there, the demo data stops being used. The demo files have the exact layout, so they're a good template.

### admissions (one row per admission to the stroke service)

| Column | What goes in it |
|---|---|
| `arrival_datetime` | Date and time of arrival. This one is required. |
| `discharge_datetime` | Date and time of discharge |
| `los_days` | Length of stay in days |
| `diagnosis` | For example Ischaemic stroke, Intracerebral haemorrhage, TIA, Stroke mimic: seizure. Only the first two count as strokes for the patient KPIs. |
| `died_inpatient` | Yes or No |
| `door_to_needle_min` | Minutes from arrival to thrombolysis. Leave it blank if the patient wasn't thrombolysed. |
| `readmitted_90d` | Yes or No |
| `su_bed_days` | Days spent on the stroke unit |
| `smoker_at_admission`, `smoking_followup_90d`, `quit_at_90d` | Yes or No |
| `doses_missed` | Doses missed, not counting ones held back for clinical reasons |
| `pex_score` | Patient experience score from 0 to 10. Leave it blank if there was no survey. |
| `age` | Age in years |
| `sex` | Female or Male |
| `deprivation_quintile` | 1 for least deprived up to 5 for most deprived, based on address |
| `first_language_english` | Yes or No |
| `homeless` | Yes or No |

Dates can be written as `2026-01-05 14:30` or `05/01/2026 14:30` (day first). Yes/No columns also accept Y/N, True/False or 1/0.

### service_monthly (one row per month)

`month` (for example `2026-01`), `incidents_total`, `incidents_mod_severe`, `complaints_total`, `complaints_mod_severe`, `external_test_cost_eur`, `external_test_budget_eur`, `nchd_overtime_cost_eur`, `nchd_overtime_budget_eur` and `active_audits` (the number running at the end of the month).

### clinic_referrals (one row per referral to the new-patient stroke clinic)

`referral_id`, `referral_date` and `appointment_date`. Leave the appointment date blank if the patient hasn't been seen yet.

Once you've added your files, open **Data check** in the sidebar. It tells you how many rows were read and whether anything couldn't be read.

## Targets

These are placeholders for now and need to be agreed locally. You can change them in `core\kpis.py`.

| KPI | Target |
|---|---|
| Readmission within 90 days | 18% or lower |
| Time on a stroke unit | 90% or higher |
| Quit smoking at 90 days | 40% or higher |
| Missed doses (median) | 1 or fewer |
| Patient experience (median) | 8 out of 10 or higher |
| Door to needle (median) | 40 minutes or less |
| Wait for new-patient clinic (median) | 28 days or less |
| Time of discharge (median) | 13:00 or earlier |
| External test cost and NCHD overtime | The monthly budget in `service_monthly` |
| Incidents, complaints and audits | No target |

## Reading the dashboard

- The left icon on each card shows whether something has really changed. The NHS Making Data Count approach treats it as a change if a month falls outside the limits, if 7 months in a row sit on one side of the average, if 7 months in a row go up or go down, or if 2 out of 3 months are close to a limit.
- The right icon shows whether you can expect to hit the target. "Reliably misses target" means the process itself needs to change, because pushing harder on individual months won't get there.
- The 90-day KPIs stop about four months before the latest data. A month only appears once 95% of its patients have had their 90-day follow-up.
- Length of stay is grouped by the month patients went home. Grouping by month of arrival would make the latest month look shorter than it really is.
- The equity figures aren't adjusted for case mix, so treat any difference as a reason to look closer.

## Checking it still works after a change

```text
.venv\Scripts\python.exe tests\smoke_pages.py
```

This opens all three pages and prints OK for each one, or shows the error.
