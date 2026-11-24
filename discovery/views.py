import csv
from datetime import date, datetime, time, timedelta
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, F, Min, OuterRef, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseServerError, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models.functions import ExtractHour, TruncDay, TruncMonth, TruncWeek, TruncYear
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import stripe

from .models import (BookingHistory, Genre, Language, Movie, MovieReview, MovieView,
                     MovieWatch, PaymentTransaction, ReviewReport, Showtime, Theater)
from .forms import MovieReviewForm, ReviewReportForm, SignUpForm
from .tickets import render_ticket_pdf
from .payments import PaymentSetupError, handle_webhook_event, process_checkout_session, start_checkout, stripe_is_configured
from .reservations import (SEAT_CODES, SeatsUnavailable, expire_stale_holds,
                           reacquire_booking_hold, reserve_and_create_booking, seat_map)

logger = logging.getLogger(__name__)


def _analytics_date_range(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=29)
    errors = []

    def parse_date(key, default):
        raw = request.GET.get(key)
        if not raw:
            return default
        try:
            return date.fromisoformat(raw)
        except ValueError:
            errors.append(f"{key.title()} date must use YYYY-MM-DD format.")
            return default

    start = parse_date("start", default_start)
    end = parse_date("end", today)
    if start > end:
        errors.append("Start date must be on or before end date.")
        start, end = default_start, today
    start_at = timezone.make_aware(datetime.combine(start, time.min))
    end_at = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
    return start, end, start_at, end_at, errors


def _analytics_report(request):
    start, end, start_at, end_at, errors = _analytics_date_range(request)
    bookings = BookingHistory.objects.filter(booked_at__gte=start_at, booked_at__lt=end_at)
    confirmed = bookings.filter(status=BookingHistory.Status.CONFIRMED)
    summary = bookings.aggregate(
        confirmed_count=Count("id", filter=Q(status=BookingHistory.Status.CONFIRMED)),
        revenue=Sum("total_amount", filter=Q(status=BookingHistory.Status.CONFIRMED)),
        failed_count=Count("id", filter=Q(status=BookingHistory.Status.FAILED)),
        cancelled_count=Count("id", filter=Q(status=BookingHistory.Status.CANCELLED)),
    )
    refunds = PaymentTransaction.objects.filter(
        created_at__gte=start_at,
        created_at__lt=end_at,
        status__in=[PaymentTransaction.Status.REFUND_PENDING, PaymentTransaction.Status.REFUNDED],
    ).aggregate(count=Count("id"), amount_minor=Sum("amount_minor"))

    periods = []
    period_queries = (
        ("Daily", TruncDay("booked_at")),
        ("Weekly", TruncWeek("booked_at")),
        ("Monthly", TruncMonth("booked_at")),
        ("Yearly", TruncYear("booked_at")),
    )
    for label, truncation in period_queries:
        grouped = list(confirmed.annotate(period=truncation).values("period").annotate(
            bookings=Count("id"), revenue=Sum("total_amount")
        ).order_by("period"))
        for row in grouped:
            row["period_label"] = timezone.localtime(row["period"]).strftime(
                "%d %b %Y" if label in {"Daily", "Weekly"} else "%b %Y" if label == "Monthly" else "%Y"
            )
        periods.extend({**row, "group": label} for row in grouped)
    period_trends = {}
    for label in ("Daily", "Weekly", "Monthly", "Yearly"):
        grouped = [row for row in periods if row["group"] == label]
        visible = grouped[-30:] if label == "Daily" else grouped[-16:] if label == "Weekly" else grouped[-12:] if label == "Monthly" else grouped[-8:]
        maximum = max((row["revenue"] or 0 for row in visible), default=0)
        for row in visible:
            row["bar_percent"] = int(row["revenue"] * 100 / maximum) if maximum else 0
        period_trends[label.lower()] = visible

    movies = list(confirmed.values("movie_id", "movie__title").annotate(
        booking_count=Count("id"), revenue=Sum("total_amount")
    ).order_by("-booking_count", "movie__title")[:10])

    theater_bookings = {
        row["showtime__theater_id"]: row
        for row in confirmed.filter(showtime__isnull=False).values("showtime__theater_id").annotate(
            booking_count=Count("id"), revenue=Sum("total_amount")
        )
    }
    show_stats = {row["theater_id"]: row for row in Showtime.objects.filter(
        starts_at__gte=start_at, starts_at__lt=end_at
    ).values("theater_id").annotate(
        show_count=Count("id"),
        booked_seats=Count("seat_reservations", filter=Q(
            seat_reservations__status="booked"
        )),
    )}
    theaters = []
    for theater_id, name, city in Theater.objects.order_by("city", "name").values_list("id", "name", "city"):
        row = show_stats.get(theater_id, {"show_count": 0, "booked_seats": 0})
        performance = theater_bookings.get(theater_id, {})
        capacity = row["show_count"] * len(SEAT_CODES)
        theaters.append({
            "theater_id": theater_id,
            "theater__name": name,
            "theater__city": city,
            "show_count": row["show_count"],
            "booked_seats": row["booked_seats"],
            "booking_count": performance.get("booking_count", 0),
            "revenue": performance.get("revenue") or 0,
            "occupancy": (row["booked_seats"] * 100 / capacity) if capacity else 0,
            "capacity": capacity,
        })
    theaters.sort(key=lambda row: (-row["revenue"], row["theater__city"], row["theater__name"]))

    peak_hours = list(bookings.annotate(hour=ExtractHour("booked_at")).values("hour").annotate(
        booking_count=Count("id")
    ).order_by("hour"))
    user_model = get_user_model()
    user_growth = list(user_model.objects.filter(
        date_joined__gte=start_at, date_joined__lt=end_at
    ).annotate(period=TruncMonth("date_joined")).values("period").annotate(
        users=Count("id")
    ).order_by("period"))
    for row in user_growth:
        row["period_label"] = timezone.localtime(row["period"]).strftime("%b %Y")
    new_users = sum(row["users"] for row in user_growth)

    return {
        "start": start,
        "end": end,
        "errors": errors,
        "confirmed_count": summary["confirmed_count"] or 0,
        "revenue": summary["revenue"] or 0,
        "failed_count": summary["failed_count"] or 0,
        "cancelled_count": summary["cancelled_count"] or 0,
        "refund_count": refunds["count"] or 0,
        "refund_total": (refunds["amount_minor"] or 0) / 100,
        "new_users": new_users,
        "periods": periods,
        "period_trends": period_trends,
        "trend_sections": [
            ("Daily", period_trends["daily"]),
            ("Weekly", period_trends["weekly"]),
            ("Monthly", period_trends["monthly"]),
            ("Yearly", period_trends["yearly"]),
        ],
        "movies": movies,
        "theaters": theaters,
        "peak_hours": peak_hours,
        "user_growth": user_growth,
    }


