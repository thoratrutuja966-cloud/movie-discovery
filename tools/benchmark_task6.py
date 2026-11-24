"""Small, reproducible SQLite benchmark for Task 6 booking-date aggregations.

This uses synthetic rows in an in-memory database. It does not access the app's
database or claim to predict production PostgreSQL performance.
"""

import argparse
import sqlite3
import statistics
import time
from datetime import date, datetime, time as datetime_time, timedelta


def measure(connection, sql, parameters, repetitions):
    samples = []
    result = None
    for _ in range(repetitions):
        started = time.perf_counter()
        result = connection.execute(sql, parameters).fetchone()
        samples.append((time.perf_counter() - started) * 1000)
    return result, statistics.median(samples)


def query_plan(connection, sql, parameters):
    return [row[3] for row in connection.execute("EXPLAIN QUERY PLAN " + sql, parameters)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    if args.rows < 100_000:
        parser.error("--rows must be at least 100000 to meet the assignment target")

    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA journal_mode=MEMORY")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("""
        CREATE TABLE booking_history (
            id INTEGER PRIMARY KEY,
            booked_at TEXT NOT NULL,
            status TEXT NOT NULL,
            total_amount REAL NOT NULL
        )
    """)

    today = date.today()
    base = datetime.combine(today - timedelta(days=365 * 8), datetime_time.min)
    rows = []
    for index in range(args.rows):
        booked_at = base + timedelta(days=(index * 29) % (365 * 8), minutes=(index * 37) % 1440)
        status = "confirmed" if index % 10 < 7 else "failed" if index % 10 < 9 else "cancelled"
        rows.append((booked_at.isoformat(timespec="seconds"), status, float(220 + index % 500)))
    connection.executemany(
        "INSERT INTO booking_history(booked_at, status, total_amount) VALUES (?, ?, ?)", rows
    )
    connection.commit()

    start_at = datetime.combine(today - timedelta(days=29), datetime_time.min).isoformat(timespec="seconds")
    end_at = datetime.combine(today + timedelta(days=1), datetime_time.min).isoformat(timespec="seconds")
    date_range_query = """
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0)
        FROM booking_history
        WHERE booked_at >= ? AND booked_at < ?
    """
    confirmed_range_query = """
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0)
        FROM booking_history
        WHERE status = 'confirmed' AND booked_at >= ? AND booked_at < ?
    """
    parameters = (start_at, end_at)

    baseline_date, baseline_date_ms = measure(
        connection,
        "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM booking_history NOT INDEXED WHERE booked_at >= ? AND booked_at < ?",
        parameters,
        args.repetitions,
    )
    baseline_confirmed, baseline_confirmed_ms = measure(
        connection,
        "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM booking_history NOT INDEXED WHERE status = 'confirmed' AND booked_at >= ? AND booked_at < ?",
        parameters,
        args.repetitions,
    )

    connection.execute("CREATE INDEX booking_booked_at_idx ON booking_history(booked_at)")
    connection.execute("CREATE INDEX booking_status_time_idx ON booking_history(status, booked_at)")
    connection.execute("ANALYZE")
    indexed_date, indexed_date_ms = measure(connection, date_range_query, parameters, args.repetitions)
    indexed_confirmed, indexed_confirmed_ms = measure(connection, confirmed_range_query, parameters, args.repetitions)

    print(f"Rows: {args.rows:,}")
    print(f"Date range: {today - timedelta(days=29)} through {today} (inclusive)")
    print(f"Median over {args.repetitions} runs; values below are milliseconds")
    print(f"Date-range aggregate: scan {baseline_date_ms:.2f}; indexed {indexed_date_ms:.2f}; matching rows {indexed_date[0]:,}")
    print(f"Confirmed date aggregate: scan {baseline_confirmed_ms:.2f}; indexed {indexed_confirmed_ms:.2f}; matching rows {indexed_confirmed[0]:,}")
    print("Date-range query plan:")
    for line in query_plan(connection, date_range_query, parameters):
        print(f"  {line}")
    print("Confirmed date query plan:")
    for line in query_plan(connection, confirmed_range_query, parameters):
        print(f"  {line}")
    print("Scope: synthetic SQLite query-shape benchmark only; not a Django/PostgreSQL production benchmark.")


if __name__ == "__main__":
    main()
