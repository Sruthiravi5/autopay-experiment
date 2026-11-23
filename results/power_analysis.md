# Power analysis

Inputs come from the exploration of six months of history (`results/baseline.json`). Two-sided test at 5% significance, 80% power, 50/50 split.

## Primary metric: autopay enrollment within 30 days

- Eligible population: 525,047 customers, so 262,523 per arm.
- Baseline 30-day enrollment: 8.00%.
- Smallest detectable lift (intent-to-treat): **0.21 pts** (8.00% to 8.21%).

Not everyone in treatment opens the app and sees the prompt. The ITT effect is the effect among viewers times the share who see it, so the effect among viewers must be larger to be detected. The exposure rate is unknown before launch; these are planning assumptions:

| Share of treatment who see the prompt | Smallest detectable lift among viewers |
|---|---|
| 50% | 0.42 pts |
| 70% | 0.30 pts |
| 90% | 0.23 pts |

For comparison, customers needed per arm to detect a given ITT lift:

| ITT lift | Customers per arm |
|---|---|
| 0.25 pts | 187,550 |
| 0.50 pts | 47,536 |
| 1.00 pts | 12,204 |

A 1-point lift needs far fewer customers than are available. The full population is still used because the planned segments and the guardrails need it (below).

## Planned segments

| Segment | Share of population | Per arm | Smallest detectable lift |
|---|---|---|---|
| New customers (opened in the last 12 months) | 20.5% | 53,822 | 0.47 pts |
| Prior late payers (any late or missed payment in history) | 41.8% | 109,730 | 0.33 pts |

The segment estimates are planned in advance, not searched for after the results are in.

## Secondary metric: share of balance paid, with and without CUPED

- Average share paid 48.1%, standard deviation 0.374.
- Correlation with the pre-period average: r = 0.81, so CUPED removes 66% of the variance.

| | Standard deviation | Smallest detectable difference |
|---|---|---|
| Without CUPED | 0.374 | 0.29 pts |
| With CUPED | 0.217 | 0.17 pts |

CUPED is worth the same as running the test on 3.0x as many customers.

On-time payment, by contrast, has r = 0.17, so CUPED removes only 2.8% of its variance. Enrollment: 0.16%.

