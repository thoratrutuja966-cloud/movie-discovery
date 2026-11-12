from django.conf import settings
from django.db import models
import uuid

class Genre(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    def __str__(self): return self.name

class Movie(models.Model):
    title = models.CharField(max_length=180, db_index=True)
    synopsis = models.TextField()
    genres = models.ManyToManyField(Genre, related_name="movies")
    language = models.CharField(max_length=40, db_index=True)
    release_date = models.DateField(db_index=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0, db_index=True)
    popularity = models.PositiveIntegerField(default=0, db_index=True)
    poster_url = models.CharField(max_length=300, blank=True, help_text="Poster image URL or a path such as /static/discovery/posters/film.svg")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-popularity", "title"]
        indexes = [models.Index(fields=["-release_date", "-rating"]), models.Index(fields=["-popularity", "-release_date"])]
    def __str__(self): return self.title

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
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movie_booking_history")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="booking_history")
    showtime = models.ForeignKey(Showtime, on_delete=models.PROTECT, related_name="bookings", null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    booking_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment_reference = models.CharField(max_length=80, blank=True)
    seats = models.JSONField(default=list, blank=True)
    total_amount = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    ticket_email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)
    booked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-booked_at"]
        indexes = [models.Index(fields=["user", "status", "-booked_at"])]

    def __str__(self): return f"{self.user} · {self.movie} · {self.get_status_display()}"
