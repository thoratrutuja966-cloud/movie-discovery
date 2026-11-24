from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Avg
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from urllib.parse import parse_qs, urlparse
import re
import uuid

class Genre(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    def __str__(self): return self.name

class CastMember(models.Model):
    name = models.CharField(max_length=120, unique=True)
    bio = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self): return self.name

class Language(models.Model):
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self): return self.name

class Movie(models.Model):
    title = models.CharField(max_length=180, db_index=True)
    synopsis = models.TextField()
    genres = models.ManyToManyField(Genre, related_name="movies")
    language = models.CharField(max_length=120, blank=True, default="", db_index=True, help_text="Automatically updated from selected languages.")
    languages = models.ManyToManyField(Language, related_name="movies", blank=True)
    release_date = models.DateField(db_index=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0, db_index=True)
    catalog_rating = models.DecimalField(max_digits=3, decimal_places=1, default=0, help_text="Starting/editor rating shown until users submit reviews.")
    popularity = models.PositiveIntegerField(default=0, db_index=True)
    poster_url = models.CharField(max_length=300, blank=True, help_text="Poster image URL or a path such as /static/discovery/posters/film.svg")
    description = models.TextField(blank=True, help_text="Optional full movie description; synopsis is used when blank.")
    trailer_url = models.URLField(max_length=500, blank=True, help_text="YouTube watch or youtu.be URL. Other hosts are not embedded.")
    certification = models.CharField(max_length=20, blank=True, help_text="Age certificate, for example U, U/A, A, PG-13.")
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    cast_members = models.ManyToManyField(CastMember, related_name="movies", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-popularity", "title"]
        indexes = [models.Index(fields=["-release_date", "-rating"]), models.Index(fields=["-popularity", "-release_date"])]

    def save(self, *args, **kwargs):
        if not kwargs.get("raw") and (
            not self.pk
            or not MovieReview.objects.filter(movie_id=self.pk, status=MovieReview.Status.PUBLISHED).exists()
        ):
            self.rating = self.catalog_rating
        super().save(*args, **kwargs)

    def __str__(self): return self.title

    @property
    def trailer_embed_url(self):
        """Return a privacy-enhanced YouTube embed URL, never an arbitrary iframe URL."""
        if not self.trailer_url:
            return ""
        parsed = urlparse(self.trailer_url.strip())
        host = (parsed.hostname or "").lower()
        if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com", "youtu.be", "www.youtu.be"}:
            return ""
        video_id = ""
        if host.endswith("youtu.be"):
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            video_id = parsed.path.split("/")[2]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return ""
        return f"https://www.youtube-nocookie.com/embed/{video_id}"

    @property
    def trailer_link_url(self):
        """Expose a clickable YouTube link only when its host is trusted."""
        if not self.trailer_url:
            return ""
        parsed = urlparse(self.trailer_url.strip())
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
            "youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com",
            "www.youtube-nocookie.com", "youtu.be", "www.youtu.be",
        }:
            return ""
        return self.trailer_url.strip()

class MoviePoster(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="poster_images")
    image_url = models.URLField(max_length=500)
    alt_text = models.CharField(max_length=180, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self): return self.alt_text or f"Poster for {self.movie}"

class Theater(models.Model):
    name = models.CharField(max_length=120)
    city = models.CharField(max_length=80, db_index=True)
    def __str__(self): return f"{self.name} · {self.city}"

class Showtime(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="showtimes")
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name="showtimes")
    starts_at = models.DateTimeField(db_index=True)
    ticket_price = models.DecimalField(max_digits=7, decimal_places=2)
    screen = models.CharField(max_length=80, default="Screen 1")
    class Meta:
        indexes = [models.Index(fields=["starts_at", "ticket_price"])]
    def __str__(self): return f"{self.movie} · {self.theater} · {self.starts_at:%d %b %H:%M}"

class MovieView(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movie_views")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="view_events")
    viewed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ["-viewed_at"]
        indexes = [models.Index(fields=["user", "-viewed_at"])]

class BookingHistory(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Payment pending"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Payment failed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movie_booking_history")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="booking_history")
    showtime = models.ForeignKey(Showtime, on_delete=models.PROTECT, related_name="bookings", null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    booking_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment_reference = models.CharField(max_length=80, blank=True)
    seats = models.JSONField(default=list, blank=True)
    total_amount = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    ticket_email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)
    booked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-booked_at"]
        indexes = [
            models.Index(fields=["user", "status", "-booked_at"]),
            models.Index(fields=["status", "booked_at"], name="booking_status_time_idx"),
        ]

    def __str__(self): return f"{self.user} · {self.movie} · {self.get_status_display()}"


class PaymentTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        REFUND_PENDING = "refund_pending", "Refund pending"
        REFUNDED = "refunded", "Refunded"

    booking = models.ForeignKey(BookingHistory, on_delete=models.PROTECT, related_name="payment_attempts")
    provider = models.CharField(max_length=20, default="stripe")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    amount_minor = models.PositiveIntegerField(help_text="Amount in the currency's smallest unit, such as paise.")
    currency = models.CharField(max_length=3, default="inr")
    checkout_session_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    payment_intent_id = models.CharField(max_length=255, blank=True)
    refund_id = models.CharField(max_length=255, blank=True)
    refund_error = models.TextField(blank=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    checkout_url = models.URLField(max_length=1000, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="payment_status_time_idx")]

    def __str__(self):
        return f"{self.provider} · {self.booking.booking_id} · {self.get_status_display()}"


class PaymentWebhookEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=120)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.event_type} · {self.event_id}"


class SeatReservation(models.Model):
    class Status(models.TextChoices):
        HELD = "held", "Temporarily held"
        BOOKED = "booked", "Booked"
        RELEASED = "released", "Released"

    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="seat_reservations")
    seat_code = models.CharField(max_length=4)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seat_reservations")
    booking = models.ForeignKey(
        BookingHistory, on_delete=models.CASCADE, related_name="seat_reservations", null=True, blank=True
    )
    payment_attempt = models.ForeignKey(
        PaymentTransaction, on_delete=models.SET_NULL, related_name="seat_reservations", null=True, blank=True
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HELD, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["showtime_id", "seat_code"]
        constraints = [
            models.UniqueConstraint(fields=["showtime", "seat_code"], name="unique_seat_row_per_showtime"),
        ]
        indexes = [models.Index(fields=["showtime", "status", "expires_at"], name="discovery_s_showti_3ac947_idx")]

    def __str__(self):
        return f"{self.showtime} · {self.seat_code} · {self.get_status_display()}"

class MovieWatch(models.Model):
    """A viewer confirms attendance against a completed, confirmed booking."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movie_watches")
    booking = models.OneToOneField(BookingHistory, on_delete=models.CASCADE, related_name="watch_confirmation")
    watched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-watched_at"]

    def clean(self):
        if self.booking_id and self.user_id:
            booking = self.booking
            if booking.user_id != self.user_id or booking.status != BookingHistory.Status.CONFIRMED:
                raise ValidationError("A watch confirmation must belong to the user with a confirmed booking.")

    def __str__(self): return f"{self.user} watched {self.booking.movie}"

class MovieReview(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        HIDDEN = "hidden", "Hidden"

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movie_reviews")
    booking = models.ForeignKey(BookingHistory, on_delete=models.PROTECT, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(max_length=5000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["movie", "user"], name="unique_review_per_movie_user"),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=10), name="review_rating_1_to_10"),
        ]
        indexes = [models.Index(fields=["movie", "status", "-created_at"])]

    def clean(self):
        if self.booking_id and self.user_id and self.movie_id:
            booking = self.booking
            if booking.user_id != self.user_id or booking.movie_id != self.movie_id or booking.status != BookingHistory.Status.CONFIRMED:
                raise ValidationError("A review must reference the user's confirmed booking for this movie.")
            if not MovieWatch.objects.filter(user_id=self.user_id, booking_id=self.booking_id).exists():
                raise ValidationError("A verified review requires a completed watched-booking confirmation.")

    def __str__(self): return f"{self.movie} · {self.rating}/10 · {self.user}"

class ReviewReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        DISMISSED = "dismissed", "Dismissed"
        ACTIONED = "actioned", "Action taken"

    class Reason(models.TextChoices):
        ABUSE = "abuse", "Abusive or hateful content"
        SPOILER = "spoiler", "Unmarked spoiler"
        SPAM = "spam", "Spam or advertising"
        OTHER = "other", "Other"

    review = models.ForeignKey(MovieReview, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_reports")
    reason = models.CharField(max_length=12, choices=Reason.choices)
    details = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["review", "reporter"], name="unique_review_report_per_user")]

    def __str__(self): return f"Report on review {self.review_id} ({self.get_status_display()})"


def recalculate_movie_rating(movie_id):
    average = MovieReview.objects.filter(movie_id=movie_id, status=MovieReview.Status.PUBLISHED).aggregate(value=Avg("rating"))["value"]
    movie = Movie.objects.filter(pk=movie_id).only("catalog_rating").first()
    if movie:
        Movie.objects.filter(pk=movie_id).update(rating=average if average is not None else movie.catalog_rating)


@receiver(post_save, sender=MovieReview)
@receiver(post_delete, sender=MovieReview)
def update_movie_rating_after_review_change(sender, instance, **kwargs):
    recalculate_movie_rating(instance.movie_id)


@receiver(post_save, sender=ReviewReport)
def hide_review_when_report_actioned(sender, instance, **kwargs):
    if instance.status == ReviewReport.Status.ACTIONED:
        MovieReview.objects.filter(pk=instance.review_id).update(status=MovieReview.Status.HIDDEN)
        recalculate_movie_rating(instance.review.movie_id)
