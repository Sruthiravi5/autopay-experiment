"""
balance.py — do the two groups look alike before the test started?

Randomization should make control and treatment similar on everything measured
before the test: payment history, credit line, tenure. A standardized mean difference
(SMD) puts every variable on the same scale:

    SMD = (mean_treatment - mean_control) / pooled standard deviation

The common rule of thumb: |SMD| < 0.1 means the groups are balanced on that variable.
Unlike a p-value, SMD does not shrink just because the sample is large, so it measures
how big an imbalance is, not merely whether one exists.
"""
import numpy as np
import pandas as pd

SMD_THRESHOLD = 0.1


def smd(treatment_values, control_values):
    """Standardized mean difference between two groups (works for 0/1 flags too)."""
    t = np.asarray(treatment_values, dtype=float)
    c = np.asarray(control_values, dtype=float)
    t, c = t[~np.isnan(t)], c[~np.isnan(c)]
    pooled_sd = np.sqrt((t.var(ddof=1) + c.var(ddof=1)) / 2)
    if pooled_sd == 0:
        return 0.0
    return float((t.mean() - c.mean()) / pooled_sd)


def balance_table(df, group_col, covariates, treatment_label="treatment", threshold=SMD_THRESHOLD):
    """One row per covariate: group means, SMD, and whether it is within the threshold."""
    is_treat = df[group_col] == treatment_label
    rows = []
    for col in covariates:
        t, c = df.loc[is_treat, col], df.loc[~is_treat, col]
        value = smd(t, c)
        rows.append({"covariate": col, "mean_control": float(c.mean()), "mean_treatment": float(t.mean()),
                     "smd": value, "balanced": abs(value) < threshold})
    return pd.DataFrame(rows)
