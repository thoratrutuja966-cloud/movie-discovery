from django.urls import path
from . import views

urlpatterns = [
    path("", views.movie_list, name="movie_list"),
    path("movie/<int:pk>/", views.movie_detail, name="movie_detail"),
    path("accounts/signup/", views.signup, name="signup"),
    path("showtime/<int:showtime_id>/book/", views.create_demo_booking, name="create_demo_booking"),
    path("bookings/", views.booking_history, name="booking_history"),
    path("bookings/<int:booking_pk>/ticket.pdf", views.ticket_download, name="ticket_download"),
    path("tickets/verify/<uuid:booking_id>/", views.ticket_verify, name="ticket_verify"),
]
