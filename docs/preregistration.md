# Preregistration: in-app autopay prompt

**Status:** locked. Written on 23 Nov 2026, before the experiment generator existed and before any experiment data was created. In the simulated timeline the test launches on 1 Oct 2026. Any change after this point is listed under *Deviations* at the end, with the reason.

## 1. Question

Does showing cardholders an in-app prompt to turn on autopay increase autopay enrollment, and does it improve how they pay without causing harm?

- **H0:** the prompt does not change 30-day autopay enrollment.
- **H1:** the prompt changes 30-day autopay enrollment (two-sided test).

## 2. Design

| Item | Plan |
|---|---|
| Unit of randomization | Customer (all their sessions see the same experience) |
| Population | Open accounts not on autopay on 1 Oct 2026: about 525,000 customers |
| Split | 50% control (current app), 50% treatment (app with prompt) |
| Assignment | Random, fixed seed, recorded before launch |
| Duration | 30 days, 1 to 30 Oct 2026. Fixed horizon: no early stopping and no looking at results before day 30 |
| Treatment | A prompt to turn on autopay, shown when the customer opens the app |

Not everyone in treatment opens the app, so some never see the prompt. Control customers cannot see it.

## 3. Metrics

| Role | Metric | Definition |
|---|---|---|
| **Primary** | Autopay enrollment | Enrolled within 30 days of 1 Oct (yes/no) |
| Secondary | Share of balance paid | Amount paid ÷ statement balance on the 1 Nov statement, capped at 1 |
| Secondary | On-time payment | Paid on or before the due date of the 1 Nov statement |
| Guardrail | Customer service contacts | Contacts per customer during the 30 days |
| Guardrail | Missed payments | No payment at all on the 1 Nov statement |

Payment metrics use the 1 Nov statement because it is the first one where a new autopay enrollment takes effect. All metrics are measured on every assigned customer, including those who never saw the prompt.

## 4. Analysis plan

1. **Health checks first.** Sample ratio mismatch (chi-square test of the 50/50 split): if p < 0.001, stop and investigate before reading any result. Also check that the two groups match on pre-period behavior (standardized differences under 0.1).
2. **Primary effect (intent-to-treat).** Difference in 30-day enrollment between treatment and control, with a 95% confidence interval.
3. **Effect among viewers.** Intent-to-treat effect divided by the share of treatment who saw the prompt (complier average causal effect). Valid because control cannot see the prompt.
4. **Secondary metrics.** Difference in means, with CUPED. The pre-period covariate is each customer's average from April to September 2026. Holm correction across the secondary metrics.
5. **Guardrails.** One-sided non-inferiority tests. Contacts must not rise by more than 5% relative to control; missed payments must not rise by more than 0.10 percentage points.
6. **Planned segments.** New vs. tenured customers, and prior late payers (any late or missed payment in the history) vs. others. Each reported with a confidence interval and a test of whether the effect differs between the groups. No other segments will be treated as findings.
7. **Novelty check.** Enrollment effect by week of the test.

## 5. Power

From `results/power_analysis.md`, at 5% significance and 80% power with about 262,500 customers per arm:

- Primary: the smallest detectable intent-to-treat lift is **0.21 points** (8.00% to 8.21%).
- Segments: 0.47 points for new customers, 0.33 points for prior late payers.
- Share of balance paid: 0.29 points without CUPED, 0.17 points with CUPED (r = 0.81).

## 6. Decision rule

| Result | Decision |
|---|---|
| Primary lift significant and positive, all guardrails pass | Ship to all eligible customers |
| Primary lift positive, but a guardrail fails in one planned segment only | Ship to everyone except that segment, and investigate |
| Primary lift not significant, or a guardrail fails overall | Do not ship |

A statistically significant lift smaller than 0.5 points is reported, but shipping it is a business judgment, since it may not cover the cost of building and maintaining the prompt.

## 7. Validation of the method

Before the real analysis is trusted, the pipeline is checked on simulated data:

- **A/A tests:** about 500 runs with no true effect. The false-positive rate should be close to 5%.
- **Recovery test:** with a known planted effect, the estimate's 95% interval should contain the true value about 95% of the time.
- **Broken split:** a dataset with a deliberate 51/49 assignment bug must fail the sample ratio check.

## Deviations

None so far.
