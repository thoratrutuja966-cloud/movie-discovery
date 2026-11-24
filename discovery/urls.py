from django.urls import path
from . import views

urlpatterns = [
    path("", views.movie_list, name="movie_list"),
    path("movie/<int:pk>/", views.movie_detail, name="movie_detail"),
    path("movie/<int:pk>/review/", views.submit_movie_review, name="submit_movie_review"),
    path("reviews/<int:review_pk>/report/", views.report_movie_review, name="report_movie_review"),
    path("bookings/<int:booking_pk>/watched/", views.mark_movie_watched, name="mark_movie_watched"),
    path("accounts/signup/", views.signup, name="signup"),
    path("showtime/<int:showtime_id>/seats/", views.seat_availability, name="seat_availability"),
    path("showtime/<int:showtime_id>/book/", views.create_booking_checkout, name="create_booking_checkout"),
    path("bookings/", views.booking_history, name="booking_history"),
    path("bookings/<int:booking_pk>/retry-payment/", views.retry_booking_payment, name="retry_booking_payment"),
    path("payments/success/", views.payment_success, name="payment_success"),
    path("payments/stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("bookings/<int:booking_pk>/ticket.pdf", views.ticket_download, name="ticket_download"),
    path("tickets/verify/<uuid:booking_id>/", views.ticket_verify, name="ticket_verify"),
]
