# Databricks notebook source
"""
03_health_checks.py — Stage 5: was the test run correctly?

Run after 01_load.py:
    python pipeline/03_health_checks.py          (your laptop)
    or open it in Databricks and click Run all

Nothing here compares outcomes between the groups. Health checks come before any
result is read, so a broken test can't be explained away after seeing a number
you like. Every check uses things fixed before the test started, the assignment
itself, or logging that has nothing to do with the outcome.

Checks
  1. Sample ratio mismatch: is the split 50/50, overall and within each planned segment?
  2. Proof the check works: the deliberately broken 51/49 copy must fail.
  3. Balance: do the groups look alike on pre-test behavior?
  4. Exposure: only treatment saw the prompt, and when.
  5. Data integrity: one row per customer, nothing missing, dates in the window.

Writes results/health_checks.md.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

ON_DATABRICKS = "DATABRICKS_RUNTIME_VERSION" in os.environ
if ON_DATABRICKS:
    sys.path.append(os.path.abspath("../stats"))
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    metrics = spark.table("workspace.autopay.customer_metrics").toPandas()
    broken = pd.read_parquet("/Volumes/workspace/autopay/raw/experiment_broken/assignments.parquet")
    load_log = json.loads(Path("/Volumes/workspace/autopay/raw/load_log.json").read_text())
    OUT = Path("../results/health_checks.md")
else:
    sys.path.append(str(Path(__file__).resolve().parents[1] / "stats"))
    metrics = pd.read_parquet("data/warehouse/customer_metrics")
    broken = pd.read_parquet("data/experiment_broken/assignments.parquet")
    load_log = json.loads(Path("results/load_log.json").read_text())
    OUT = Path("results/health_checks.md")

from balance import SMD_THRESHOLD, balance_table  # noqa: E402
from srm import SRM_ALPHA, srm_from_labels  # noqa: E402

summary = []   # (check, result, detail) rows for the top table
sections = []  # detail sections


def record(check, passed, detail, expected_fail=False):
    if expected_fail:
        result = "Caught, as expected" if not passed else "**Missed: check is broken**"
    else:
        result = "Pass" if passed else "**FAIL**"
    summary.append((check, result, detail))
    return passed != expected_fail  # True when the outcome is what a healthy test needs


healthy = True

# ---------------------------------------------------------------------------
# 1. Sample ratio mismatch, overall and within segments
# ---------------------------------------------------------------------------
overall = srm_from_labels(metrics["variant"])
healthy &= record("Sample ratio, all customers", overall["passed"],
                  f"treatment {overall['treatment_share']:.2%}, p = {overall['p_value']:.2f}")

segment_rows = []
segments = {f"Tenure: {g}": metrics["tenure_group"] == g for g in ("new", "tenured", "unknown")}
segments["Prior late payers"] = metrics["prior_late"] == 1
segments["No late payments"] = metrics["prior_late"] == 0
for name, mask in segments.items():
    r = srm_from_labels(metrics.loc[mask, "variant"])
    segment_rows.append((name, r))
segments_ok = all(r["passed"] for _, r in segment_rows)
worst_p = min(r["p_value"] for _, r in segment_rows)
healthy &= record("Sample ratio, within each planned segment", segments_ok,
                  f"{len(segment_rows)} segments, smallest p = {worst_p:.2f}")

sec = ["## 1. Sample ratio mismatch", "",
       f"A chi-square test of the observed split against 50/50. The test fails when p < {SRM_ALPHA}: "
       "strict, because with 525,000 customers only a real problem should stop the analysis.", "",
       "| Group | Control | Treatment | Treatment share | p-value | Result |", "|---|---|---|---|---|---|",
       f"| All customers | {overall['n_control']:,} | {overall['n_treatment']:,} | "
       f"{overall['treatment_share']:.2%} | {overall['p_value']:.3f} | {'Pass' if overall['passed'] else 'FAIL'} |"]
for name, r in segment_rows:
    sec.append(f"| {name} | {r['n_control']:,} | {r['n_treatment']:,} | {r['treatment_share']:.2%} | "
               f"{r['p_value']:.3f} | {'Pass' if r['passed'] else 'FAIL'} |")
sec += ["", "Checking within segments catches bugs that hit only one group of customers, "
        "which an overall check can hide.", ""]
sections += sec

# ---------------------------------------------------------------------------
# 2. Proof the check works: the broken copy must fail
# ---------------------------------------------------------------------------
broken_result = srm_from_labels(broken["variant"])
healthy &= record("Broken 51/49 copy is detected", broken_result["passed"],
                  f"treatment {broken_result['treatment_share']:.2%}, p = {broken_result['p_value']:.1e}",
                  expected_fail=True)
sections += ["## 2. Proof the check works", "",
             "The same test on a copy with a deliberate assignment bug, where about 2% of control customers "
             "were moved into treatment:", "",
             f"- Control {broken_result['n_control']:,}, treatment {broken_result['n_treatment']:,} "
             f"({broken_result['treatment_share']:.2%}).",
             f"- p = {broken_result['p_value']:.1e}, far below {SRM_ALPHA}, so the check stops the analysis.", "",
             f"A {broken_result['treatment_share']:.0%}/{1 - broken_result['treatment_share']:.0%} split looks "
             f"harmless by eye. At this scale it is about "
             f"{(broken_result['treatment_share'] - 0.5) / (0.5 / len(broken) ** 0.5):.0f} standard deviations "
             "from 50/50, so it cannot be chance.", ""]

# ---------------------------------------------------------------------------
# 3. Balance on pre-test variables
# ---------------------------------------------------------------------------
metrics["is_new"] = (metrics["tenure_group"] == "new").astype(int)
covariates = {
    "pre_on_time_rate": "On-time rate, Apr to Sep",
    "pre_share_paid": "Share of balance paid, Apr to Sep",
    "pre_days_late": "Average days late, Apr to Sep",
    "pre_statements": "Statements in history",
    "credit_line": "Credit line ($)",
    "prior_late": "Prior late payer",
    "is_new": "New customer",
}
table = balance_table(metrics, "variant", list(covariates))
balanced = bool(table["balanced"].all())
healthy &= record("Groups balanced before the test", balanced,
                  f"largest |SMD| = {table['smd'].abs().max():.3f} (limit {SMD_THRESHOLD})")
sec = ["## 3. Balance before the test", "",
       "Standardized mean difference (SMD) between treatment and control on behavior measured before "
       f"1 Oct. Balanced when |SMD| < {SMD_THRESHOLD}.", "",
       "| Variable | Control | Treatment | SMD | Result |", "|---|---|---|---|---|"]
for _, r in table.iterrows():
    fmt = "{:,.0f}" if r["covariate"] == "credit_line" else "{:.3f}"
    sec.append(f"| {covariates[r['covariate']]} | {fmt.format(r['mean_control'])} | "
               f"{fmt.format(r['mean_treatment'])} | {r['smd']:+.4f} | {'Pass' if r['balanced'] else 'FAIL'} |")
sec += ["", "These are also the variables the analysis uses for CUPED, so balance here matters twice.", ""]
sections += sec

# ---------------------------------------------------------------------------
# 4. Exposure
# ---------------------------------------------------------------------------
treat = metrics["variant"] == "treatment"
control_views = int(metrics.loc[~treat, "saw_prompt"].sum())
healthy &= record("No control customer saw the prompt", control_views == 0, f"{control_views} control views")
exposure = metrics.loc[treat, "saw_prompt"].mean()
view_day = (pd.to_datetime(metrics.loc[treat & (metrics["saw_prompt"] == 1), "first_view_date"])
            - pd.Timestamp("2026-10-01")).dt.days
by_week = (view_day // 7 + 1).clip(upper=5).value_counts(normalize=True).sort_index()
summary.append(("Share of treatment who saw the prompt", "Recorded", f"{exposure:.1%}"))
sec = ["## 4. Exposure", "",
       f"- Control customers who saw the prompt: {control_views} (must be zero).",
       f"- Treatment customers who saw it: {exposure:.1%}. The rest never opened the app during the test. "
       "The analysis reports the effect on everyone assigned (intent-to-treat) and divides by this share "
       "for the effect among viewers.", "",
       "| Week of first view | Share of viewers |", "|---|---|"]
sec += [f"| Week {int(w)}{' (days 29-30)' if w == 5 else ''} | {s:.1%} |" for w, s in by_week.items()]
sec += ["", "Most customers see the prompt in week 1, so any novelty effect will show up early. "
        "The analysis checks the effect week by week.", ""]
sections += sec

# ---------------------------------------------------------------------------
# 5. Data integrity
# ---------------------------------------------------------------------------
required = ["variant", "tenure_group", "pre_on_time_rate", "pre_share_paid", "nov_share_paid",
            "nov_on_time", "nov_missed", "service_contacts"]
missing = {c: int(metrics[c].isna().sum()) for c in required if metrics[c].isna().any()}
weeks_ok = metrics["enroll_week"].dropna().between(1, 5).all()
integrity = {
    "One row per customer": metrics["customer_id"].is_unique,
    "Every assigned customer has a metrics row":
        len(metrics) == load_log["row_counts"]["exp_assignments"],
    "No missing values in metrics": not missing,
    "Enrollments fall inside the 30-day window": bool(weeks_ok),
}
integrity_ok = all(integrity.values())
healthy &= record("Data integrity", integrity_ok,
                  f"{sum(integrity.values())} of {len(integrity)} checks pass")
sec = ["## 5. Data integrity", ""]
sec += [f"- {name}: {'yes' if ok else '**no**'}" for name, ok in integrity.items()]
if missing:
    sec.append(f"- Missing values: {missing}")
sec += [f"- Duplicate payments removed before building metrics: {load_log['hist_duplicate_payments_removed']:,} "
        f"in history and {load_log['exp_duplicate_payments_removed']:,} during the test "
        "(the ingestion bug found in exploration is still running).", ""]
sections += sec

# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
verdict = ("**Healthy.** Every check passed, and the broken copy was caught. The test can go to analysis."
           if healthy else "**Not healthy.** Stop and investigate the failed checks before reading any results.")
out = ["# Health checks", "", verdict, "",
       "| Check | Result | Detail |", "|---|---|---|"]
out += [f"| {c} | {r} | {d} |" for c, r, d in summary]
out += [""] + sections
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(out) + "\n")
print("\n".join(out))
if not healthy:
    sys.exit(1)
