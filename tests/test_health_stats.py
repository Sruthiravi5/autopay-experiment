"""Checks for the sample ratio mismatch test and the balance check."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stats"))
from balance import balance_table, smd  # noqa: E402
from srm import srm_from_labels, srm_test  # noqa: E402


def test_exact_split_passes():
    result = srm_test(50_000, 50_000)
    assert result["passed"] and result["p_value"] == pytest.approx(1.0)


def test_51_49_split_fails_at_scale():
    assert not srm_test(257_000, 268_000)["passed"]


def test_random_splits_rarely_fail():
    # With honest random assignment, p < 0.001 should happen about 0.1% of the time.
    rng = np.random.default_rng(0)
    fails = sum(not srm_test(*np.bincount(rng.random(10_000) < 0.5, minlength=2))["passed"]
                for _ in range(2_000))
    assert fails <= 10


def test_unequal_design_is_respected():
    # A 90/10 design with a 90/10 result is healthy.
    assert srm_test(90_000, 10_000, expected_treatment_share=0.1)["passed"]


def test_srm_from_labels_counts_correctly():
    labels = pd.Series(["treatment"] * 60 + ["control"] * 40)
    result = srm_from_labels(labels)
    assert (result["n_control"], result["n_treatment"]) == (40, 60)


def test_smd_of_identical_groups_is_zero():
    x = np.arange(100.0)
    assert smd(x, x) == 0.0


def test_smd_detects_a_one_sd_shift():
    rng = np.random.default_rng(1)
    assert smd(rng.normal(1, 1, 50_000), rng.normal(0, 1, 50_000)) == pytest.approx(1.0, abs=0.03)


def test_balance_table_flags_imbalance():
    df = pd.DataFrame({"variant": ["treatment"] * 4 + ["control"] * 4,
                       "same": [1, 2, 3, 4, 1, 2, 3, 4],
                       "shifted": [10, 11, 12, 13, 1, 2, 3, 4]})
    table = balance_table(df, "variant", ["same", "shifted"]).set_index("covariate")
    assert table.loc["same", "balanced"] and not table.loc["shifted", "balanced"]
