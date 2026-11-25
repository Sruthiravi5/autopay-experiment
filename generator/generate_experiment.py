"""
generate_experiment.py — runs the 30-day autopay prompt test in the simulated world.

Run from the repo root, after generate_history.py:
    python generator/generate_experiment.py

Writes the data an analyst would pull after the test:
    data/experiment/assignments.parquet          who was in control or treatment
    data/experiment/prompt_views.parquet         first time each treatment customer saw the prompt
    data/experiment/autopay_enrollments.parquet  October autopay sign-ups in the test population
    data/experiment/statements.parquet           1 Oct and 1 Nov statements
    data/experiment/payments.parquet             payments on those statements (duplicates included)
    data/experiment/service_contacts.parquet     customer service contacts during the test

    data/experiment_broken/assignments.parquet   same test with a 51/49 assignment bug,
                                                 for the sample ratio mismatch check

    data/_truth/experiment_truth.parquet         per-customer truth; NEVER use in analysis
    data/_truth/experiment_truth.json            the true effects the analysis should recover

What happens, step by step:
  1. Eligible customers (open, not on autopay on 1 Oct) are split 50/50 at random.
  2. About 70% of treatment opens the app during October and sees the prompt,
     most of them in the first week.
  3. Everyone can enroll on their own, at their usual monthly rate. Viewers get an
     extra chance from the prompt: larger for new customers, larger for week-1 viewers.
  4. The 1 Nov statement is paid in full and on time by anyone now on autopay, so the
     prompt reaches payment metrics through enrollment.
  5. Past late payers who see the prompt contact customer service more: the planted harm.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg
from generate_history import make_statements_and_payments, save

HISTORY = Path("data/history")
OUT = Path("data/experiment")
OUT_BROKEN = Path("data/experiment_broken")
OUT_TRUTH = Path("data/_truth")
TEST_DAYS = 30


def prior_late_flag(customers):
    """True for customers with any late or missed payment in the history.
    Matches how the analyst defines the segment, so the planted harm lands on a group
    the analysis can actually find."""
    statements = pd.read_parquet(HISTORY / "statements.parquet")
    payments = pd.read_parquet(HISTORY / "payments.parquet").drop_duplicates()
    # Parquet DATE columns load as Python date objects; convert them so pandas can work fast.
    for df, cols in ((statements, ["statement_date", "due_date"]), (payments, ["statement_date", "payment_date"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    first = payments.groupby(["customer_id", "statement_date"], as_index=False)["payment_date"].min()
    s = statements.merge(first, on=["customer_id", "statement_date"], how="left")
    late = s["payment_date"].isna() | (s["payment_date"] > s["due_date"])
    ever_late = late.groupby(s["customer_id"]).any()
    return customers["customer_id"].map(ever_late).fillna(False).to_numpy(dtype=bool)


def main():
    rng = np.random.default_rng(cfg.SEED + 1)  # separate stream from the history
    start = pd.Timestamp(cfg.EXPERIMENT_START)
    days = pd.date_range(start, periods=TEST_DAYS, freq="D")

    customers = pd.read_parquet(HISTORY / "customers.parquet")
    enrollments = pd.read_parquet(HISTORY / "autopay_enrollments.parquet")
    traits = pd.read_parquet(OUT_TRUTH / "customer_traits.parquet")

    # ------------------------------------------------------------------
    # 1. Population and assignment
    # ------------------------------------------------------------------
    already = customers["customer_id"].isin(enrollments["customer_id"])
    eligible = customers[customers["account_status"].eq("open") & ~already].reset_index(drop=True)
    t = traits.set_index("customer_id").loc[eligible["customer_id"]].reset_index()
    n = len(eligible)
    ids = eligible["customer_id"].to_numpy()

    treated = rng.random(n) < 0.5
    is_new = t["is_new"].to_numpy()
    prior_late = prior_late_flag(eligible)

    # ------------------------------------------------------------------
    # 2. Exposure: who sees the prompt, and on which day
    # ------------------------------------------------------------------
    sees = treated & (rng.random(n) < cfg.EXPOSURE_RATE)
    view_day = np.minimum(rng.geometric(cfg.DAILY_FIRST_OPEN_PROB, n) - 1, TEST_DAYS - 1)
    view_day = np.where(sees, view_day, -1)

    # ------------------------------------------------------------------
    # 3. Enrollment: organic chance for everyone, plus the prompt's lift for viewers
    # ------------------------------------------------------------------
    base_lift = np.where(is_new, cfg.LIFT_NEW_CUSTOMERS, cfg.TRUE_LIFT)
    novelty = np.where(view_day < 7, cfg.WEEK1_MULTIPLIER, 1.0)
    # Scale so each tenure group's average lift among viewers equals its planted lift.
    for group in (is_new, ~is_new):
        viewers = sees & group
        novelty[viewers] = novelty[viewers] / novelty[viewers].mean()
    lift = np.where(sees, base_lift * novelty, 0.0)

    p_organic = t["enroll_propensity"].to_numpy()
    # Two independent chances: organic (p) and prompted (q). Together they give p + lift.
    q_prompt = np.clip(lift / (1 - p_organic), 0, 1)
    organic = rng.random(n) < p_organic
    prompted = rng.random(n) < q_prompt

    organic_day = rng.integers(0, TEST_DAYS, n)
    delay = rng.geometric(cfg.RESPONSE_DELAY_PROB, n) - 1
    prompted_day = np.minimum(view_day + delay, TEST_DAYS - 1)
    enroll_day = np.where(organic & prompted, np.minimum(organic_day, prompted_day),
                          np.where(organic, organic_day, prompted_day))
    enrolled = organic | prompted

    enrolled_on = np.full(n, np.datetime64("NaT", "ns"))
    enrolled_on[enrolled] = days[enroll_day[enrolled]].to_numpy()

    # ------------------------------------------------------------------
    # 4. Statements and payments for 1 Oct and 1 Nov
    # Reuses the history logic, so payments behave exactly as before. Autopay set up in
    # October applies from the 1 Nov statement onward.
    # ------------------------------------------------------------------
    gen_customers = eligible.assign(open_date=t["true_open_date"].to_numpy())
    statements, payments = make_statements_and_payments(
        rng, gen_customers, t, enrolled_on, [start, start + pd.DateOffset(months=1)])
    first_new_id = int(pd.read_parquet(HISTORY / "payments.parquet")["payment_id"].max()) + 1
    payments["payment_id"] += first_new_id - 1
    # The same ingestion bug is still in production: some payments load twice.
    dup = payments.sample(frac=cfg.DUPLICATE_PAYMENT_RATE, random_state=cfg.SEED + 1)
    payments = (pd.concat([payments, dup], ignore_index=True)
                .sort_values(["payment_date", "payment_id"], kind="stable").reset_index(drop=True))

    # ------------------------------------------------------------------
    # 5. Customer service contacts: the guardrail, with a planted harm
    # ------------------------------------------------------------------
    harmed = sees & prior_late
    contact_mult = (np.where(prior_late, cfg.LATE_PAYER_BASE_CONTACT_MULT, 1.0)
                    * np.where(harmed, 1 + cfg.LATE_PAYER_CONTACT_LIFT, 1.0))
    n_contacts = rng.poisson(cfg.BASE_CONTACT_RATE * contact_mult)
    contact_customer = np.repeat(ids, n_contacts)
    contacts = pd.DataFrame({
        "contact_id": np.arange(len(contact_customer), dtype="int64") + 1,
        "customer_id": contact_customer,
        "contact_date": days[rng.integers(0, TEST_DAYS, len(contact_customer))].to_numpy(),
    }).sort_values(["contact_date", "contact_id"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Save what the analyst receives
    # ------------------------------------------------------------------
    assignments = pd.DataFrame({
        "customer_id": ids,
        "variant": np.where(treated, "treatment", "control"),
        "assigned_date": start,
    })
    views = pd.DataFrame({"customer_id": ids[sees],
                          "first_view_date": days[view_day[sees]].to_numpy()})
    october_enrollments = pd.DataFrame({"customer_id": ids[enrolled],
                                        "enrollment_date": enrolled_on[enrolled]})

    print(f"Test population: {n:,} customers")
    print("Saving:")
    save(assignments, OUT / "assignments.parquet")
    save(views, OUT / "prompt_views.parquet")
    save(october_enrollments, OUT / "autopay_enrollments.parquet")
    save(statements, OUT / "statements.parquet")
    save(payments, OUT / "payments.parquet")
    save(contacts, OUT / "service_contacts.parquet")

    # Broken copy: an assignment bug moves some control customers into treatment,
    # pushing treatment to 51% of the test. Only the assignment table is affected.
    flip = (~treated) & (rng.random(n) < (cfg.SRM_BROKEN_SHARE - 0.5) / 0.5)
    save(assignments.assign(variant=np.where(treated | flip, "treatment", "control")),
         OUT_BROKEN / "assignments.parquet")

    # ------------------------------------------------------------------
    # The truth, for validating the analysis afterwards
    # ------------------------------------------------------------------
    truth = pd.DataFrame({"customer_id": ids, "treated": treated, "saw_prompt": sees,
                          "view_day": view_day, "true_lift": lift, "is_new": is_new,
                          "prior_late": prior_late, "contact_multiplier": contact_mult})
    save(truth, OUT_TRUTH / "experiment_truth.parquet")

    def mean_lift(mask):
        return float(lift[mask].mean())

    summary = {
        "itt_enrollment_lift": mean_lift(treated),
        "viewer_enrollment_lift": mean_lift(sees),
        "exposure_rate": float(sees[treated].mean()),
        "itt_lift_new": mean_lift(treated & is_new),
        "itt_lift_tenured": mean_lift(treated & ~is_new),
        "viewer_lift_week1": mean_lift(sees & (view_day < 7)),
        "viewer_lift_later": mean_lift(sees & (view_day >= 7)),
        "contact_lift_prior_late_viewers": cfg.LATE_PAYER_CONTACT_LIFT,
        "contact_lift_prior_late_itt": float(cfg.LATE_PAYER_CONTACT_LIFT * sees[treated & prior_late].mean()),
        "broken_treatment_share": float((treated | flip).mean()),
    }
    (OUT_TRUTH / "experiment_truth.json").write_text(json.dumps(summary, indent=2))
    print(f"  wrote {OUT_TRUTH / 'experiment_truth.json'}")
    print("Done. Analyze data/experiment/; don't peek at data/_truth/.")


if __name__ == "__main__":
    main()
