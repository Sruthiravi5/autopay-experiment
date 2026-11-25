-- 02_metrics.sql: one row per test customer, with everything the health checks and
-- the analysis need. Run by 01_load.py, which first creates the hist_* and exp_* views
-- and removes duplicate payments.
--
-- Metric definitions follow docs/preregistration.md. The test starts on 1 Oct 2026 and
-- lasts 30 days, so the window is 1 to 30 Oct. Payment metrics use the 1 Nov statement,
-- the first one where autopay set up in October takes effect.


-- 1. Payment outcome for every statement: was it paid on time, how late, how much.
--    Several payments on one statement are added up, and the first one sets the timing.
CREATE OR REPLACE TEMP VIEW hist_statement_outcomes AS
SELECT
    s.customer_id,
    s.statement_date,
    p.first_payment_date IS NULL                                                   AS missed,
    COALESCE(p.first_payment_date <= s.due_date, FALSE)                            AS on_time,
    CASE WHEN p.first_payment_date > s.due_date
         THEN datediff(p.first_payment_date, s.due_date) ELSE 0 END                AS days_late,
    CASE WHEN s.balance > 0
         THEN LEAST(COALESCE(p.amount_paid, 0) / s.balance, 1.0) ELSE 1.0 END     AS share_paid
FROM hist_statements s
LEFT JOIN (
    SELECT customer_id, statement_date,
           MIN(payment_date) AS first_payment_date,
           SUM(amount)       AS amount_paid
    FROM hist_payments
    GROUP BY customer_id, statement_date
) p
  ON p.customer_id = s.customer_id AND p.statement_date = s.statement_date;


CREATE OR REPLACE TEMP VIEW exp_statement_outcomes AS
SELECT
    s.customer_id,
    s.statement_date,
    p.first_payment_date IS NULL                                                   AS missed,
    COALESCE(p.first_payment_date <= s.due_date, FALSE)                            AS on_time,
    CASE WHEN p.first_payment_date > s.due_date
         THEN datediff(p.first_payment_date, s.due_date) ELSE 0 END                AS days_late,
    CASE WHEN s.balance > 0
         THEN LEAST(COALESCE(p.amount_paid, 0) / s.balance, 1.0) ELSE 1.0 END     AS share_paid
FROM exp_statements s
LEFT JOIN (
    SELECT customer_id, statement_date,
           MIN(payment_date) AS first_payment_date,
           SUM(amount)       AS amount_paid
    FROM exp_payments
    GROUP BY customer_id, statement_date
) p
  ON p.customer_id = s.customer_id AND p.statement_date = s.statement_date;


-- 2. Pre-period behavior, April to September 2026. These are the CUPED covariates and
--    the balance-check variables. Nobody in the test was on autopay yet, so every
--    history statement reflects manual paying.
CREATE OR REPLACE TEMP VIEW pre_period AS
SELECT
    customer_id,
    COUNT(*)                                     AS pre_statements,
    AVG(CAST(on_time AS DOUBLE))                 AS pre_on_time_rate,
    AVG(share_paid)                              AS pre_share_paid,
    AVG(days_late)                               AS pre_days_late,
    CAST(MAX(CAST(NOT on_time AS INT)) AS INT)   AS prior_late
FROM hist_statement_outcomes
GROUP BY customer_id;


-- 3. Tenure group as of 1 Oct. When the open date is missing, a first statement after
--    1 Apr proves the account opened recently, so the customer is new.
CREATE OR REPLACE TEMP VIEW tenure AS
SELECT
    c.customer_id,
    c.credit_line,
    CASE
        WHEN c.open_date IS NOT NULL AND datediff(DATE'2026-10-01', c.open_date) <= 365 THEN 'new'
        WHEN c.open_date IS NOT NULL                                                    THEN 'tenured'
        WHEN f.first_statement > DATE'2026-04-01'                                       THEN 'new'
        ELSE 'unknown'
    END AS tenure_group
FROM hist_customers c
LEFT JOIN (SELECT customer_id, MIN(statement_date) AS first_statement
           FROM hist_statements GROUP BY customer_id) f
  ON f.customer_id = c.customer_id;


-- 4. The customer metrics table.
CREATE OR REPLACE TEMP VIEW customer_metrics AS
SELECT
    a.customer_id,
    a.variant,
    t.tenure_group,
    COALESCE(pp.prior_late, 0)                                         AS prior_late,
    t.credit_line,

    -- pre-period (covariates)
    pp.pre_statements,
    pp.pre_on_time_rate,
    pp.pre_share_paid,
    pp.pre_days_late,

    -- exposure: treatment customers who opened the app and saw the prompt
    CAST(v.first_view_date IS NOT NULL AS INT)                        AS saw_prompt,
    v.first_view_date,

    -- primary metric: enrolled within the 30-day window
    CAST(e.enrollment_date IS NOT NULL AS INT)                        AS enrolled_30d,
    e.enrollment_date,
    CAST(FLOOR(datediff(e.enrollment_date, DATE'2026-10-01') / 7) AS INT) + 1 AS enroll_week,

    -- secondary metrics and missed-payment guardrail, on the 1 Nov statement
    nov.share_paid                                                    AS nov_share_paid,
    CAST(nov.on_time AS INT)                                          AS nov_on_time,
    CAST(nov.missed AS INT)                                           AS nov_missed,
    nov.days_late                                                     AS nov_days_late,

    -- guardrail: customer service contacts during the window
    COALESCE(sc.contacts, 0)                                          AS service_contacts
FROM exp_assignments a
LEFT JOIN tenure t      ON t.customer_id = a.customer_id
LEFT JOIN pre_period pp ON pp.customer_id = a.customer_id
LEFT JOIN exp_prompt_views v ON v.customer_id = a.customer_id
LEFT JOIN (SELECT customer_id, MIN(enrollment_date) AS enrollment_date
           FROM exp_enrollments
           WHERE enrollment_date BETWEEN DATE'2026-10-01' AND DATE'2026-10-30'
           GROUP BY customer_id) e
  ON e.customer_id = a.customer_id
LEFT JOIN (SELECT * FROM exp_statement_outcomes WHERE statement_date = DATE'2026-11-01') nov
  ON nov.customer_id = a.customer_id
LEFT JOIN (SELECT customer_id, COUNT(*) AS contacts
           FROM exp_service_contacts
           WHERE contact_date BETWEEN DATE'2026-10-01' AND DATE'2026-10-30'
           GROUP BY customer_id) sc
  ON sc.customer_id = a.customer_id;
