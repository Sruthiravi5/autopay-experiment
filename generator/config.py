"""
config.py — the hidden truth of the simulated world.

Everything the generator "knows" lives in this one file. Your analysis code
(pipeline/ and stats/) must never import it: at a real bank you wouldn't know
these numbers, and the whole point of the project is to recover them from
the data. The only code allowed to read this file is generator/ and tests/.
"""
from datetime import date

SEED = 42  # same seed -> identical data for anyone who runs the generator

# ---------------------------------------------------------------------------
# Population and timeline
# ---------------------------------------------------------------------------
N_CUSTOMERS = 1_000_000            # all customers, before any eligibility filter
HISTORY_MONTHS = 6                 # months of history before the experiment
EXPERIMENT_START = date(2026, 10, 1)
DUE_DAYS_AFTER_STATEMENT = 25      # payment is due 25 days after the statement

# ---------------------------------------------------------------------------
# Customer mix
# ---------------------------------------------------------------------------
NEW_CUSTOMER_SHARE = 0.20          # opened within 12 months of EXPERIMENT_START
CLOSED_DURING_HISTORY_SHARE = 0.03 # accounts closed partway through the history
AUTOPAY_BEFORE_HISTORY_SHARE = 0.15  # already on autopay when history begins

# ---------------------------------------------------------------------------
# Payment behavior
# Each customer gets a hidden "reliability": their chance of paying on time in
# any month. It drives behavior before AND during the experiment, which is why
# past behavior predicts future behavior (the thing CUPED exploits).
# ---------------------------------------------------------------------------
RELIABILITY_BETA = (9.0, 1.0)      # Beta distribution; mean 0.90, long tail of risky customers
MEAN_DAYS_LATE = 12                # average days late, among late payments
MISSED_SHARE_OF_LATE = 0.08        # late payments that never arrive (no payment row)
MIN_PAYMENT_FLOOR = 25             # minimum payment is max($25, 2% of balance)

# ---------------------------------------------------------------------------
# Payment habit: how much of the balance a manual payer usually pays.
# Card issuers split customers into transactors (pay in full every month) and
# revolvers (pay part of the balance and carry the rest). The habit is stable,
# with a little month-to-month wobble, so past share paid predicts the next
# month well. This is the metric where CUPED should clearly help.
# ---------------------------------------------------------------------------
TRANSACTOR_SHARE = 0.35            # share of customers who usually pay in full
REVOLVER_HABIT_BETA = (2.0, 5.0)   # revolvers' usual share of balance paid; mean about 0.29
PAY_SHARE_MONTHLY_NOISE = 0.08     # month-to-month wobble around the habit
TRANSACTOR_SLIP_RATE = 0.05        # chance a transactor pays only part in a given month

# ---------------------------------------------------------------------------
# Organic autopay enrollment (no prompt)
# Monthly chance of turning on autopay = base x reliability effect x tenure effect.
# Base is tuned so the monthly rate among eligible customers is about 8%.
# Eager enrollers leave the pool each month while new customers join it,
# so the rate stays roughly flat; check that during exploration.
# ---------------------------------------------------------------------------
MONTHLY_ENROLL_BASE = 0.072
RELIABILITY_ENROLL_SLOPE = 3.0     # reliable customers are likelier to enroll
NEW_CUSTOMER_ENROLL_MULT = 1.5     # new customers are likelier to enroll

# ---------------------------------------------------------------------------
# Planted data problems (you find these on Days 3-4)
# ---------------------------------------------------------------------------
DUPLICATE_PAYMENT_RATE = 0.005     # ingestion bug: some payment rows appear twice
MISSING_OPEN_DATE_RATE = 0.01      # some customers have no open date recorded

# ---------------------------------------------------------------------------
# Experiment effects (used by generate_experiment.py)
# Lifts are added to a viewer's chance of enrolling within the 30 days.
# Novelty: customers who see the prompt in week 1 respond WEEK1_MULTIPLIER times as
# strongly as later viewers, scaled so the average lift stays at TRUE_LIFT / LIFT_NEW_CUSTOMERS.
# ---------------------------------------------------------------------------
TRUE_LIFT = 0.02                   # enrollment lift among customers who SEE the prompt
EXPOSURE_RATE = 0.70               # share of treatment who open the app and see it
LIFT_NEW_CUSTOMERS = 0.04          # stronger lift for new customers
WEEK1_MULTIPLIER = 1.8             # novelty: the effect is strongest in week 1
LATE_PAYER_CONTACT_LIFT = 0.15     # guardrail harm: past late payers who see the prompt call 15% more
SRM_BROKEN_SHARE = 0.51            # treatment share in the broken dataset only

# Customer service contacts during the 30-day test (needed for the guardrail).
BASE_CONTACT_RATE = 0.12           # average contacts per customer in 30 days
LATE_PAYER_BASE_CONTACT_MULT = 1.5 # past late payers call more even without any prompt

# Timing of prompt views and responses.
DAILY_FIRST_OPEN_PROB = 0.15       # viewers' daily chance of first opening the app; front-loads views
RESPONSE_DELAY_PROB = 0.5          # prompted enrollers sign up within a day or two of seeing it
