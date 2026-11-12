import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone

from .models import BookingHistory
from .tickets import render_ticket_pdf

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True,
             retry_backoff_max=600, retry_jitter=True, max_retries=5)
def send_booking_ticket_email(self, booking_pk):
    booking = BookingHistory.objects.select_related(
        "user", "movie", "showtime__theater"
    ).get(pk=booking_pk)
    if booking.status != BookingHistory.Status.CONFIRMED:
        return "Booking is not confirmed; ticket email skipped."
    if not booking.user.email:
        raise ValueError(f"Booking {booking.pk} has no recipient email address.")

    verify_path = reverse("ticket_verify", kwargs={"booking_id": booking.booking_id})
    verify_url = f"{settings.SITE_BASE_URL}{verify_path}"
    pdf = render_ticket_pdf(booking, verify_url)
    showtime = booking.showtime
    show_line = (f"{showtime.theater.name}, {showtime.theater.city} · "
                 f"{timezone.localtime(showtime.starts_at):%d %b %Y, %I:%M %p} · {showtime.screen}"
                 if showtime else "Showtime details unavailable")
    email = EmailMessage(
        subject=f"Your CineTrail ticket: {booking.movie.title}",
        body=(f"Hello {booking.user.get_full_name() or booking.user.username},\n\n"
              f"Your booking is confirmed. Your ticket is attached.\n\n"
              f"Movie: {booking.movie.title}\nShow: {show_line}\n"
              f"Seats: {', '.join(booking.seats) or '—'}\n"
              f"Booking ID: {booking.booking_id}\nPayment reference: {booking.payment_reference}\n"
              f"Verify ticket: {verify_url}\n\nCineTrail"),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[booking.user.email],
    )
    email.attach(f"CineTrail-ticket-{booking.booking_id}.pdf", pdf.read(), "application/pdf")
    try:
        email.send(fail_silently=False)
    except Exception as exc:
        BookingHistory.objects.filter(pk=booking.pk).update(email_error=str(exc)[:2000])
        logger.exception("Ticket email failed for booking %s; Celery will retry", booking.pk)
        raise

    BookingHistory.objects.filter(pk=booking.pk).update(
        ticket_email_sent_at=timezone.now(), email_error=""
    )
    return f"Ticket emailed for booking {booking.pk}."
