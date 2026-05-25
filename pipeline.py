import sqlite3
import pandas as pd
import logging
from pathlib import Path

# -------------------------
# LOGGING CONFIG
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "commercial_insurance.db"
CSV_PATH = BASE_DIR / "small_commercial_underwriting_raw.csv"
SILVER_SQL_PATH = BASE_DIR / "bronze_to_silver.sql"
GOLD_SQL_PATH = BASE_DIR / "silver_to_gold.sql"

# -------------------------
# TASKS
# -------------------------

def ingest_raw(conn, csv_path=CSV_PATH):
    logging.info("Step 1: Starting CSV ingestion into staging_raw")

    try:
        df = pd.read_csv(csv_path)

        logging.info(f"CSV loaded successfully | rows={len(df)} | columns={len(df.columns)}")

        df.to_sql(
            "staging_raw",
            conn,
            if_exists="replace",
            index=False
        )

        logging.info("Step 1 complete: staging_raw table created")

    except Exception as e:
        logging.exception(f"Step 1 failed: ingestion error - {e}")
        raise


def run_silver_sql(conn, sql_path=SILVER_SQL_PATH):
    logging.info("Step 2: Starting silver transformation SQL execution")

    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()

        cursor = conn.cursor()
        cursor.executescript(sql)
        conn.commit()

        logging.info("Step 2 complete: silver_customers table created")

    except Exception as e:
        logging.exception(f"Step 2 failed: SQL execution error - {e}")
        raise

def run_gold_sql(conn, sql_path=GOLD_SQL_PATH):
    logging.info("Step 3: Starting gold transformation SQL execution")

    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()

        cursor = conn.cursor()
        cursor.executescript(sql)
        conn.commit()

        logging.info("Step 3 complete: gold_customers table created")

    except Exception as e:
        logging.exception(f"Step 3 failed: SQL execution error - {e}")
        raise

def validate(conn):
    logging.info("Step 4: Running validation checks")

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM staging_raw")
        raw_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM silver_customers")
        silver_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM gold_customers")
        gold_count = cursor.fetchone()[0]

        logging.info(f"Row counts | raw={raw_count} | silver={silver_count} | gold={gold_count}")

        if silver_count == 0:
            raise Exception("Silver table is empty")
        
        if gold_count == 0:
            raise Exception("Gold table is empty")

        # -------------------------
        # NULL CHECKS
        # -------------------------

        cursor.execute("""
            SELECT COUNT(*)
            FROM gold_customers
            WHERE payroll_per_employee IS NULL
        """)

        null_payroll_metric = cursor.fetchone()[0]

        logging.info(
            f"Gold validation | null payroll_per_employee={null_payroll_metric}"
        )

        # -------------------------
        # NEGATIVE VALUE CHECKS
        # -------------------------

        cursor.execute("""
            SELECT COUNT(*)
            FROM gold_customers
            WHERE payroll_per_employee < 0
               OR payroll_to_revenue_ratio < 0
        """)

        negative_metric_count = cursor.fetchone()[0]

        logging.info(
            f"Gold validation | negative metric rows={negative_metric_count}"
        )

        if negative_metric_count > 0:
            raise Exception(
                f"Gold validation failed: {negative_metric_count} negative metric rows found"
            )

        # -------------------------
        # RATIO SANITY CHECK
        # -------------------------

        cursor.execute("""
            SELECT COUNT(*)
            FROM gold_customers
            WHERE payroll_to_revenue_ratio > 10
        """)

        extreme_ratio_count = cursor.fetchone()[0]

        logging.info(
            f"Gold validation | extreme payroll_to_revenue_ratio rows={extreme_ratio_count}"
        )

        logging.info("Step 4 complete: validation passed")

    except Exception as e:
        logging.exception(f"Step 4 failed: validation error - {e}")
        raise


# -------------------------
# PIPELINE RUNNER (DAG-LIKE)
# -------------------------

def run_pipeline(db_path=DB_PATH):
    logging.info("PIPELINE STARTED")

    conn = sqlite3.connect(db_path)

    try:
        ingest_raw(conn)
        run_silver_sql(conn)
        run_gold_sql(conn)
        validate(conn)

        logging.info("PIPELINE SUCCESS")

    except Exception as e:
        logging.error(f"PIPELINE FAILED: {e}")
        raise

    finally:
        conn.close()
        logging.info("Database connection closed")


# -------------------------
# ENTRY POINT
# -------------------------

if __name__ == "__main__":
    run_pipeline()
