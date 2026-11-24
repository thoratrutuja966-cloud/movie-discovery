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

Signed-in users can choose up to eight seat labels (for example `A1, A2`) and pay through Stripe Checkout in test mode. A booking is confirmed only after server-side payment verification. The owner can download a generated PDF ticket containing the film, theater, screen, showtime, seats, booking ID, payment reference, total, and a QR code that opens a status-only verification page. A confirmation email with the PDF is sent by a Celery worker after payment succeeds; transient email errors retry with backoff up to five times.

### Run email delivery locally

1. Install/start Redis (for example, with Docker or WSL) and copy `.env.example` to `.env`. The default broker URL is `redis://127.0.0.1:6379/0`.
2. Set your SMTP values in `.env`. Never commit real credentials; `.env` is ignored by Git.
3. In one terminal run `celery -A config worker -l info --pool=solo` from the project folder on Windows (`--pool=solo` is omitted on Linux/macOS).
4. In another terminal run Django with `python manage.py runserver`. A successfully paid booking queues its ticket email; the worker creates and attaches the PDF.

Without Redis and a running worker, bookings and on-demand PDF downloads still work, but email cannot be delivered. The queue configuration is in `config/celery.py`; production deployment also needs a Redis-compatible broker and a Celery background worker. The web app and worker must share the same database; configure the same PostgreSQL `DATABASE_URL` on both (the default SQLite database is for local demos only).

## Public demo deployment

The included `render.yaml` and `build.sh` configure a public Render web service named CineTrail. Push this project to GitHub, then in Render choose **New → Blueprint** and connect the repository. Render builds the app and gives it a public `onrender.com` address. The deployment loads the sample catalogue from `discovery/fixtures/demo_catalog.json` and serves static files through WhiteNoise.

The free Render web service sleeps after 15 minutes without traffic and the first request after sleep can take about a minute. Its filesystem is temporary, so admin edits and uploaded files do not persist across restarts; this setup is for a class demo, not production. Celery email delivery additionally needs a Redis-compatible Render Key Value broker and a separate background worker; a worker uses a paid Render plan, so it is not provisioned automatically by the free web-service Blueprint.

## Features

- Search titles; filter by genre, language, city, theater, release date, minimum rating, and show date.
- Show the filtered count and paginate at nine cards per page.
- Sort by popularity, release date, rating, or lowest ticket price.
- Show details and upcoming showtimes with theater, city, date, and price.
- Record signed-in movie views and payment-confirmed bookings; recommend unseen titles from genres the user watches and books (bookings receive extra weight).
- Manage catalog records through Django Admin; load sample data with `python manage.py seed_movies`.
- Create Stripe-hosted test Checkout sessions; confirm tickets only from server-verified payment status or signed webhooks; inspect payment attempts and webhook event IDs in Django Admin.

## Implementation notes

Filters compose on a Django ORM queryset. Card summaries use `Min` for ticket price and the next upcoming show, genres are prefetched, and the result count is calculated in the database before pagination. Movie and showtime models include indexes for common sort and date access paths.

The sample catalog is illustrative. Payments are test-mode only until the deployment owner configures Stripe test keys and a webhook signing secret. Seat reservations use a demo 8-row by 10-seat auditorium per showtime; adapt that layout to the theater's real seating plan before production use.

## Assignment report draft

**Introduction and background.** This module helps viewers discover films and compare local showtimes. It is structured as a Django app for integration into a larger course application.

**Learning objectives and activities.** The work covers relational models, ORM filters and aggregates, query-driven controls, pagination, Django Admin, and user-specific recommendations. The catalog links movies to genres and showtimes, and showtimes to theaters.

**Skills and competencies.** Django models and views, query composition, aggregation, templates, pagination, indexing, and responsive interface styling.

**Challenges and solutions.** Filters need to compose while keeping the displayed count accurate and URLs shareable. GET parameters drive the filters, one queryset applies them, and database count and pagination follow. Ticket price and upcoming show summaries use ORM aggregation. Recommendations combine view and confirmed-booking genre signals and exclude movies already viewed or booked.

**Outcomes and impact.** The deliverable includes a discovery page, sample catalog loader, movie details, and an admin-managed catalog. Selected indexes and prefetching support query efficiency. No benchmark was run because the sample data is not representative of production scale.

**Feedback, evidence, and conclusion.** Source code and the seed command provide reviewable evidence. Before final submission, integrate the course application's catalog and confirmed bookings and measure performance with its data. No internship feedback or measured performance results are claimed here.

## Task 3: movie management, trailers, and verified reviews

Django Admin manages movies, genres, languages, cast, theaters, showtimes, and multiple poster image URLs. Movie records include long descriptions, YouTube trailers, certification, and runtime. Trailer URLs are embedded only from approved YouTube hosts using the privacy-enhanced player.

Run python manage.py enrich_task3_movies to populate the ten Task 3 demo titles with details. The invented CineTrail stories use sample cast and demo certifications; where there is no verified official video, the trailer button opens a YouTube search rather than embedding an unrelated trailer. Signed-in users can mark a confirmed booking watched after its showtime and runtime have passed, then submit or edit a review. Administrators can moderate reported reviews in Django Admin.

## Task 4: test-mode payment workflow

Bookings start as pending. The server calculates the amount from the selected showtime and seats, creates a Stripe Checkout session with an idempotency key, and confirms the booking only after a matching paid session is verified. The webhook endpoint is `/payments/stripe/webhook/`; configure Stripe to send `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`, and `refund.updated` events. The webhook signature is verified against the raw request body, and event IDs are stored to ignore duplicate deliveries. A signed-in customer can resume or retry a pending/failed payment from My tickets. PDF tickets and ticket emails remain limited to confirmed bookings.

Before enabling checkout, add `STRIPE_SECRET_KEY` (an `sk_test_...` key), `STRIPE_WEBHOOK_SECRET` (`whsec_...`), and `STRIPE_CURRENCY=INR` to the private environment variables for the web service in Render. Do not commit or send keys in chat. In the Stripe Dashboard's test mode, add the webhook endpoint `https://YOUR-RENDER-HOST/payments/stripe/webhook/` and copy its signing secret to Render. Apply migrations during deployment; `build.sh` already runs `manage.py migrate`.

## Task 5: live seat availability and temporary holds

Movie showtimes display a live 8×10 seat map that refreshes every five seconds. Selecting seats does not hold them; the server acquires all requested seats atomically when a signed-in customer continues to checkout. A unique `(showtime, seat_code)` database constraint and a showtime row lock prevent two active bookings from taking the same seat. Holds last two minutes, after which they are released and the associated open Stripe Checkout session is expired. A payment that reaches Stripe after its seat hold is gone does not receive a ticket; the application requests an idempotent automatic refund and records its refund status in the payment attempt.

