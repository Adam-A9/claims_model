import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import run_pipeline


@pytest.fixture(scope="module")
def pipeline_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("data") / "commercial_insurance.db"
    run_pipeline(db_path=db_path)
    return db_path


def table_count(db_path, table_name):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]


def test_silver_exists(pipeline_db):
    assert table_count(pipeline_db, "silver_customers") > 0


def test_gold_exists(pipeline_db):
    assert table_count(pipeline_db, "gold_customers") > 0
