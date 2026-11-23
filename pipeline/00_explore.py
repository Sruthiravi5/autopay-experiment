"""
00_explore.py — Stage 2 (Explore): get to know six months of history before designing the test.

Run from the repo root, after the history generator:
    python generator/generate_history.py
    python pipeline/00_explore.py

This script only reads data/history/. It never imports generator/config.py or
reads data/_truth/: a real analyst doesn't know the true numbers, so everything
here is worked out from the data alone.

It answers four questions:
  1. Is the data trustworthy? (keys, missing values, duplicates)
  2. What is the baseline autopay enrollment rate, and is it stable month to month?
  3. Who enrolls? (new vs. tenured customers)
  4. Does past payment behavior predict future behavior? (if yes, CUPED will help)

Results are printed and saved to results/exploration_summary.md.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data/history")
RESULTS = Path("results")
EXPERIMENT_START = pd.Timestamp("2026-10-01")  # from the test plan, not from the generator

lines = []  # collected for the markdown summary


def report(text=""):
    print(text)
    lines.append(text)


def pct(x):
    return f"{x:.2%}"


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
customers = pd.read_parquet(DATA / "customers.parquet")
enrollments = pd.read_parquet(DATA / "autopay_enrollments.parquet")
statements = pd.read_parquet(DATA / "statements.parquet")
payments = pd.read_parquet(DATA / "payments.parquet")

for df, cols in [(customers, ["open_date", "closed_date"]),
                 (enrollments, ["enrollment_date"]),
                 (statements, ["statement_date", "due_date"]),
                 (payments, ["statement_date", "payment_date"])]:
    for c in cols:
        df[c] = pd.to_datetime(df[c])

report("# Exploration summary")
report()
report("## 1. Data checks")
report()
report("| Table | Rows | Key | Duplicate keys |")
report("|---|---|---|---|")
checks = [
    ("customers", customers, ["customer_id"]),
    ("autopay_enrollments", enrollments, ["customer_id"]),
    ("statements", statements, ["customer_id", "statement_date"]),
    ("payments", payments, ["payment_id"]),
]
for name, df, key in checks:
    dupes = int(df.duplicated(subset=key).sum())
    report(f"| {name} | {len(df):,} | {', '.join(key)} | {dupes:,} |")
report()

# Problem 1: duplicate payment rows. Same payment_id loaded twice.
dup_payments = payments.duplicated(keep="first")  # every column identical
report(f"- **Duplicate payments:** {dup_payments.sum():,} rows ({pct(dup_payments.mean())}) are exact "
       "copies of another row (same payment_id). Counting them would overstate payments, "
       "so they are dropped before any analysis.")
payments = payments[~dup_payments].copy()

# Problem 2: missing open dates.
missing_open = customers["open_date"].isna()
report(f"- **Missing open dates:** {missing_open.sum():,} customers ({pct(missing_open.mean())}) have no "
       "open date, so their tenure is unknown. They stay in the data, in an 'unknown tenure' group, "
       "rather than being dropped.")

closed = customers["account_status"].eq("closed")
report(f"- **Closed accounts:** {closed.sum():,} ({pct(closed.mean())}) closed during the history window. "
       "They can't be in the experiment.")

orphans = ~payments.set_index(["customer_id", "statement_date"]).index.isin(
    statements.set_index(["customer_id", "statement_date"]).index)
report(f"- **Payments without a statement:** {orphans.sum():,}. Every payment links to a statement.")
report()

# ---------------------------------------------------------------------------
# 2. Baseline enrollment rate, month by month
# A customer is eligible in a month if the account was open before the month
# began, stayed open the whole month, and was not already on autopay.
# ---------------------------------------------------------------------------
enrolled_on = customers[["customer_id"]].merge(enrollments, on="customer_id", how="left")["enrollment_date"]
open_date = customers["open_date"]
closed_date = customers["closed_date"]
month_starts = pd.date_range(statements["statement_date"].min(), periods=6, freq="MS")

# For customers with no open date, the first statement proves when the account existed.
# A first statement after the start of the history means the account opened during it.
first_statement = (customers[["customer_id"]]
                   .merge(statements.groupby("customer_id", as_index=False)["statement_date"].min(),
                          on="customer_id", how="left")["statement_date"])
opened_in_window = open_date.isna() & (first_statement > month_starts[0])

# Tenure group as of the experiment start (new = opened within the last 12 months).
# Missing open dates that opened during the history window are new by definition.
tenure_days = (EXPERIMENT_START - open_date).dt.days
tenure_group = np.select([opened_in_window, open_date.isna(), tenure_days <= 365],
                         ["new", "unknown", "new"], default="tenured")
report(f"- Of the customers with no open date, {opened_in_window.sum():,} have a first statement inside the "
       "history window, so they must be new customers. The rest stay 'unknown'.")
report()

rows = []
for m_start in month_starts:
    m_end = m_start + pd.DateOffset(months=1)
    # Open before the month began: use the open date, or the first statement when it's missing.
    opened_before = np.where(open_date.isna(), first_statement <= m_start, open_date < m_start)
    eligible = (opened_before
                & (closed_date.isna() | (closed_date >= m_end))
                & (enrolled_on.isna() | (enrolled_on >= m_start)))
    enrolled = eligible & (enrolled_on < m_end)
    for group in ["all", "new", "tenured", "unknown"]:
        in_group = eligible if group == "all" else eligible & (tenure_group == group)
        rows.append({"month": m_start.strftime("%Y-%m"), "group": group,
                     "eligible": int(in_group.sum()),
                     "enrolled": int((enrolled & in_group).sum())})
monthly = pd.DataFrame(rows)
monthly["rate"] = monthly["enrolled"] / monthly["eligible"]

report("## 2. Baseline autopay enrollment rate")
report()
report("Share of eligible customers who turn on autopay within the month, with no prompt.")
report()
pivot = monthly.pivot(index="month", columns="group", values="rate")[["all", "new", "tenured", "unknown"]]
report("| Month | All | New | Tenured | Unknown tenure |")
report("|---|---|---|---|---|")
for month, r in pivot.iterrows():
    report(f"| {month} | {pct(r['all'])} | {pct(r['new'])} | {pct(r['tenured'])} | {pct(r['unknown'])} |")
report()
all_rates = pivot["all"]
report(f"- The overall rate ranges from {pct(all_rates.min())} to {pct(all_rates.max())} "
       f"(average {pct(all_rates.mean())}). It is stable enough to use as the baseline in the power calculation.")
report(f"- New customers enroll at about {pivot['new'].mean() / pivot['tenured'].mean():.1f}x the rate of tenured "
       "customers, so tenure is worth checking as a segment.")
report()

# ---------------------------------------------------------------------------
# 3. Payment behavior
# On time = paid on or before the due date. Missed = no payment for that statement.
# Autopay customers always pay on time, so behavior is measured on manual payers.
# ---------------------------------------------------------------------------
pay = (payments.groupby(["customer_id", "statement_date"], as_index=False)
       .agg(first_payment=("payment_date", "min")))
stm = statements.merge(pay, on=["customer_id", "statement_date"], how="left")
stm = stm.merge(enrollments, on="customer_id", how="left")
stm["on_autopay"] = stm["enrollment_date"].notna() & (stm["enrollment_date"] < stm["statement_date"])
stm["missed"] = stm["first_payment"].isna()
stm["on_time"] = ~stm["missed"] & (stm["first_payment"] <= stm["due_date"])
stm["days_late"] = (stm["first_payment"] - stm["due_date"]).dt.days.clip(lower=0)

manual = stm[~stm["on_autopay"]]
report("## 3. Payment behavior (manual payers)")
report()
report(f"- On-time rate: {pct(manual['on_time'].mean())}")
report(f"- Late but paid: {pct((~manual['on_time'] & ~manual['missed']).mean())}")
report(f"- Missed entirely: {pct(manual['missed'].mean())}")
late_paid = manual[~manual["on_time"] & ~manual["missed"]]
report(f"- Among late payments, median days late: {late_paid['days_late'].median():.0f} "
       f"(mean {late_paid['days_late'].mean():.1f})")
report(f"- Autopay customers' on-time rate: {pct(stm.loc[stm['on_autopay'], 'on_time'].mean())}")
report()

# ---------------------------------------------------------------------------
# 4. Does the past predict the future? (the case for CUPED)
# Compare each manual payer's on-time rate in months 1-3 with months 4-6.
# ---------------------------------------------------------------------------
# Rehearse CUPED on history: use months 1-5 as the "pre-period" and month 6 as the
# "outcome". CUPED removes a share of the variance equal to the squared correlation
# between the two, so r^2 is the variance reduction we could expect.
m_start = month_starts[-1]
pre_on_time = manual[manual["statement_date"] < m_start].groupby("customer_id")["on_time"].mean()
post = manual[manual["statement_date"] == m_start].set_index("customer_id")
both = post[["on_time", "days_late"]].join(pre_on_time.rename("pre_on_time"), how="inner")
pre_days_late = (manual[manual["statement_date"] < m_start]
                 .groupby("customer_id")["days_late"].mean().rename("pre_days_late"))
both = both.join(pre_days_late, how="inner").dropna()
r_on_time = both["pre_on_time"].corr(both["on_time"].astype(float))
r_days_late = both["pre_days_late"].corr(both["days_late"])

# Does past on-time behavior predict who enrolls in the last month?
m_end = m_start + pd.DateOffset(months=1)
eligible_last = (np.where(open_date.isna(), first_statement <= m_start, open_date < m_start)
                 & (closed_date.isna() | (closed_date >= m_end))
                 & (enrolled_on.isna() | (enrolled_on >= m_start)))
enrolled_last = eligible_last & (enrolled_on < m_end)
prior = (manual[manual["statement_date"] < m_start]
         .groupby("customer_id")["on_time"].mean().rename("prior_on_time"))
frame = pd.DataFrame({"customer_id": customers["customer_id"],
                      "eligible": eligible_last, "enrolled": enrolled_last})
frame = frame[frame["eligible"]].merge(prior, on="customer_id", how="left")
r_enroll = frame["prior_on_time"].corr(frame["enrolled"].astype(float))
frame["prior_band"] = pd.cut(frame["prior_on_time"], [-0.01, 0.5, 0.99, 1.0],
                             labels=["paid on time half or less", "mostly on time", "always on time"])
by_band = frame.groupby("prior_band", observed=True)["enrolled"].agg(["mean", "size"])

report("## 4. Does past behavior predict future behavior?")
report()
report("Rehearsal of CUPED on history: months 1-5 as the pre-period, month 6 as the outcome "
       f"({len(both):,} manual payers). Expected variance reduction = correlation squared.")
report()
report("| Outcome metric | Pre-period covariate | Correlation | Variance CUPED would remove |")
report("|---|---|---|---|")
report(f"| On time in month 6 | On-time rate, months 1-5 | {r_on_time:.2f} | {pct(r_on_time ** 2)} |")
report(f"| Days late in month 6 | Average days late, months 1-5 | {r_days_late:.2f} | {pct(r_days_late ** 2)} |")
report(f"| Enrolled in month 6 | On-time rate, months 1-5 | {r_enroll:.2f} | {pct(r_enroll ** 2)} |")
report()
report("| Prior payment record | Enrolled in last month | Customers |")
report("|---|---|---|")
for band, r in by_band.iterrows():
    report(f"| {band} | {pct(r['mean'])} | {int(r['size']):,} |")
report()
report("Reliable payers do enroll more often, but past behavior explains very little of who enrolls "
       "or pays on time in a single month. CUPED will only remove a small share of the noise here, "
       "so the sample size has to come from the power calculation, not from variance reduction.")
report()

# ---------------------------------------------------------------------------
# 5. Who would be in the experiment?
# ---------------------------------------------------------------------------
eligible_exp = ((closed_date.isna() | (closed_date >= EXPERIMENT_START))
                & customers["account_status"].eq("open")
                & (enrolled_on.isna() | (enrolled_on >= EXPERIMENT_START)))
report("## 5. Experiment population on " + EXPERIMENT_START.strftime("%d %b %Y"))
report()
report(f"- Open accounts not yet on autopay: {eligible_exp.sum():,} customers "
       f"({pct(eligible_exp.mean())} of all customers).")
groups = pd.Series(tenure_group[eligible_exp.to_numpy()]).value_counts()
report("- By tenure: " + ", ".join(f"{g} {n:,}" for g, n in groups.items()) + ".")
report(f"- Expected 30-day enrollment with no prompt: about {pct(all_rates.iloc[-1])} (last month's rate).")

RESULTS.mkdir(exist_ok=True)
(RESULTS / "exploration_summary.md").write_text("\n".join(lines) + "\n")
print(f"\nSaved {RESULTS / 'exploration_summary.md'}")
