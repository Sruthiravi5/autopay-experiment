# Health checks

**Healthy.** Every check passed, and the broken copy was caught. The test can go to analysis.

| Check | Result | Detail |
|---|---|---|
| Sample ratio, all customers | Pass | treatment 49.92%, p = 0.22 |
| Sample ratio, within each planned segment | Pass | 5 segments, smallest p = 0.22 |
| Broken 51/49 copy is detected | Caught, as expected | treatment 50.91%, p = 9.1e-40 |
| Groups balanced before the test | Pass | largest |SMD| = 0.003 (limit 0.1) |
| No control customer saw the prompt | Pass | 0 control views |
| Share of treatment who saw the prompt | Recorded | 70.2% |
| Data integrity | Pass | 4 of 4 checks pass |

## 1. Sample ratio mismatch

A chi-square test of the observed split against 50/50. The test fails when p < 0.001: strict, because with 525,000 customers only a real problem should stop the analysis.

| Group | Control | Treatment | Treatment share | p-value | Result |
|---|---|---|---|---|---|
| All customers | 262,967 | 262,080 | 49.92% | 0.221 | Pass |
| Tenure: new | 53,846 | 53,800 | 49.98% | 0.888 | Pass |
| Tenure: tenured | 206,718 | 205,935 | 49.91% | 0.223 | Pass |
| Tenure: unknown | 2,403 | 2,345 | 49.39% | 0.400 | Pass |
| Prior late payers | 109,960 | 109,502 | 49.90% | 0.328 | Pass |
| No late payments | 153,007 | 152,578 | 49.93% | 0.438 | Pass |

Checking within segments catches bugs that hit only one group of customers, which an overall check can hide.

## 2. Proof the check works

The same test on a copy with a deliberate assignment bug, where about 2% of control customers were moved into treatment:

- Control 257,742, treatment 267,305 (50.91%).
- p = 9.1e-40, far below 0.001, so the check stops the analysis.

A 51%/49% split looks harmless by eye. At this scale it is about 13 standard deviations from 50/50, so it cannot be chance.

## 3. Balance before the test

Standardized mean difference (SMD) between treatment and control on behavior measured before 1 Oct. Balanced when |SMD| < 0.1.

| Variable | Control | Treatment | SMD | Result |
|---|---|---|---|---|
| On-time rate, Apr to Sep | 0.886 | 0.886 | +0.0005 | Pass |
| Share of balance paid, Apr to Sep | 0.476 | 0.477 | +0.0022 | Pass |
| Average days late, Apr to Sep | 1.248 | 1.250 | +0.0009 | Pass |
| Statements in history | 5.611 | 5.608 | -0.0027 | Pass |
| Credit line ($) | 5,983 | 5,977 | -0.0015 | Pass |
| Prior late payer | 0.418 | 0.418 | -0.0007 | Pass |
| New customer | 0.205 | 0.205 | +0.0013 | Pass |

These are also the variables the analysis uses for CUPED, so balance here matters twice.

## 4. Exposure

- Control customers who saw the prompt: 0 (must be zero).
- Treatment customers who saw it: 70.2%. The rest never opened the app during the test. The analysis reports the effect on everyone assigned (intent-to-treat) and divides by this share for the effect among viewers.

| Week of first view | Share of viewers |
|---|---|
| Week 1 | 67.9% |
| Week 2 | 21.8% |
| Week 3 | 7.0% |
| Week 4 | 2.2% |
| Week 5 (days 29-30) | 1.1% |

Most customers see the prompt in week 1, so any novelty effect will show up early. The analysis checks the effect week by week.

## 5. Data integrity

- One row per customer: yes
- Every assigned customer has a metrics row: yes
- No missing values in metrics: yes
- Enrollments fall inside the 30-day window: yes
- Duplicate payments removed before building metrics: 28,091 in history and 5,204 during the test (the ingestion bug found in exploration is still running).

