from datetime import date, timedelta
import logging
import re
import uuid

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, F, Min, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .models import (BookingHistory, Genre, Language, Movie, MovieReview, MovieView,
                     MovieWatch, ReviewReport, Showtime, Theater)
from .forms import MovieReviewForm, ReviewReportForm, SignUpForm
from .tickets import render_ticket_pdf

logger = logging.getLogger(__name__)

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
def create_demo_booking(request, showtime_id):
    """Create a confirmed sample booking; real payment verification belongs to task 4."""
    showtime = get_object_or_404(
        Showtime.objects.select_related("movie", "theater"),
        pk=showtime_id,
        starts_at__gt=timezone.now(),
    )
    seats_text = request.POST.get("seats", "")
    seats = [seat.strip().upper() for seat in seats_text.split(",") if seat.strip()]
    if not seats or len(seats) > 8 or len(seats) != len(set(seats)) or any(not re.fullmatch(r"[A-Z]{1,2}[0-9]{1,2}", seat) for seat in seats):
        messages.error(request, "Enter 1–8 different seats, separated by commas (for example A1, A2).")
        return redirect("movie_detail", pk=showtime.movie_id)

    with transaction.atomic():
        booking = BookingHistory.objects.create(
            user=request.user,
            movie=showtime.movie,
            showtime=showtime,
            status=BookingHistory.Status.CONFIRMED,
            seats=seats,
            total_amount=showtime.ticket_price * len(seats),
            payment_reference=f"DEMO-{uuid.uuid4().hex[:12].upper()}",
        )
        queue_status = {}
        transaction.on_commit(lambda booking_pk=booking.pk: queue_status.update(queued=_enqueue_ticket_email(booking_pk)))

    email_state = "queued" if queue_status.get("queued") else "unavailable"
    return redirect(f"/bookings/?booked={booking.pk}&email={email_state}")


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
    bookings = list(BookingHistory.objects.filter(user=request.user).select_related(
        "movie", "showtime__theater"
    ).annotate(watch_confirmed=Exists(MovieWatch.objects.filter(booking_id=OuterRef("pk")))).order_by("-booked_at"))
    now = timezone.now()
    for booking in bookings:
        runtime = booking.movie.duration_minutes or 120
        booking.can_mark_watched = bool(
            booking.status == BookingHistory.Status.CONFIRMED
            and booking.showtime
            and booking.showtime.starts_at + timedelta(minutes=runtime) <= now
            and not booking.watch_confirmed
        )
    return render(request, "discovery/booking_history.html", {
        "bookings": bookings,
        "booked": request.GET.get("booked"),
        "email_queued": request.GET.get("email") == "queued",
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
