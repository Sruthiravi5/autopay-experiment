# Databricks notebook source
"""
01_load.py — load the raw tables into Spark, clean them, and build the metrics table.

Runs the same code in two places:

  Databricks   Open this file from the repo's Git folder and click Run all. It reads the
               Parquet files you uploaded to a Volume and saves `customer_metrics` as a
               table in the `workspace.autopay` schema. See docs/databricks_setup.md.

  Your laptop  python pipeline/01_load.py   (needs Java and `pip install pyspark`)
               Reads data/ and writes data/warehouse/customer_metrics/ as Parquet.

Steps
  1. Load every history and experiment table as a Spark view.
  2. Remove the duplicate payment rows found during exploration (known ingestion bug).
  3. Run 02_metrics.sql, which builds one row per test customer.
  4. Save the result and a small load log (row counts, duplicates removed).
"""
import json
import os
from pathlib import Path

from pyspark.sql import SparkSession

ON_DATABRICKS = "DATABRICKS_RUNTIME_VERSION" in os.environ

if ON_DATABRICKS:
    DATA_ROOT = "/Volumes/workspace/autopay/raw"       # where you upload the data/ folder
    SCHEMA = "workspace.autopay"
    SQL_FILE = Path("02_metrics.sql")                  # notebooks run from their own folder
    LOG_FILE = Path(f"{DATA_ROOT}/load_log.json")
    spark = SparkSession.builder.getOrCreate()
else:
    DATA_ROOT = "data"
    SQL_FILE = Path(__file__).with_name("02_metrics.sql")
    LOG_FILE = Path("results/load_log.json")
    spark = (SparkSession.builder.master("local[*]").appName("autopay")
             .config("spark.driver.memory", "4g")
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.ui.enabled", "false")
             .config("spark.ui.showConsoleProgress", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

TABLES = {
    # view name               file
    "hist_customers":         "history/customers.parquet",
    "hist_enrollments":       "history/autopay_enrollments.parquet",
    "hist_statements":        "history/statements.parquet",
    "hist_payments_raw":      "history/payments.parquet",
    "exp_assignments":        "experiment/assignments.parquet",
    "exp_prompt_views":       "experiment/prompt_views.parquet",
    "exp_enrollments":        "experiment/autopay_enrollments.parquet",
    "exp_statements":         "experiment/statements.parquet",
    "exp_payments_raw":       "experiment/payments.parquet",
    "exp_service_contacts":   "experiment/service_contacts.parquet",
}

# 1. Load
log = {"row_counts": {}}
for view, file in TABLES.items():
    df = spark.read.parquet(f"{DATA_ROOT}/{file}")
    df.createOrReplaceTempView(view)
    log["row_counts"][view] = df.count()

# 2. Clean: duplicate payments are exact copies of another row (same payment_id and values).
for prefix in ("hist", "exp"):
    raw = spark.table(f"{prefix}_payments_raw")
    clean = raw.dropDuplicates()
    clean.createOrReplaceTempView(f"{prefix}_payments")
    log[f"{prefix}_duplicate_payments_removed"] = log["row_counts"][f"{prefix}_payments_raw"] - clean.count()

# 3. Build the metrics table: run each statement in the SQL file in order.
#    Comment lines are removed first, then the text is split on semicolons.
code = "\n".join(line for line in SQL_FILE.read_text().splitlines() if not line.strip().startswith("--"))
for statement in (s.strip() for s in code.split(";")):
    if statement:
        spark.sql(statement)

metrics = spark.table("customer_metrics")
log["customer_metrics_rows"] = metrics.count()

# 4. Save
if ON_DATABRICKS:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    metrics.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SCHEMA}.customer_metrics")
    print(f"Saved table {SCHEMA}.customer_metrics")
else:
    metrics.write.mode("overwrite").parquet(f"{DATA_ROOT}/warehouse/customer_metrics")
    print(f"Saved {DATA_ROOT}/warehouse/customer_metrics/")

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_FILE.write_text(json.dumps(log, indent=2))
print(json.dumps(log, indent=2))