@staff_member_required
def admin_analytics(request):
    report = _analytics_report(request)
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Cache-Control"] = "private, no-store"
        response["Content-Disposition"] = (
            f'attachment; filename="cinetrail-analytics-{report["start"]}-to-{report["end"]}.csv"'
        )
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["CineTrail analytics", report["start"], report["end"]])
        writer.writerow(["Summary metric", "Value"])
        for label, value in (
            ("Confirmed bookings", report["confirmed_count"]),
            ("Revenue (INR)", report["revenue"]),
            ("Failed bookings", report["failed_count"]),
            ("Cancelled bookings", report["cancelled_count"]),
            ("Refund cases", report["refund_count"]),
            ("Refund amount (INR)", report["refund_total"]),
            ("New users", report["new_users"]),
        ):
            writer.writerow([label, value])
        writer.writerow([])
        writer.writerow(["Revenue trend", "Period", "Confirmed bookings", "Revenue (INR)"])
        for row in report["periods"]:
            writer.writerow([row["group"], row["period_label"], row["bookings"], row["revenue"]])
        writer.writerow([])
        writer.writerow(["Movie", "Confirmed bookings", "Revenue (INR)"])
        for row in report["movies"]:
            writer.writerow([_safe_csv_text(row["movie__title"]), row["booking_count"], row["revenue"]])
        writer.writerow([])
        writer.writerow(["Theater", "City", "Showtimes", "Booked seats", "Capacity", "Occupancy %", "Bookings", "Revenue (INR)"])
        for row in report["theaters"]:
            writer.writerow([_safe_csv_text(row["theater__name"]), _safe_csv_text(row["theater__city"]), row["show_count"], row["booked_seats"], row["capacity"], f'{row["occupancy"]:.1f}', row["booking_count"], row["revenue"]])
        writer.writerow([])
        writer.writerow(["Peak booking hour (24h)", "Bookings"])
        for row in report["peak_hours"]:
            writer.writerow([row["hour"], row["booking_count"]])
        writer.writerow([])
        writer.writerow(["User growth month", "New users"])
        for row in report["user_growth"]:
            writer.writerow([row["period_label"], row["users"]])
        return response
    response = render(request, "discovery/admin_analytics.html", report)
    response["Cache-Control"] = "private, no-store"
    return response


