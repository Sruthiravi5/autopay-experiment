# Autopay experiment

**Can one in-app prompt get more cardholders onto autopay, and does it help or harm anyone?**

An end-to-end A/B test run the way an analyst at a card issuer would run it: explore the history, preregister the plan, size the test, check its health, analyze it, validate the method, and make a ship or no-ship call.

The data is simulated. That's deliberate: because the true effects are planted, the project can prove its methods recover them, which isn't possible with real data. The analysis code never reads the generator's settings or hidden truth.

## Progress

| Stage | Status | Output |
|---|---|---|
| 1. Frame | Done | Question, metrics and decision rule in the preregistration |
| 2. Explore | Done | [`results/exploration_summary.md`](results/exploration_summary.md) |
| 3. Design | Done | [`docs/preregistration.md`](docs/preregistration.md), [`results/power_analysis.md`](results/power_analysis.md) |
| 4. Run | Done | 30-day test data in `data/experiment/`, described in the [data dictionary](docs/data_dictionary.md) |
| 5. Check health | Done | [`results/health_checks.md`](results/health_checks.md), built with PySpark and Spark SQL ([Databricks setup](docs/databricks_setup.md)) |
| 6. Analyze | Next | Intent-to-treat, effect among viewers, CUPED, segments, guardrails |
| 7. Validate | To do | A/A false-positive rate, recovery of planted effects |
| 8. Decide | To do | Tableau readout and decision memo |

## What exploration found

- **Two planted data problems caught.** 0.5% of payment rows were duplicates from an ingestion bug, and 1% of customers had no open date. Duplicates are dropped. Missing open dates are kept, and customers whose first statement falls inside the history are recognized as new.
- **A stable baseline.** 8.0% of eligible customers turn on autopay in a given month with no prompt; new customers enroll at about 1.5x the rate of tenured ones.
- **Where CUPED helps, and where it doesn't.** Rehearsing CUPED on history (months 1 to 5 predicting month 6):

| Metric | Correlation with the past | Variance CUPED removes |
|---|---|---|
| Share of balance paid | 0.81 | 66% |
| Paid on time | 0.17 | 3% |
| Enrolled in autopay | 0.04 | 0.2% |

Share of balance paid is a stable habit (transactors pay in full, revolvers carry a balance), so the past predicts it well. Paying on time and enrolling are mostly one-off events in a given month, so CUPED barely helps them. The test is sized by power analysis, not by CUPED.

## Design in one paragraph

About 525,000 eligible customers are split 50/50 for 30 days. The primary metric is 30-day autopay enrollment, analyzed intent-to-treat; the smallest detectable lift is 0.21 points (8.00% to 8.21%). Because not everyone opens the app, the effect among customers who actually saw the prompt is estimated separately. Guardrails on customer service contacts and missed payments must pass before anything ships. Details and the decision rule are in the [preregistration](docs/preregistration.md).

## How the test was run (Stage 4)

`generator/generate_experiment.py` plays out the 30-day test. It splits the 525,047 eligible customers 50/50, lets about 70% of the treatment group open the app and see the prompt (most in the first week), and records autopay sign-ups, the 1 Nov statement and its payments, and customer service contacts. It also writes a copy with a deliberate 51/49 assignment bug for the health check to catch. The true effects are saved in `data/_truth/` and are only opened at the end, to check whether the analysis found them.

## Health check (Stage 5)

Before reading any result, the test was checked for problems. PySpark and Spark SQL (`pipeline/01_load.py`, `pipeline/02_metrics.sql`) clean the raw tables and build one row per test customer; the same code runs in Databricks or locally.

- **The split is sound.** 49.92% treatment overall (p = 0.22), and 50/50 within every planned segment.
- **The check works.** A copy with a deliberate 51/49 assignment bug fails with p = 9×10⁻⁴⁰.
- **The groups match before the test.** Every pre-test variable is within 0.003 standard deviations (limit 0.1).
- **Exposure is clean.** No control customer saw the prompt; 70.2% of treatment did, two-thirds of them in week 1.

No outcome was compared between the groups at this stage. Full results: [`results/health_checks.md`](results/health_checks.md).

## Repository

```
generator/   builds the simulated world (config.py holds the hidden truth)
pipeline/    analysis steps, run in order
stats/       reusable statistics: power, sample ratio mismatch, balance (CUPED and estimators next)
tests/       checks on the statistics and the generated data
docs/        preregistration, data dictionary, decision memo
results/     outputs written by the pipeline
```

## Run it

Python 3.11 or later.

```bash
pip install -r requirements.txt
python generator/generate_history.py   # about 10 seconds; writes data/history/
python pipeline/00_explore.py          # writes results/exploration_summary.md and baseline.json
python stats/power.py                  # writes results/power_analysis.md
python generator/generate_experiment.py  # about 10 seconds; writes data/experiment/
python pipeline/01_load.py             # Spark: cleans the data and builds customer_metrics (needs Java)
python pipeline/03_health_checks.py    # writes results/health_checks.md
python -m pytest tests                 # checks the statistics and the generated test data
```

`data/` is not committed; the generator recreates it exactly from a fixed seed.
