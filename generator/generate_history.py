"""
generate_history.py — builds the 6 months of history an analyst would pull from
the warehouse before designing the experiment.

Run from the repo root:
    python generator/generate_history.py

Writes:
    data/history/customers.parquet            one row per customer
    data/history/autopay_enrollments.parquet  one row per autopay sign-up
    data/history/statements.parquet           one row per customer per month
    data/history/payments.parquet             one row per payment received
    data/_truth/customer_traits.parquet       the generator's secret; NEVER use in analysis

The data is simulated, but built like real card data: payments link to
statements, autopay status has to be worked out from enrollment dates, and a
few realistic data problems are planted for you to find while exploring.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import config as cfg

OUT_HISTORY = Path("data/history")
OUT_TRUTH = Path("data/_truth")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def random_dates(rng, start, end):
    """One random date per row, uniformly between start (inclusive) and end (exclusive).
    start and end are arrays (or scalars) of pandas Timestamps."""
    start = pd.to_datetime(start)
    end = pd.to_datetime(end)
    span_days = np.asarray((end - start) / pd.Timedelta(days=1), dtype=float)
    offsets = np.floor(rng.random(len(span_days)) * span_days).astype("int64")
    return start + pd.to_timedelta(offsets, unit="D")


def save(df, path):
    """Write Parquet with plain DATE columns (no time part), which Spark reads cleanly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    fields = [pa.field(f.name, pa.date32()) if pa.types.is_timestamp(f.type) else f
              for f in table.schema]
    pq.write_table(table.cast(pa.schema(fields)), path)
    print(f"  wrote {path}  ({len(df):,} rows)")


# ---------------------------------------------------------------------------
# 1. Customers and their hidden traits
# ---------------------------------------------------------------------------
def make_customers(rng, history_start, exp_start):
    n = cfg.N_CUSTOMERS
    customer_id = np.arange(n, dtype="int64") + 10_000_001

    # Tenure: new customers opened in the last year; everyone else 1-15 years ago.
    # New customers start at 31 days so each has at least one statement.
    is_new = rng.random(n) < cfg.NEW_CUSTOMER_SHARE
    days_open = np.where(is_new,
                         rng.integers(31, 366, n),
                         rng.integers(366, 15 * 365, n))
    open_date = exp_start - pd.to_timedelta(days_open, unit="D")

    # Credit line: right-skewed, like real limits, rounded to $100.
    credit_line = np.clip(np.round(rng.lognormal(np.log(5000), 0.6, n) / 100) * 100, 500, 30_000)

    # Hidden reliability: chance of paying on time in a given month.
    reliability = rng.beta(*cfg.RELIABILITY_BETA, n)

    # Hidden monthly chance of turning on autopay without any prompt.
    # Reliable customers and new customers are more likely to enroll.
    centered = reliability - reliability.mean()
    enroll_propensity = (cfg.MONTHLY_ENROLL_BASE
                         * np.exp(cfg.RELIABILITY_ENROLL_SLOPE * centered)
                         * np.where(is_new, cfg.NEW_CUSTOMER_ENROLL_MULT, 1.0))
    enroll_propensity = np.clip(enroll_propensity, 0, 0.9)

    # Some accounts close partway through the history window.
    is_closed = rng.random(n) < cfg.CLOSED_DURING_HISTORY_SHARE
    close_from = pd.Series(open_date + pd.Timedelta(days=1)).clip(lower=history_start)
    closed_date = pd.Series(random_dates(rng, close_from, exp_start)).where(is_closed)

    customers = pd.DataFrame({
        "customer_id": customer_id,
        "open_date": open_date,
        "credit_line": credit_line,
        "account_status": np.where(is_closed, "closed", "open"),
        "closed_date": closed_date,
    })
    truth = pd.DataFrame({
        "customer_id": customer_id,
        "reliability": reliability,
        "enroll_propensity": enroll_propensity,
        "is_new": is_new,
        "true_open_date": open_date,
    })
    return customers, truth


# ---------------------------------------------------------------------------
# 2. Autopay enrollments (before and during the history window)
# ---------------------------------------------------------------------------
def make_enrollments(rng, customers, truth, history_start, month_starts):
    n = len(customers)
    open_date = pd.to_datetime(customers["open_date"]).to_numpy()
    closed_date = pd.to_datetime(customers["closed_date"]).to_numpy()
    reliability = truth["reliability"].to_numpy()
    propensity = truth["enroll_propensity"].to_numpy()

    enrolled_on = np.full(n, np.datetime64("NaT", "ns"))

    # Already on autopay before the history begins (more likely if reliable).
    p_before = np.clip(cfg.AUTOPAY_BEFORE_HISTORY_SHARE
                       * np.exp(cfg.RELIABILITY_ENROLL_SLOPE * (reliability - reliability.mean())), 0, 1)
    before = (rng.random(n) < p_before) & (open_date < np.datetime64(history_start))
    idx = np.flatnonzero(before)
    enrolled_on[idx] = random_dates(rng, open_date[idx], np.full(len(idx), history_start))

    # Organic enrollment, month by month. Only customers open for the whole month
    # and not yet on autopay can enroll.
    for m_start in month_starts:
        m_end = m_start + pd.DateOffset(months=1)
        at_risk = (np.isnat(enrolled_on)
                   & (open_date < np.datetime64(m_start))
                   & (np.isnat(closed_date) | (closed_date >= np.datetime64(m_end))))
        enrolls = at_risk & (rng.random(n) < propensity)
        idx = np.flatnonzero(enrolls)
        enrolled_on[idx] = random_dates(rng, np.full(len(idx), m_start), np.full(len(idx), m_end))

    has = ~np.isnat(enrolled_on)
    enrollments = pd.DataFrame({
        "customer_id": customers["customer_id"].to_numpy()[has],
        "enrollment_date": enrolled_on[has],
    })
    return enrollments, enrolled_on