def _safe_csv_text(value):
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

SORTS = {"popular": "-popularity", "newest": "-release_date", "rating": "-rating", "price": "showtimes__ticket_price"}

def movie_list(request):
    params = request.GET
    movies = Movie.objects.all().prefetch_related("genres", "languages").annotate(
        min_price=Min("showtimes__ticket_price"),
        next_show=Min("showtimes__starts_at", filter=Q(showtimes__starts_at__gte=timezone.now())),
        cities_count=Count("showtimes__theater__city", distinct=True),
    ).distinct()
    query = params.get("q", "").strip()
    if query: movies = movies.filter(title__icontains=query)
    if params.get("genre"): movies = movies.filter(genres__slug=params["genre"])
    if params.get("language"): movies = movies.filter(languages__name=params["language"])
    if params.get("city"): movies = movies.filter(showtimes__theater__city__iexact=params["city"])
    if params.get("theater"): movies = movies.filter(showtimes__theater_id=params["theater"])
    if params.get("date"):
        try: movies = movies.filter(release_date__gte=date.fromisoformat(params["date"]))
        except ValueError: pass
    if params.get("min_rating"):
        try: movies = movies.filter(rating__gte=float(params["min_rating"]))
        except ValueError: pass
    if params.get("show_date"):
        try:
            show_day = date.fromisoformat(params["show_date"])
            movies = movies.filter(showtimes__starts_at__date=show_day)
        except ValueError: pass
    sort = params.get("sort", "popular")
    if sort == "price": movies = movies.order_by("min_price", "title")
    else: movies = movies.order_by(SORTS.get(sort, SORTS["popular"]), "title")
    # Count is applied to the already filtered queryset, so the live result total matches the cards.
    match_count = movies.count()
    page = Paginator(movies, 9).get_page(params.get("page"))
    recommendations = Movie.objects.none()
    if request.user.is_authenticated:
        watched_ids = MovieView.objects.filter(user=request.user).order_by().values("movie_id")
        booked_ids = BookingHistory.objects.filter(
            user=request.user, status=BookingHistory.Status.CONFIRMED
        ).order_by().values("movie_id")
        interacted_ids = watched_ids.union(booked_ids)
        favorite_genres = Genre.objects.annotate(
            view_score=Count("movies__view_events", filter=Q(movies__view_events__user=request.user), distinct=True),
            booking_score=Count("movies__booking_history", filter=Q(movies__booking_history__user=request.user, movies__booking_history__status=BookingHistory.Status.CONFIRMED), distinct=True),
        ).annotate(score=F("view_score") + 2 * F("booking_score")).filter(score__gt=0).order_by("-score", "name").values("id")[:3]
        recommendations = Movie.objects.exclude(pk__in=interacted_ids).filter(genres__in=favorite_genres).annotate(
            shared=Count("genres", distinct=True),
        ).order_by("-shared", "-popularity").distinct()[:4]
    return render(request, "discovery/movie_list.html", {"movies": page, "page_obj": page, "match_count": match_count,
        "featured_movies": Movie.objects.order_by("-popularity", "title")[:3],
        "genres": Genre.objects.order_by("name"), "languages": Language.objects.order_by("name"),
        "cities": Theater.objects.order_by("city").values_list("city", flat=True).distinct(), "theaters": Theater.objects.order_by("name"),
        "recommendations": recommendations, "filters": params, "sorts": [("popular", "Popularity"), ("newest", "Newest releases"), ("rating", "Top rated"), ("price", "Ticket price")], "today": timezone.localdate()} )

