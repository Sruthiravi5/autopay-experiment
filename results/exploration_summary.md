# Exploration summary

## 1. Data checks

| Table | Rows | Key | Duplicate keys |
|---|---|---|---|
| customers | 1,000,000 | customer_id | 0 |
| autopay_enrollments | 453,371 | customer_id | 0 |
| statements | 5,652,851 | customer_id, statement_date | 0 |
| payments | 5,646,221 | payment_id | 28,091 |

- **Duplicate payments:** 28,091 rows (0.50%) are exact copies of another row (same payment_id). Counting them would overstate payments, so they are dropped before any analysis.
- **Missing open dates:** 10,113 customers (1.01%) have no open date, so their tenure is unknown. They stay in the data, in an 'unknown tenure' group, rather than being dropped.
- **Closed accounts:** 30,127 (3.01%) closed during the history window. They can't be in the experiment.
- **Payments without a statement:** 0. Every payment links to a statement.

- Of the customers with no open date, 915 have a first statement inside the history window, so they must be new customers. The rest stay 'unknown'.

## 2. Baseline autopay enrollment rate

Share of eligible customers who turn on autopay within the month, with no prompt.

| Month | All | New | Tenured | Unknown tenure |
|---|---|---|---|---|
| 2026-04 | 7.78% | 11.06% | 7.34% | 7.43% |
| 2026-05 | 7.80% | 10.86% | 7.31% | 7.53% |
| 2026-06 | 7.87% | 10.91% | 7.32% | 7.47% |
| 2026-07 | 7.88% | 10.86% | 7.25% | 7.63% |
| 2026-08 | 7.92% | 10.83% | 7.23% | 7.54% |
| 2026-09 | 8.00% | 11.02% | 7.20% | 6.61% |

- The overall rate ranges from 7.78% to 8.00% (average 7.88%). It is stable enough to use as the baseline in the power calculation.
- New customers enroll at about 1.5x the rate of tenured customers, so tenure is worth checking as a segment.

## 3. Payment behavior (manual payers)

- On-time rate: 89.24%
- Late but paid: 9.89%
- Missed entirely: 0.87%
- Among late payments, median days late: 8 (mean 11.9)
- Autopay customers' on-time rate: 100.00%
- Share of balance paid: average 47.95% for manual payers, 100.00% for autopay customers.
- 31.54% of manual payers usually pay their full balance (transactors); the rest usually carry a balance (revolvers).

## 4. Does past behavior predict future behavior?

Rehearsal of CUPED on history: months 1-5 as the pre-period, month 6 as the outcome (550,582 manual payers). Expected variance reduction = correlation squared.

| Outcome metric | Pre-period covariate | Correlation | Variance CUPED would remove |
|---|---|---|---|
| On time in month 6 | On-time rate, months 1-5 | 0.17 | 2.75% |
| Days late in month 6 | Average days late, months 1-5 | 0.09 | 0.73% |
| Enrolled in month 6 | On-time rate, months 1-5 | 0.04 | 0.16% |
| Share of balance paid in month 6 | Average share paid, months 1-5 | 0.81 | 66.38% |

| Prior payment record | Enrolled in last month | Customers |
|---|---|---|
| paid on time half or less | 5.48% | 23,402 |
| mostly on time | 6.64% | 183,814 |
| always on time | 8.73% | 345,633 |

Two kinds of behavior show up. Paying on time and enrolling are mostly one-off events in a given month, so past behavior explains little of them and CUPED will barely help. Share of balance paid is a stable habit, so past behavior explains 66.38% of it and CUPED should sharply cut the noise on that metric.

## 5. Experiment population on 01 Oct 2026

- Open accounts not yet on autopay: 525,047 customers (52.50% of all customers).
- By tenure: tenured 412,653, new 107,646, unknown 4,748.
- Expected 30-day enrollment with no prompt: about 8.00% (last month's rate).
- Prior late payers (any late or missed payment in the history): 41.80% of the population.
