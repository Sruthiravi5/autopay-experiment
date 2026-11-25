# Data dictionary

All tables are Parquet files with plain `DATE` columns, so they load cleanly into pandas, Spark or Databricks. `customer_id` links every table. Row counts are from the default seed.

The analysis may read `data/history/` and `data/experiment/` only. `data/_truth/` holds the simulation's answers and is read only by the generator and the tests.

## History: 1 Apr to 30 Sep 2026 (`data/history/`)

### customers (1,000,000 rows)
One row per customer.

| Column | Type | Meaning |
|---|---|---|
| customer_id | integer | Unique customer key |
| open_date | date | Account opening date. **Missing for about 1% of customers** (known data problem) |
| credit_line | number | Credit limit in dollars |
| account_status | text | `open` or `closed` |
| closed_date | date | Closing date; empty if open |

### autopay_enrollments (about 454,000 rows)
One row per customer who turned on autopay before 1 Oct 2026. Customers with no row are not on autopay.

| Column | Type | Meaning |
|---|---|---|
| customer_id | integer | Customer key |
| enrollment_date | date | Day autopay was turned on |

### statements (about 5.65 million rows)
One row per customer per monthly statement, dated the 1st of each month.

| Column | Type | Meaning |
|---|---|---|
| customer_id | integer | Customer key |
| statement_date | date | Statement date (1st of the month) |
| due_date | date | Payment due date, 25 days after the statement |
| balance | number | Statement balance in dollars |
| min_payment_due | number | Minimum due: the larger of $25 or 2% of the balance, capped at the balance |

### payments (about 5.65 million rows)
One row per payment received against a statement. A statement with no payment was missed.

| Column | Type | Meaning |
|---|---|---|
| payment_id | integer | Payment key. **About 0.5% of rows are exact duplicates** (known ingestion bug): drop them before use |
| customer_id | integer | Customer key |
| statement_date | date | The statement this payment is for |
| payment_date | date | Day the payment arrived |
| amount | number | Amount paid in dollars |

## Experiment: 1 to 30 Oct 2026 (`data/experiment/`)

The test population is the 525,047 customers with open accounts who were not on autopay on 1 Oct 2026.

### assignments (525,047 rows)

| Column | Type | Meaning |
|---|---|---|
| customer_id | integer | Customer key, one row per customer |
| variant | text | `control` (current app) or `treatment` (app with the autopay prompt) |
| assigned_date | date | 1 Oct 2026 for everyone |

### prompt_views (about 184,000 rows)
One row per treatment customer who saw the prompt. Treatment customers with no row never opened the app during the test.

| Column | Type | Meaning |
|---|---|---|
| customer_id | integer | Customer key |
| first_view_date | date | First day the customer saw the prompt |

### autopay_enrollments (about 46,000 rows)
Autopay sign-ups during the test, from both groups.

| Column | Type | Meaning |
|---|---|---|
| customer_id | integer | Customer key |
| enrollment_date | date | Day autopay was turned on |

### statements (1,050,094 rows) and payments (about 1.05 million rows)
Same columns as the history tables, for the 1 Oct and 1 Nov 2026 statements. Autopay set up in October first takes effect on the 1 Nov statement, so payment metrics use that statement. The duplicate-payment bug is still present.

### service_contacts (about 78,000 rows)
One row per contact with customer service during the test.

| Column | Type | Meaning |
|---|---|---|
| contact_id | integer | Contact key |
| customer_id | integer | Customer key |
| contact_date | date | Day of the contact |

## Broken copy (`data/experiment_broken/`)

`assignments.parquet` only, with the same columns. An assignment bug moved about 2% of control customers into treatment, so treatment is about 51% of the test. It exists to prove that the sample ratio check catches a broken split.
