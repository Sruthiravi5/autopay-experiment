# Running the pipeline in Databricks

Stages 5 and 6 run in Databricks Free Edition: the raw Parquet files go into a Unity Catalog volume, PySpark and Spark SQL build the metrics table, and the health checks read it back. The same scripts also run on a laptop (see the README), which is how they were tested.

You need a free Databricks account and the data generated on your computer:

```bash
python generator/generate_history.py
python generator/generate_experiment.py
```

## 1. Create a schema and a volume

1. In the left sidebar, open **Catalog**.
2. Open the **workspace** catalog and create a schema named **`autopay`**.
3. Inside `autopay`, create a volume named **`raw`**.

The scripts expect the data at `/Volumes/workspace/autopay/raw/`.

## 2. Upload the data

Open the `raw` volume and use **Upload to this volume**. Recreate this folder layout:

```
raw/
  history/            customers, autopay_enrollments, statements, payments (.parquet)
  experiment/         assignments, prompt_views, autopay_enrollments, statements,
                      payments, service_contacts (.parquet)
  experiment_broken/  assignments.parquet
```

Do not upload `data/_truth/`. Databricks is playing the role of the bank's warehouse, and the warehouse doesn't know the answers.

## 3. Bring in the code

1. In the sidebar, open **Workspace**, then **Create > Git folder**.
2. Paste `https://github.com/Sruthiravi5/autopay-experiment.git`, choose **GitHub**, and create the folder.

## 4. Run it

1. Open `pipeline/01_load.py`. It opens as a notebook because of its first line. Attach serverless compute and click **Run all**. It loads the tables, removes duplicate payments, runs `02_metrics.sql`, and saves the table `workspace.autopay.customer_metrics`.
2. Open `pipeline/03_health_checks.py` and click **Run all**. It writes `results/health_checks.md` and stops with an error if the test is not healthy.

## 5. Check it matches

The Databricks run should give the same numbers as `results/health_checks.md` in the repo: 525,047 customers, treatment 49.92% (p = 0.22), the broken copy caught, and every balance SMD under 0.01.

A quick look at the table in a SQL cell:

```sql
SELECT variant, tenure_group, COUNT(*) AS customers
FROM workspace.autopay.customer_metrics
GROUP BY variant, tenure_group
ORDER BY tenure_group, variant;
```

Free Edition limits and menu names change from time to time. If a step looks different, the [Git folders documentation](https://docs.databricks.com/aws/en/repos/git-operations-with-repos) has the current steps.
