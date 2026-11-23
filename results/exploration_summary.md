# Exploration summary

## 1. Data checks

| Table | Rows | Key | Duplicate keys |
|---|---|---|---|
| customers | 1,000,000 | customer_id | 0 |
| autopay_enrollments | 453,677 | customer_id | 0 |
| statements | 5,653,528 | customer_id, statement_date | 0 |
| payments | 5,647,177 | payment_id | 28,095 |

- **Duplicate payments:** 28,095 rows (0.50%) are exact copies of another row (same payment_id). Counting them would overstate payments, so they are dropped before any analysis.
- **Missing open dates:** 10,118 customers (1.01%) have no open date, so their tenure is unknown. They stay in the data, in an 'unknown tenure' group, rather than being dropped.
- **Closed accounts:** 29,970 (3.00%) closed during the history window. They can't be in the experiment.
- **Payments without a statement:** 0. Every payment links to a statement.

- Of the customers with no open date, 932 have a first statement inside the history window, so they must be new customers. The rest stay 'unknown'.

## 2. Baseline autopay enrollment rate

Share of eligible customers who turn on autopay within the month, with no prompt.

| Month | All | New | Tenured | Unknown tenure |
|---|---|---|---|---|
| 2026-04 | 7.84% | 11.12% | 7.39% | 7.76% |
| 2026-05 | 7.87% | 11.10% | 7.35% | 7.84% |
| 2026-06 | 7.87% | 10.98% | 7.30% | 7.46% |
| 2026-07 | 7.85% | 10.97% | 7.19% | 7.86% |
| 2026-08 | 7.90% | 10.81% | 7.21% | 7.30% |
| 2026-09 | 7.96% | 10.78% | 7.19% | 8.09% |

- The overall rate ranges from 7.84% to 7.96% (average 7.88%). It is stable enough to use as the baseline in the power calculation.
- New customers enroll at about 1.5x the rate of tenured customers, so tenure is worth checking as a segment.

## 3. Payment behavior (manual payers)

- On-time rate: 89.26%
- Late but paid: 9.88%
- Missed entirely: 0.86%
- Among late payments, median days late: 8 (mean 11.9)
- Autopay customers' on-time rate: 100.00%

## 4. Does past behavior predict future behavior?

Rehearsal of CUPED on history: months 1-5 as the pre-period, month 6 as the outcome (550,163 manual payers). Expected variance reduction = correlation squared.

| Outcome metric | Pre-period covariate | Correlation | Variance CUPED would remove |
|---|---|---|---|
| On time in month 6 | On-time rate, months 1-5 | 0.17 | 2.76% |
| Days late in month 6 | Average days late, months 1-5 | 0.09 | 0.78% |
| Enrolled in month 6 | On-time rate, months 1-5 | 0.04 | 0.15% |

| Prior payment record | Enrolled in last month | Customers |
|---|---|---|
| paid on time half or less | 5.88% | 23,149 |
| mostly on time | 6.53% | 183,935 |
| always on time | 8.69% | 345,207 |

Reliable payers do enroll more often, but past behavior explains very little of who enrolls or pays on time in a single month. CUPED will only remove a small share of the noise here, so the sample size has to come from the power calculation, not from variance reduction.

## 5. Experiment population on 01 Oct 2026

- Open accounts not yet on autopay: 524,839 customers (52.48% of all customers).
- By tenure: tenured 412,530, new 107,642, unknown 4,667.
- Expected 30-day enrollment with no prompt: about 7.96% (last month's rate).
