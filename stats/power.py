"""
power.py — how big an effect can this experiment reliably detect?

The functions are general. Running the file uses the baseline numbers measured
during exploration (results/baseline.json) and writes results/power_analysis.md.

    python stats/power.py

Terms
- MDE (minimum detectable effect): the smallest true effect the test would detect
  80% of the time at a 5% false-positive rate. Smaller is better.
- Intent-to-treat (ITT): compare everyone assigned to treatment with everyone in
  control, whether or not they saw the prompt. Unbiased, but diluted by customers
  who never opened the app.
- CUPED: subtract the part of each customer's outcome that their pre-experiment
  behavior predicts. With correlation r, the noise (variance) falls by r^2.
"""
import json
from pathlib import Path

import numpy as np
from scipy.stats import norm
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

ALPHA = 0.05
POWER = 0.80


def z_total(alpha=ALPHA, power=POWER):
    """z for a two-sided test at alpha plus z for the chosen power."""
    return norm.ppf(1 - alpha / 2) + norm.ppf(power)


def mde_proportion(p, n_per_arm, alpha=ALPHA, power=POWER):
    """Smallest absolute lift in a rate (e.g. 8% -> 8% + MDE) the test can detect.

    Solves for the effect size on the arcsine scale (Cohen's h), which accounts for the
    treatment arm's rate being a little higher than control's, then converts back to a rate.
    """
    h = NormalIndPower().solve_power(nobs1=n_per_arm, alpha=alpha, power=power, ratio=1)
    p_treat = np.sin(np.arcsin(np.sqrt(p)) + h / 2) ** 2
    return p_treat - p


def n_per_arm_proportion(p, lift, alpha=ALPHA, power=POWER):
    """Customers needed per arm to detect an absolute lift from rate p."""
    h = proportion_effectsize(p + lift, p)
    return int(np.ceil(NormalIndPower().solve_power(effect_size=h, alpha=alpha, power=power, ratio=1)))


def mde_mean(sd, n_per_arm, alpha=ALPHA, power=POWER):
    """Smallest difference in means the test can detect, for an outcome with standard deviation sd."""
    return z_total(alpha, power) * sd * np.sqrt(2 / n_per_arm)


def cuped_sd(sd, r):
    """Standard deviation left after CUPED, given correlation r with the pre-period covariate."""
    return sd * np.sqrt(1 - r ** 2)


def pts(x):
    return f"{100 * x:.2f} pts"


def main():
    b = json.loads(Path("results/baseline.json").read_text())
    n_arm = int(b["population"]) // 2
    p = b["enroll_rate_monthly"]

    out = ["# Power analysis", ""]
    out += [f"Inputs come from the exploration of six months of history (`results/baseline.json`). "
            f"Two-sided test at {ALPHA:.0%} significance, {POWER:.0%} power, 50/50 split.", ""]

    # 1. Primary metric: 30-day enrollment, intent-to-treat
    mde_itt = mde_proportion(p, n_arm)
    out += ["## Primary metric: autopay enrollment within 30 days", "",
            f"- Eligible population: {int(b['population']):,} customers, so {n_arm:,} per arm.",
            f"- Baseline 30-day enrollment: {p:.2%}.",
            f"- Smallest detectable lift (intent-to-treat): **{pts(mde_itt)}** "
            f"({p:.2%} to {p + mde_itt:.2%}).", ""]

    # Not everyone assigned to treatment will see the prompt, which dilutes the ITT effect.
    out += ["Not everyone in treatment opens the app and sees the prompt. The ITT effect is the effect "
            "among viewers times the share who see it, so the effect among viewers must be larger to be "
            "detected. The exposure rate is unknown before launch; these are planning assumptions:", "",
            "| Share of treatment who see the prompt | Smallest detectable lift among viewers |",
            "|---|---|"]
    for exposure in (0.5, 0.7, 0.9):
        out.append(f"| {exposure:.0%} | {pts(mde_itt / exposure)} |")
    out.append("")

    # How many customers would a smaller test need?
    out += ["For comparison, customers needed per arm to detect a given ITT lift:", "",
            "| ITT lift | Customers per arm |", "|---|---|"]
    for lift in (0.0025, 0.005, 0.01):
        out.append(f"| {pts(lift)} | {n_per_arm_proportion(p, lift):,} |")
    out += ["", "A 1-point lift needs far fewer customers than are available. The full population is still "
            "used because the planned segments and the guardrails need it (below).", ""]

    # 2. Segments
    out += ["## Planned segments", "", "| Segment | Share of population | Per arm | Smallest detectable lift |",
            "|---|---|---|---|"]
    for name, share in (("New customers (opened in the last 12 months)", b["share_new"]),
                        ("Prior late payers (any late or missed payment in history)", b["share_prior_late"])):
        n_seg = int(n_arm * share)
        out.append(f"| {name} | {share:.1%} | {n_seg:,} | {pts(mde_proportion(p, n_seg))} |")
    out += ["", "The segment estimates are planned in advance, not searched for after the results are in.", ""]

    # 3. Secondary metric with and without CUPED
    sd, r = b["share_paid_sd"], b["r_share_paid"]
    sd_c = cuped_sd(sd, r)
    raw, adj = mde_mean(sd, n_arm), mde_mean(sd_c, n_arm)
    out += ["## Secondary metric: share of balance paid, with and without CUPED", "",
            f"- Average share paid {b['share_paid_mean']:.1%}, standard deviation {sd:.3f}.",
            f"- Correlation with the pre-period average: r = {r:.2f}, so CUPED removes {r ** 2:.0%} of the variance.",
            "", "| | Standard deviation | Smallest detectable difference |", "|---|---|---|",
            f"| Without CUPED | {sd:.3f} | {pts(raw)} |",
            f"| With CUPED | {sd_c:.3f} | {pts(adj)} |", "",
            f"CUPED is worth the same as running the test on {(sd / sd_c) ** 2:.1f}x as many customers.", "",
            f"On-time payment, by contrast, has r = {b['r_on_time']:.2f}, so CUPED removes only "
            f"{b['r_on_time'] ** 2:.1%} of its variance. Enrollment: {b['r_enroll'] ** 2:.2%}.", ""]

    Path("results/power_analysis.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