def movie_detail(request, pk):
    movie = get_object_or_404(Movie.objects.prefetch_related("genres", "poster_images", "cast_members"), pk=pk)
    if request.user.is_authenticated:
        MovieView.objects.create(user=request.user, movie=movie)
    showtimes = Showtime.objects.filter(movie=movie, starts_at__gte=timezone.now()).select_related("theater").order_by("starts_at")
    similar = Movie.objects.filter(genres__in=movie.genres.all()).filter(
        languages__in=movie.languages.all()
    ).exclude(pk=movie.pk).prefetch_related("genres", "languages").distinct().order_by("-popularity")[:4]
    trending = Movie.objects.exclude(pk=movie.pk).prefetch_related("genres").order_by("-popularity", "title")[:4]
    recent_releases = Movie.objects.exclude(pk=movie.pk).prefetch_related("genres").order_by("-release_date", "title")[:4]
    review_form = None
    can_review = False
    pending_watches = []
    if request.user.is_authenticated:
        runtime = movie.duration_minutes or 120
        pending_watches = list(BookingHistory.objects.filter(
            user=request.user,
            movie=movie,
            status=BookingHistory.Status.CONFIRMED,
            showtime__starts_at__lte=timezone.now() - timedelta(minutes=runtime),
            watch_confirmation__isnull=True,
        ).select_related("showtime", "showtime__theater").order_by("-showtime__starts_at"))
        can_review = MovieWatch.objects.filter(user=request.user, booking__movie=movie).exists()
        if can_review:
            existing_review = MovieReview.objects.filter(movie=movie, user=request.user).first()
            review_form = MovieReviewForm(instance=existing_review)
    reviews = MovieReview.objects.filter(movie=movie, status=MovieReview.Status.PUBLISHED).select_related("user")
    return render(request, "discovery/movie_detail.html", {
        "movie": movie,
        "showtimes": showtimes,
        "payments_enabled": stripe_is_configured(),
        "seat_codes": SEAT_CODES,
        "similar": similar,
        "trending": trending,
        "recent_releases": recent_releases,
        "reviews": reviews,
        "review_count": reviews.count(),
        "review_form": review_form,
        "can_review": can_review,
        "pending_watches": pending_watches,
        "report_form": ReviewReportForm(),
    })


@login_required
@require_POST
def mark_movie_watched(request, booking_pk):
    booking = get_object_or_404(
        BookingHistory.objects.select_related("movie", "showtime"),
        pk=booking_pk,
        user=request.user,
        status=BookingHistory.Status.CONFIRMED,
    )
    runtime = booking.movie.duration_minutes or 120
    if not booking.showtime or booking.showtime.starts_at + timedelta(minutes=runtime) > timezone.now():
        messages.error(request, "You can mark this movie watched after its showtime has finished.")
        return redirect("movie_detail", pk=booking.movie_id)
    MovieWatch.objects.get_or_create(user=request.user, booking=booking)
    messages.success(request, "Marked as watched. You can now rate and review this movie.")
    return redirect(f"/movie/{booking.movie_id}/#reviews")


