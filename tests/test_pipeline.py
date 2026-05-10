import sqlite3

def test_silver_exists():
    conn = sqlite3.connect("commercial_insurance.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM silver_customers")
    count = cursor.fetchone()[0]

    assert count > 0


def test_gold_exists():
    conn = sqlite3.connect("commercial_insurance.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM gold_customers")
    count = cursor.fetchone()[0]

    assert count > 0