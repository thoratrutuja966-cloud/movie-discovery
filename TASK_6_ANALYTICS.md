# Task 6: Admin business analytics

## Dashboard

- Open `/admin-dashboard/` while signed in with an active Django staff account. The dashboard and CSV export are protected with Django's `staff_member_required` check.
- Choose an inclusive start and end date. The default range is the most recent 30 days.
- The page reports confirmed booking revenue, new accounts, failed and cancelled bookings, refunds, daily/weekly/monthly/yearly revenue trends, occupancy per theater, top movies and theaters, peak booking hours, and monthly user growth.
- Use **Export CSV** to download the same date-filtered report. The file contains aggregate figures and no customer email addresses or other user-level data.

## Query and indexing notes

The report uses Django ORM `Count`, `Sum`, date truncation, and filtered aggregates. It asks the database for grouped totals and transfers only summary rows to Django rather than loading individual booking or payment records into Python. Theater occupancy is aggregated from showtimes and booked seat-reservation rows; capacity is based on the current 80-seat auditorium map. The page limits displayed trend buckets while the CSV keeps the full selected range.

Migration `0008_analytics_indexes` adds composite indexes on `(status, booked_at)` for booking status/date filters and `(status, created_at)` for refund/payment status/date filters. Existing indexes on `Showtime.starts_at` and `BookingHistory.booked_at` also support the date-range lookups. These choices let the database narrow common status-and-date queries using index ranges and keep aggregation in the database.

## 100,000-row benchmark

Run `python tools/benchmark_task6.py` to create 100,000 synthetic booking rows in an in-memory SQLite database, compare date-range aggregates before and after the same single-column and composite indexes used by the app, and print query plans. Increase the size with `--rows 250000` or the sample count with `--repetitions 10`. The benchmark is reproducible and does not read or modify the app database.

On the development machine for this report, the seven-run median was 2.57 ms for a date-range aggregate without indexes and 0.29 ms with the `booked_at` index; the confirmed date-range aggregate was 4.33 ms without indexes and 0.19 ms with `(status, booked_at)`. SQLite's query plan changed from a table scan to index range searches for both query shapes.

This benchmark demonstrates the index access path and local SQLite query shape only. Its timings are machine-specific and are not a production PostgreSQL throughput claim. For deployment-scale evidence, repeat against an isolated PostgreSQL database on the target hosting plan with representative bookings, showtimes, reservations, and users; record its query plan and timings.

## Admin account security

No default username or password is created, committed, or included in this repository. Use a dedicated Django staff/superuser account provisioned through the hosting environment's protected shell or another approved secret-management workflow. If an assignment report requires credentials, deliver them to the intended reviewer privately through an approved channel; never publish them in GitHub, a public report, or source code.