@login_required
@require_POST
def submit_movie_review(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    watched_booking = MovieWatch.objects.filter(
        user=request.user, booking__movie=movie, booking__status=BookingHistory.Status.CONFIRMED,
    ).select_related("booking").order_by("-watched_at").first()
    if not watched_booking:
        messages.error(request, "You can review this movie after a confirmed booking's showtime has finished and you mark it watched.")
        return redirect("movie_detail", pk=movie.pk)
    existing = MovieReview.objects.filter(movie=movie, user=request.user).first()
    if existing and existing.status == MovieReview.Status.HIDDEN:
        messages.error(request, "This review is hidden while it is being moderated. Contact an administrator if you need help.")
        return redirect(f"/movie/{movie.pk}/#reviews")
    form = MovieReviewForm(request.POST, instance=existing)
    if form.is_valid():
        review = form.save(commit=False)
        review.movie = movie
        review.user = request.user
        if not existing:
            review.booking = watched_booking.booking
        review.save()
        messages.success(request, "Your review has been saved.")
    else:
        messages.error(request, "Please enter a rating from 1 to 10 and a review of up to 5,000 characters.")
    return redirect(f"/movie/{movie.pk}/#reviews")


@login_required
@require_POST
def report_movie_review(request, review_pk):
    review = get_object_or_404(MovieReview.objects.select_related("movie"), pk=review_pk, status=MovieReview.Status.PUBLISHED)
    if review.user_id == request.user.id:
        messages.error(request, "You cannot report your own review.")
        return redirect(f"/movie/{review.movie_id}/#reviews")
    if ReviewReport.objects.filter(review=review, reporter=request.user).exists():
        messages.info(request, "You have already reported this review. An administrator can review your report.")
        return redirect(f"/movie/{review.movie_id}/#reviews")
    form = ReviewReportForm(request.POST)
    if form.is_valid():
        report = form.save(commit=False)
        report.review = review
        report.reporter = request.user
        report.save()
        messages.success(request, "Thank you. Your report has been sent to the site administrators.")
    else:
        messages.error(request, "Choose a reason before submitting the report.")
    return redirect(f"/movie/{review.movie_id}/#reviews")


@login_required
@require_POST
def create_booking_checkout(request, showtime_id):
    """Create a pending booking, then redirect to Stripe-hosted test Checkout."""
    if not stripe_is_configured():
        messages.error(request, "Secure online payment is not configured yet. Please try again later.")
        return redirect("movie_detail", pk=get_object_or_404(Showtime, pk=showtime_id).movie_id)
    raw_seats = request.POST.getlist("seats")
    seats = [seat.strip().upper() for value in raw_seats for seat in value.split(",") if seat.strip()]
    try:
        expire_stale_holds(showtime_id)
        booking = reserve_and_create_booking(user=request.user, showtime_id=showtime_id, seats=seats)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("movie_detail", pk=get_object_or_404(Showtime, pk=showtime_id).movie_id)
    except SeatsUnavailable as exc:
        messages.error(request, str(exc))
        return redirect("movie_detail", pk=get_object_or_404(Showtime, pk=showtime_id).movie_id)
    return _redirect_to_checkout(request, booking.pk)


def seat_availability(request, showtime_id):
    showtime = get_object_or_404(Showtime, pk=showtime_id, starts_at__gt=timezone.now())
    expire_stale_holds(showtime.pk)
    response = JsonResponse({
        "showtime_id": showtime.pk,
        "hold_seconds": 120,
        "seats": seat_map(showtime.pk, request.user.pk if request.user.is_authenticated else None),
    })
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
def retry_booking_payment(request, booking_pk):
    booking = get_object_or_404(BookingHistory, pk=booking_pk, user=request.user)
    if booking.status == BookingHistory.Status.CONFIRMED:
        messages.info(request, "This booking is already confirmed.")
        return redirect("booking_history")
    if booking.status in {BookingHistory.Status.FAILED, BookingHistory.Status.CANCELLED}:
        expire_stale_holds(booking.showtime_id)
        try:
            booking = reacquire_booking_hold(booking.pk, request.user)
        except SeatsUnavailable as exc:
            messages.error(request, str(exc))
            return redirect("movie_detail", pk=booking.movie_id)
    return _redirect_to_checkout(request, booking.pk)


def _redirect_to_checkout(request, booking_pk):
    try:
        checkout_url, state = start_checkout(booking_pk)
    except PaymentSetupError as exc:
        messages.error(request, str(exc))
        return redirect("booking_history")
    except stripe.StripeError:
        logger.exception("Stripe Checkout request failed for booking %s", booking_pk)
        messages.error(request, "Stripe could not start checkout. Use Retry payment in My tickets to safely try again.")
        return redirect("booking_history")
    if state == "confirmed":
        messages.info(request, "This booking is already confirmed.")
        return redirect("booking_history")
    if state == "showtime_passed":
        messages.error(request, "This showtime has already started. Choose another show.")
        return redirect("booking_history")
    if state == "hold_expired":
        messages.error(request, "Your two-minute seat hold expired. Choose seats again from the movie page.")
        return redirect("booking_history")
    if not checkout_url:
        messages.error(request, "Checkout is not available yet. Please retry from My tickets.")
        return redirect("booking_history")
    return redirect(checkout_url)


@login_required
def payment_success(request):
    session_id = request.GET.get("session_id", "")
    attempt = PaymentTransaction.objects.filter(
        checkout_session_id=session_id,
        booking__user=request.user,
    ).select_related("booking").first()
    if not attempt:
        messages.error(request, "We could not match that payment session to your account.")
        return redirect("booking_history")
    try:
        if not stripe_is_configured():
            raise PaymentSetupError("Payment verification is temporarily unavailable.")
        session = stripe.checkout.Session.retrieve(session_id, api_key=settings.STRIPE_SECRET_KEY)
        if not process_checkout_session(session):
            messages.error(request, "Payment details could not be verified. Please contact support before trying again.")
        elif BookingHistory.objects.filter(pk=attempt.booking_id, status=BookingHistory.Status.CONFIRMED).exists():
            messages.success(request, "Payment confirmed. Your ticket is ready in My tickets.")
        elif PaymentTransaction.objects.filter(
            pk=attempt.pk,
            status__in=[PaymentTransaction.Status.REFUND_PENDING, PaymentTransaction.Status.REFUNDED],
        ).exists():
            messages.warning(request, "Your seat hold expired before payment completed. No ticket was issued; a refund was requested.")
        else:
            messages.info(request, "Payment is still processing. Refresh My tickets in a moment.")
    except PaymentSetupError as exc:
        messages.error(request, str(exc))
    except stripe.StripeError:
        logger.exception("Could not verify Stripe Checkout session %s", session_id)
        messages.error(request, "Payment verification is temporarily unavailable. Refresh My tickets shortly.")
    return redirect("booking_history")


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET.startswith("whsec_"):
        return HttpResponseServerError("Webhook is not configured.")
    try:
        event = stripe.Webhook.construct_event(
            payload=request.body,
            sig_header=request.headers.get("Stripe-Signature", ""),
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponseBadRequest("Invalid Stripe webhook signature.")
    try:
        handle_webhook_event(event)
    except Exception:
        logger.exception("Stripe webhook processing failed for event %s", getattr(event, "id", "unknown"))
        return HttpResponseServerError("Webhook processing failed; Stripe may retry this event.")
    return HttpResponse(status=200)


def _enqueue_ticket_email(booking_pk):
    # Queue publication happens after commit and has a short connection timeout.
    # Email transmission itself always runs in a Celery worker, never in the request.
    from .tasks import send_booking_ticket_email

    try:
        send_booking_ticket_email.delay(booking_pk)
        return True
    except Exception:
        logger.exception("Booking %s saved, but ticket email could not be queued", booking_pk)
        return False


@login_required
def booking_history(request):
    stale_showtimes = BookingHistory.objects.filter(
        user=request.user,
        status=BookingHistory.Status.PENDING,
        showtime__isnull=False,
    ).values_list("showtime_id", flat=True).distinct()
    for showtime_id in stale_showtimes:
        expire_stale_holds(showtime_id)
    bookings = list(BookingHistory.objects.filter(user=request.user).select_related(
        "movie", "showtime__theater"
    ).prefetch_related("payment_attempts", "seat_reservations").annotate(watch_confirmed=Exists(MovieWatch.objects.filter(booking_id=OuterRef("pk")))).order_by("-booked_at"))
    now = timezone.now()
    for booking in bookings:
        runtime = booking.movie.duration_minutes or 120
        held_until = [reservation.expires_at for reservation in booking.seat_reservations.all()
                      if reservation.status == "held" and reservation.expires_at]
        booking.seat_hold_expires_at = min(held_until) if held_until else None
        booking.can_mark_watched = bool(
            booking.status == BookingHistory.Status.CONFIRMED
            and booking.showtime
            and booking.showtime.starts_at + timedelta(minutes=runtime) <= now
            and not booking.watch_confirmed
        )
    return render(request, "discovery/booking_history.html", {
        "bookings": bookings,
        "payment_state": request.GET.get("payment", ""),
    })


@login_required
def ticket_download(request, booking_pk):
    booking = get_object_or_404(
        BookingHistory.objects.select_related("movie", "showtime__theater"),
        pk=booking_pk,
        user=request.user,
        status=BookingHistory.Status.CONFIRMED,
    )
    from django.conf import settings
    from django.urls import reverse

    verify_path = reverse("ticket_verify", kwargs={"booking_id": booking.booking_id})
    pdf = render_ticket_pdf(booking, f"{settings.SITE_BASE_URL}{verify_path}")
    response = HttpResponse(pdf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="CineTrail-ticket-{booking.booking_id}.pdf"'
    return response


def ticket_verify(request, booking_id):
    booking = get_object_or_404(
        BookingHistory.objects.select_related("movie", "showtime__theater"),
        booking_id=booking_id,
    )
    return render(request, "discovery/ticket_verify.html", {"booking": booking})


def signup(request):
    if request.user.is_authenticated:
        return redirect("movie_list")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("movie_list")
    return render(request, "discovery/signup.html", {"form": form})
