from django.contrib import admin
from .models import BookingHistory, Genre, Movie, MovieView, Showtime, Theater

admin.site.site_header = "CineTrail Administration"
admin.site.site_title = "CineTrail Admin"
admin.site.index_title = "Manage movies and showtimes"

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "release_date", "rating", "popularity")
    list_filter = ("language", "genres")
    search_fields = ("title", "synopsis")
    filter_horizontal = ("genres",)

@admin.register(BookingHistory)
class BookingHistoryAdmin(admin.ModelAdmin):
    list_display = ("booking_id", "user", "movie", "showtime", "status", "total_amount", "booked_at", "ticket_email_sent_at")
    list_filter = ("status", "booked_at")
    search_fields = ("booking_id", "payment_reference", "user__username", "user__email", "movie__title")
    readonly_fields = ("booking_id", "booked_at", "ticket_email_sent_at")

admin.site.register((Genre, Theater, Showtime, MovieView))
