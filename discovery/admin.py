from django.contrib import admin
from .models import (BookingHistory, CastMember, Genre, Language, Movie, MoviePoster,
                     MovieReview, MovieView, ReviewReport, Showtime, Theater,
                     MovieWatch)

admin.site.site_header = "CineTrail Administration"
admin.site.site_title = "CineTrail Admin"
admin.site.index_title = "Manage movies and showtimes"

class MoviePosterInline(admin.TabularInline):
    model = MoviePoster
    extra = 1

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "language_display", "certification", "duration_minutes", "rating", "popularity")
    list_filter = ("languages", "genres")
    search_fields = ("title", "synopsis", "description", "cast_members__name")
    filter_horizontal = ("genres", "cast_members", "languages")
    readonly_fields = ("rating", "created_at")
    fieldsets = (
        ("Film", {"fields": ("title", "synopsis", "description", "genres", "languages", "release_date", "certification", "duration_minutes", "cast_members")}),
        ("Artwork and trailer", {"fields": ("poster_url", "trailer_url")}),
        ("Ratings and discovery", {"fields": ("catalog_rating", "rating", "popularity", "created_at")}),
    )
    inlines = (MoviePosterInline,)

    @admin.display(description="Languages")
    def language_display(self, obj):
        return ", ".join(obj.languages.order_by("name").values_list("name", flat=True))

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        language_names = list(form.instance.languages.order_by("name").values_list("name", flat=True))
        form.instance.language = ", ".join(language_names)
        Movie.objects.filter(pk=form.instance.pk).update(language=form.instance.language)

@admin.register(BookingHistory)
class BookingHistoryAdmin(admin.ModelAdmin):
    list_display = ("booking_id", "user", "movie", "showtime", "status", "total_amount", "booked_at", "ticket_email_sent_at")
    list_filter = ("status", "booked_at")
    search_fields = ("booking_id", "payment_reference", "user__username", "user__email", "movie__title")
    readonly_fields = ("booking_id", "booked_at", "ticket_email_sent_at")

@admin.register(CastMember)
class CastMemberAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name", "bio")


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    search_fields = ("name",)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.movies.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(MovieReview)
class MovieReviewAdmin(admin.ModelAdmin):
    list_display = ("movie", "user", "rating", "status", "created_at", "updated_at")
    list_filter = ("status", "rating", "created_at")
    search_fields = ("movie__title", "user__username", "text")
    readonly_fields = ("movie", "user", "booking", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ("review", "reporter", "reason", "status", "created_at")
    list_filter = ("status", "reason", "created_at")
    search_fields = ("review__movie__title", "review__text", "reporter__username", "details")
    readonly_fields = ("review", "reporter", "reason", "details", "created_at")


admin.site.register((Genre, Theater, Showtime, MovieView, MovieWatch))
