"""Checks that the power formulas agree with statsmodels and behave sensibly."""
import sys
from pathlib import Path

import pytest
from statsmodels.stats.power import NormalIndPower, tt_ind_solve_power
from statsmodels.stats.proportion import proportion_effectsize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stats"))
from power import cuped_sd, mde_mean, mde_proportion, n_per_arm_proportion  # noqa: E402


def test_mde_proportion_matches_statsmodels():
    p, n = 0.08, 50_000
    lift = mde_proportion(p, n)
    h = proportion_effectsize(p + lift, p)
    achieved = NormalIndPower().power(effect_size=h, nobs1=n, alpha=0.05, ratio=1)
    assert achieved == pytest.approx(0.80, abs=0.01)


def test_sample_size_textbook_case():
    # 8% -> 9% at 5% significance and 80% power needs about 12,200 per arm.
    assert 12_000 < n_per_arm_proportion(0.08, 0.01) < 12_400


def test_mde_mean_matches_t_test():
    sd, n = 0.37, 100_000
    d = mde_mean(sd, n) / sd
    achieved = tt_ind_solve_power(effect_size=d, nobs1=n, alpha=0.05, ratio=1)
    assert achieved == pytest.approx(0.80, abs=0.01)


def test_cuped_shrinks_noise_by_r_squared():
    assert cuped_sd(1.0, 0.0) == 1.0
    assert cuped_sd(1.0, 0.8) ** 2 == pytest.approx(1 - 0.64)


def test_more_customers_detect_smaller_effects():
    assert mde_proportion(0.08, 200_000) < mde_proportion(0.08, 20_000)
