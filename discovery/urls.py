from django.urls import path
from . import views

urlpatterns = [
    path("", views.movie_list, name="movie_list"),
    path("movie/<int:pk>/", views.movie_detail, name="movie_detail"),
    path("movie/<int:pk>/review/", views.submit_movie_review, name="submit_movie_review"),
    path("reviews/<int:review_pk>/report/", views.report_movie_review, name="report_movie_review"),
    path("bookings/<int:booking_pk>/watched/", views.mark_movie_watched, name="mark_movie_watched"),
    path("accounts/signup/", views.signup, name="signup"),
    path("showtime/<int:showtime_id>/book/", views.create_demo_booking, name="create_demo_booking"),
    path("bookings/", views.booking_history, name="booking_history"),
    path("bookings/<int:booking_pk>/ticket.pdf", views.ticket_download, name="ticket_download"),
    path("tickets/verify/<uuid:booking_id>/", views.ticket_verify, name="ticket_verify"),
]
