"""
srm.py — sample ratio mismatch: did the split come out the way it was designed?

With a 50/50 design, random chance makes the two groups slightly different in size,
but only slightly. A chi-square test asks whether the observed split is too far from
50/50 to be chance. If it is, something went wrong in assignment or logging (a bug,
a filter applied to one group, lost data), and every result after that is suspect.

The usual threshold is p < 0.001, much stricter than 0.05: with large samples you only
want to stop the analysis for a real problem, not for ordinary noise.
"""
from scipy.stats import chisquare

SRM_ALPHA = 0.001


def srm_test(n_control, n_treatment, expected_treatment_share=0.5, alpha=SRM_ALPHA):
    """Chi-square test of the observed split against the designed one.

    Returns a dict with the counts, the observed treatment share, the p-value, and
    `passed` (True when there is no evidence of a mismatch).
    """
    total = n_control + n_treatment
    expected = [total * (1 - expected_treatment_share), total * expected_treatment_share]
    result = chisquare([n_control, n_treatment], f_exp=expected)
    return {
        "n_control": int(n_control),
        "n_treatment": int(n_treatment),
        "treatment_share": n_treatment / total,
        "chi2": float(result.statistic),
        "p_value": float(result.pvalue),
        "passed": bool(result.pvalue >= alpha),
    }


def srm_from_labels(variants, treatment_label="treatment", **kwargs):
    """srm_test on a column of group labels (e.g. a pandas Series of 'control'/'treatment')."""
    n_treatment = int((variants == treatment_label).sum())
    return srm_test(len(variants) - n_treatment, n_treatment, **kwargs)