# ---------------------------------------------------------------------------
# 3. Statements and payments
# ---------------------------------------------------------------------------
def make_statements_and_payments(rng, customers, truth, enrolled_on, month_starts):
    open_date = pd.to_datetime(customers["open_date"]).to_numpy()
    closed_date = pd.to_datetime(customers["closed_date"]).to_numpy()
    credit_line = customers["credit_line"].to_numpy()
    reliability = truth["reliability"].to_numpy()
    ids = customers["customer_id"].to_numpy()

    statements, payments = [], []
    for statement_date in month_starts:
        sd = np.datetime64(statement_date)
        # A statement exists if the account was open on the statement date.
        has_stmt = (open_date < sd) & (np.isnat(closed_date) | (closed_date >= sd))
        idx = np.flatnonzero(has_stmt)
        k = len(idx)

        due_date = statement_date + pd.Timedelta(days=cfg.DUE_DAYS_AFTER_STATEMENT)
        balance = np.round(credit_line[idx] * rng.beta(2, 5, k), 2)
        min_due = np.minimum(np.maximum(cfg.MIN_PAYMENT_FLOOR, np.round(0.02 * balance, 2)), balance)

        statements.append(pd.DataFrame({
            "customer_id": ids[idx],
            "statement_date": statement_date,
            "due_date": due_date,
            "balance": balance,
            "min_payment_due": min_due,
        }))

        # Autopay (enrolled before this statement) always pays the full balance on the due date.
        on_autopay = ~np.isnat(enrolled_on[idx]) & (enrolled_on[idx] < sd)
        # Everyone else pays on time with probability = their reliability.
        on_time = on_autopay | (rng.random(k) < reliability[idx])
        late = ~on_time
        missed = late & (rng.random(k) < cfg.MISSED_SHARE_OF_LATE)  # no payment at all

        # Payment timing: up to 15 days early if on time; 1-59 days late otherwise.
        days_early = np.where(on_autopay, 0, rng.integers(0, 16, k))
        days_late = np.clip(rng.geometric(1 / cfg.MEAN_DAYS_LATE, k), 1, 59)
        offset = np.where(on_time, -days_early, days_late)

        # Amount: autopay pays in full; manual on-time payers mix full, minimum and in-between;
        # late payers pay the minimum.
        u = rng.random(k)
        partial = min_due + rng.random(k) * (balance - min_due)
        manual_amount = np.where(u < 0.4, balance, np.where(u < 0.7, min_due, partial))
        amount = np.round(np.where(on_autopay, balance, np.where(late, min_due, manual_amount)), 2)

        paid = ~missed
        payments.append(pd.DataFrame({
            "customer_id": ids[idx][paid],
            "statement_date": statement_date,
            "payment_date": due_date + pd.to_timedelta(offset[paid], unit="D"),
            "amount": amount[paid],
        }))

    statements = pd.concat(statements, ignore_index=True)
    payments = pd.concat(payments, ignore_index=True)
    payments.insert(0, "payment_id", np.arange(len(payments), dtype="int64") + 1)
    return statements, payments


# ---------------------------------------------------------------------------
# 4. Plant the data problems an analyst should catch
# ---------------------------------------------------------------------------
def add_mess(rng, customers, payments):
    # Ingestion bug: a small share of payment rows are loaded twice.
    dup = payments.sample(frac=cfg.DUPLICATE_PAYMENT_RATE, random_state=cfg.SEED)
    payments = (pd.concat([payments, dup], ignore_index=True)
                .sort_values(["payment_date", "payment_id"], kind="stable")  # load order, like a real table
                .reset_index(drop=True))

    # Missing values: some customers have no open date recorded.
    customers = customers.copy()
    missing = rng.random(len(customers)) < cfg.MISSING_OPEN_DATE_RATE
    customers.loc[missing, "open_date"] = pd.NaT
    return customers, payments


# ---------------------------------------------------------------------------
def main():
    rng = np.random.default_rng(cfg.SEED)
    exp_start = pd.Timestamp(cfg.EXPERIMENT_START)
    history_start = exp_start - pd.DateOffset(months=cfg.HISTORY_MONTHS)
    month_starts = pd.date_range(history_start, periods=cfg.HISTORY_MONTHS, freq="MS")

    print(f"Generating {cfg.N_CUSTOMERS:,} customers, history {history_start.date()} to {exp_start.date()}")
    customers, truth = make_customers(rng, history_start, exp_start)
    enrollments, enrolled_on = make_enrollments(rng, customers, truth, history_start, month_starts)
    statements, payments = make_statements_and_payments(rng, customers, truth, enrolled_on, month_starts)
    customers, payments = add_mess(rng, customers, payments)

    print("Saving:")
    save(customers, OUT_HISTORY / "customers.parquet")
    save(enrollments, OUT_HISTORY / "autopay_enrollments.parquet")
    save(statements, OUT_HISTORY / "statements.parquet")
    save(payments, OUT_HISTORY / "payments.parquet")
    save(truth, OUT_TRUTH / "customer_traits.parquet")
    print("Done. Treat data/history/ as data you were handed; don't peek at data/_truth/.")


if __name__ == "__main__":
    main()
