# CineTrail · Movie discovery

A Django movie discovery module for assignment 1: title search, combined filters, live match totals, sorting, pagination, movie details, showtimes, and recommendations based on viewing and confirmed booking history.

## Run locally

Requires Python 3.10+.

```powershell
cd movie_discovery
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate --fake-initial
python manage.py seed_movies
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ for discovery and http://127.0.0.1:8000/admin/ for catalog administration. Create an admin login with `createsuperuser`; credentials are not embedded in source. Sign in at /accounts/login/ with a user created through Django Admin or the createsuperuser command. Recommendations appear after signed-in users view movie details.

## Task 2: ticket PDFs and email

The movie detail page offers a **demo booking** for signed-in users. Enter up to eight seat labels (for example `A1, A2`) and confirm. The booking history at `/bookings/` lists the booking and lets its owner download a freshly generated PDF ticket. The ticket includes the film, theater, screen, showtime, seats, booking ID, demo payment reference, amount, and a QR code that opens a public status-only verification page. A confirmation email with the PDF is sent by a Celery worker, not in the web request. Transient email errors retry with backoff up to five times.

**Payment note:** this is deliberately a sample confirmation only. It does not charge a card or verify a payment; payment integration and seat locking belong to later tasks. Generated references start with `DEMO-`.

### Run email delivery locally

1. Install/start Redis (for example, with Docker or WSL) and copy `.env.example` to `.env`. The default broker URL is `redis://127.0.0.1:6379/0`.
2. Set your SMTP values in `.env`. Never commit real credentials; `.env` is ignored by Git.
3. In one terminal run `celery -A config worker -l info --pool=solo` from the project folder on Windows (`--pool=solo` is omitted on Linux/macOS).
4. In another terminal run Django with `python manage.py runserver`. A successful demo booking queues its ticket email; the worker creates and attaches the PDF.

Without Redis and a running worker, the demo booking and on-demand PDF download still work, but email cannot be delivered. The queue configuration is in `config/celery.py`; production deployment also needs a Redis-compatible broker and a Celery background worker. The web app and worker must share the same database; configure the same PostgreSQL `DATABASE_URL` on both (the default SQLite database is for local demos only).

## Public demo deployment

The included `render.yaml` and `build.sh` configure a public Render web service named CineTrail. Push this project to GitHub, then in Render choose **New → Blueprint** and connect the repository. Render builds the app and gives it a public `onrender.com` address. The deployment loads the sample catalogue from `discovery/fixtures/demo_catalog.json` and serves static files through WhiteNoise.

The free Render web service sleeps after 15 minutes without traffic and the first request after sleep can take about a minute. Its filesystem is temporary, so admin edits and uploaded files do not persist across restarts; this setup is for a class demo, not production. Celery email delivery additionally needs a Redis-compatible Render Key Value broker and a separate background worker; a worker uses a paid Render plan, so it is not provisioned automatically by the free web-service Blueprint.

## Features

- Search titles; filter by genre, language, city, theater, release date, minimum rating, and show date.
- Show the filtered count and paginate at nine cards per page.
- Sort by popularity, release date, rating, or lowest ticket price.
- Show details and upcoming showtimes with theater, city, date, and price.
- Record signed-in movie views and confirmed bookings; recommend unseen titles from genres the user watches and books (bookings receive extra weight).
- Manage catalog records through Django Admin; load sample data with `python manage.py seed_movies`.

## Implementation notes

Filters compose on a Django ORM queryset. Card summaries use `Min` for ticket price and the next upcoming show, genres are prefetched, and the result count is calculated in the database before pagination. Movie and showtime models include indexes for common sort and date access paths.

The sample catalog is illustrative. `BookingHistory` is a lightweight demo record for recommendation signals, not a reservation or payment system. Connect it to the course application's existing confirmed bookings during integration.

## Assignment report draft

**Introduction and background.** This module helps viewers discover films and compare local showtimes. It is structured as a Django app for integration into a larger course application.

**Learning objectives and activities.** The work covers relational models, ORM filters and aggregates, query-driven controls, pagination, Django Admin, and user-specific recommendations. The catalog links movies to genres and showtimes, and showtimes to theaters.

**Skills and competencies.** Django models and views, query composition, aggregation, templates, pagination, indexing, and responsive interface styling.

**Challenges and solutions.** Filters need to compose while keeping the displayed count accurate and URLs shareable. GET parameters drive the filters, one queryset applies them, and database count and pagination follow. Ticket price and upcoming show summaries use ORM aggregation. Recommendations combine view and confirmed-booking genre signals and exclude movies already viewed or booked.

**Outcomes and impact.** The deliverable includes a discovery page, sample catalog loader, movie details, and an admin-managed catalog. Selected indexes and prefetching support query efficiency. No benchmark was run because the sample data is not representative of production scale.

**Feedback, evidence, and conclusion.** Source code and the seed command provide reviewable evidence. Before final submission, integrate the course application's catalog and confirmed bookings and measure performance with its data. No internship feedback or measured performance results are claimed here.
