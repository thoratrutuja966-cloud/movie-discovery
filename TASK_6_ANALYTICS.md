# Task 6: Admin business analytics

## Dashboard

- Open `/admin-dashboard/` while signed in with an active Django staff account. The dashboard and CSV export are protected with Django's `staff_member_required` check.
- Choose an inclusive start and end date. The default range is the most recent 30 days.
- The page reports confirmed booking revenue, new accounts, failed and cancelled bookings, refunds, daily/weekly/monthly/yearly revenue trends, occupancy per theater, top movies and theaters, peak booking hours, and monthly user growth.
- Use **Export CSV** to download the same date-filtered report. The file contains aggregate figures and no customer email addresses or other user-level data.

## Query and indexing notes

The report uses Django ORM `Count`, `Sum`, date truncation, and filtered aggregates. It asks the database for grouped totals and transfers only summary rows to Django rather than loading individual booking or payment records into Python. Theater occupancy is aggregated from showtimes and booked seat-reservation rows; capacity is based on the current 80-seat auditorium map. The page limits displayed trend buckets while the CSV keeps the full selected range.

Migration `0008_analytics_indexes` adds composite indexes on `(status, booked_at)` for booking status/date filters and `(status, created_at)` for refund/payment status/date filters. Existing indexes on `Showtime.starts_at` and `BookingHistory.booked_at` also support the date-range lookups. These choices reduce rows examined for common status-and-date queries and keep aggregation in the database.

No 100,000-booking benchmark was run as part of this change. Before making a performance claim for a particular hosting database, run a production-like benchmark with representative data and inspect the database query plan. SQLite is suitable for local development but is not the concurrency/performance target for large live booking volumes.

## Admin account security

No default username or password is created, committed, or included in this repository. Use a dedicated Django staff/superuser account provisioned through the hosting environment's protected shell or another approved secret-management workflow. If an assignment report requires credentials, deliver them to the intended reviewer privately through an approved channel; never publish them in GitHub, a public report, or source code.
