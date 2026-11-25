"""Checks that the simulated experiment is built the way the design says.

Reads the generated data, so run the generators first:
    python generator/generate_history.py
    python generator/generate_experiment.py
Tests may read data/_truth/; the analysis code may not.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

EXP = Path("data/experiment")
BROKEN = Path("data/experiment_broken")
TRUTH = Path("data/_truth")

pytestmark = pytest.mark.skipif(not (EXP / "assignments.parquet").exists(),
                                reason="run the generators first")


@pytest.fixture(scope="module")
def assignments():
    return pd.read_parquet(EXP / "assignments.parquet")


def test_each_customer_assigned_once(assignments):
    assert assignments["customer_id"].is_unique
    assert set(assignments["variant"]) == {"control", "treatment"}


def test_clean_split_is_close_to_50_50(assignments):
    share = (assignments["variant"] == "treatment").mean()
    assert share == pytest.approx(0.5, abs=0.005)


def test_broken_split_is_visibly_off():
    broken = pd.read_parquet(BROKEN / "assignments.parquet")
    assert (broken["variant"] == "treatment").mean() == pytest.approx(0.51, abs=0.003)


def test_only_treatment_sees_the_prompt(assignments):
    views = pd.read_parquet(EXP / "prompt_views.parquet")
    variant = views.merge(assignments, on="customer_id")["variant"]
    assert (variant == "treatment").all()


def test_enrollments_are_in_the_test_window(assignments):
    enrollments = pd.read_parquet(EXP / "autopay_enrollments.parquet")
    dates = pd.to_datetime(enrollments["enrollment_date"])
    assert enrollments["customer_id"].isin(assignments["customer_id"]).all()
    assert dates.between("2026-10-01", "2026-10-30").all()


def test_october_autopay_pays_november_in_full():
    enrollments = pd.read_parquet(EXP / "autopay_enrollments.parquet")
    statements = pd.read_parquet(EXP / "statements.parquet")
    payments = pd.read_parquet(EXP / "payments.parquet").drop_duplicates()
    nov = statements[pd.to_datetime(statements["statement_date"]) == "2026-11-01"]
    nov = nov[nov["customer_id"].isin(enrollments["customer_id"])]
    paid = nov.merge(payments, on=["customer_id", "statement_date"])
    assert len(paid) == len(nov)
    assert (paid["amount"] == paid["balance"]).all()


def test_planted_lifts_match_config():
    truth = json.loads((TRUTH / "experiment_truth.json").read_text())
    # Viewer lift averages TRUE_LIFT (tenured) and LIFT_NEW_CUSTOMERS (new): between 2 and 4 points.
    assert 0.02 < truth["viewer_enrollment_lift"] < 0.04
    assert truth["exposure_rate"] == pytest.approx(0.70, abs=0.01)
    assert truth["viewer_lift_week1"] > truth["viewer_lift_later"]
