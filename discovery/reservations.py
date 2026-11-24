"""Atomic two-minute seat holds for a fixed demo auditorium layout."""

from datetime import timedelta

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from .models import BookingHistory, PaymentTransaction, SeatReservation, Showtime

HOLD_DURATION = timedelta(minutes=2)
SEAT_CODES = tuple(f"{row}{number}" for row in "ABCDEFGH" for number in range(1, 11))


class SeatsUnavailable(Exception):
    pass


def reserve_and_create_booking(*, user, showtime_id, seats):
    seats = [seat.upper() for seat in seats]
    if not seats or len(seats) > 8 or len(seats) != len(set(seats)) or any(seat not in SEAT_CODES for seat in seats):
        raise ValueError("Choose 1–8 different seats from the seat map.")
    try:
        with transaction.atomic():
            showtime = Showtime.objects.select_for_update().select_related(
                "movie", "theater"
            ).get(pk=showtime_id)
            now = timezone.now()
            if showtime.starts_at <= now:
                raise SeatsUnavailable("This showtime has already started. Choose another show.")

            # Expiration is evaluated against the database state while holding the
            # showtime row lock, so simultaneous requests cannot claim the same seat.
            SeatReservation.objects.filter(
                showtime=showtime,
                status=SeatReservation.Status.HELD,
                expires_at__lte=now,
            ).update(status=SeatReservation.Status.RELEASED, updated_at=now)

            old_confirmed_seats = set()
            for old_seats in BookingHistory.objects.filter(
                showtime=showtime, status=BookingHistory.Status.CONFIRMED
            ).values_list("seats", flat=True):
                old_confirmed_seats.update(old_seats or [])

            active = set(SeatReservation.objects.filter(
                showtime=showtime,
                seat_code__in=seats,
            ).filter(
                models_q_booked_or_active(now)
            ).values_list("seat_code", flat=True))
            unavailable = active | old_confirmed_seats
            conflicts = sorted(set(seats) & unavailable)
            if conflicts:
                raise SeatsUnavailable(
                    f"Seat{'s' if len(conflicts) > 1 else ''} {', '.join(conflicts)} just became unavailable. Select another seat."
                )

            booking = BookingHistory.objects.create(
                user=user,
                movie=showtime.movie,
                showtime=showtime,
                status=BookingHistory.Status.PENDING,
                seats=seats,
                total_amount=showtime.ticket_price * len(seats),
            )
            hold_until = now + HOLD_DURATION
            existing = {
                row.seat_code: row
                for row in SeatReservation.objects.select_for_update().filter(
                    showtime=showtime, seat_code__in=seats
                )
            }
            for seat in seats:
                row = existing.get(seat)
                if row:
                    updated = SeatReservation.objects.filter(
                        pk=row.pk,
                        status=SeatReservation.Status.RELEASED,
                    ).update(
                        user=user,
                        booking=booking,
                        payment_attempt=None,
                        status=SeatReservation.Status.HELD,
                        expires_at=hold_until,
                        updated_at=now,
                    )
                    if updated != 1:
                        raise SeatsUnavailable(f"Seat {seat} just became unavailable. Select another seat.")
                else:
                    SeatReservation.objects.create(
                        showtime=showtime,
                        seat_code=seat,
                        user=user,
                        booking=booking,
                        status=SeatReservation.Status.HELD,
                        expires_at=hold_until,
                    )
            return booking
    except IntegrityError as exc:
        # The unique showtime/seat constraint is a final guard if the database
        # races on concurrent inserts (including SQLite, where row locks are no-op).
        raise SeatsUnavailable("A selected seat was claimed by another booking. Please choose again.") from exc
    except OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise SeatsUnavailable("Another booking is updating this show. Please refresh and choose again.") from exc
        raise


def reacquire_booking_hold(booking_id, user):
    """Retry a failed/expired payment using its original seats if they remain free."""
    try:
        with transaction.atomic():
            showtime_id = BookingHistory.objects.filter(pk=booking_id, user=user).values_list(
                "showtime_id", flat=True
            ).first()
            if not showtime_id:
                raise SeatsUnavailable("Booking not found.")
            showtime = Showtime.objects.select_for_update().select_related("movie").get(pk=showtime_id)
            booking = BookingHistory.objects.select_for_update().get(pk=booking_id, user=user)
            if booking.status not in {BookingHistory.Status.FAILED, BookingHistory.Status.CANCELLED}:
                return booking
            now = timezone.now()
            if showtime.starts_at <= now:
                raise SeatsUnavailable("This show has already started. Choose another show.")
            SeatReservation.objects.filter(
                showtime=showtime,
                status=SeatReservation.Status.HELD,
                expires_at__lte=now,
            ).update(status=SeatReservation.Status.RELEASED, updated_at=now)
            requested = set(booking.seats or [])
            legacy_seats = set()
            for seats in BookingHistory.objects.filter(
                showtime=showtime,
                status=BookingHistory.Status.CONFIRMED,
            ).exclude(pk=booking.pk).values_list("seats", flat=True):
                legacy_seats.update(seats or [])
            active = set(SeatReservation.objects.filter(
                showtime=showtime,
                seat_code__in=requested,
            ).filter(models_q_booked_or_active(now)).values_list("seat_code", flat=True))
            if requested & (legacy_seats | active):
                blocked = sorted(requested & (legacy_seats | active))
                raise SeatsUnavailable(f"Seats {', '.join(blocked)} are no longer free. Choose seats again.")

            hold_until = now + HOLD_DURATION
            existing = {
                row.seat_code: row
                for row in SeatReservation.objects.select_for_update().filter(
                    showtime=showtime, seat_code__in=requested
                )
            }
            for seat in requested:
                row = existing.get(seat)
                if row:
                    updated = SeatReservation.objects.filter(
                        pk=row.pk, status=SeatReservation.Status.RELEASED
                    ).update(
                        user=user,
                        booking=booking,
                        payment_attempt=None,
                        status=SeatReservation.Status.HELD,
                        expires_at=hold_until,
                        updated_at=now,
                    )
                    if updated != 1:
                        raise SeatsUnavailable(f"Seat {seat} just became unavailable. Choose again.")
                else:
                    SeatReservation.objects.create(
                        showtime=showtime, seat_code=seat, user=user, booking=booking,
                        status=SeatReservation.Status.HELD, expires_at=hold_until,
                    )
            booking.status = BookingHistory.Status.PENDING
            booking.save(update_fields=["status"])
            return booking
    except IntegrityError as exc:
        raise SeatsUnavailable("A selected seat was claimed by another booking. Please choose again.") from exc
    except OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise SeatsUnavailable("Another booking is updating this show. Refresh and choose again.") from exc
        raise


def models_q_booked_or_active(now):
    from django.db.models import Q

    return Q(status=SeatReservation.Status.BOOKED) | Q(
        status=SeatReservation.Status.HELD, expires_at__gt=now
    )


def seat_map(showtime_id, user_id=None):
    now = timezone.now()
    states = {code: {"status": "available", "expires_at": None} for code in SEAT_CODES}
    legacy = BookingHistory.objects.filter(
        showtime_id=showtime_id, status=BookingHistory.Status.CONFIRMED
    ).values_list("seats", flat=True)
    for seats in legacy:
        for seat in seats or []:
            if seat in states:
                states[seat] = {"status": "booked", "expires_at": None}

    rows = SeatReservation.objects.filter(showtime_id=showtime_id).exclude(
        status=SeatReservation.Status.RELEASED
    ).values("seat_code", "status", "user_id", "expires_at")
    for row in rows:
        seat = row["seat_code"]
        if seat not in states:
            continue
        if row["status"] == SeatReservation.Status.BOOKED:
            states[seat] = {"status": "booked", "expires_at": None}
        elif row["expires_at"] and row["expires_at"] > now:
            states[seat] = {
                "status": "mine" if user_id and row["user_id"] == user_id else "reserved",
                "expires_at": row["expires_at"].isoformat(),
            }
    return states


def booking_has_active_hold(booking, now=None, payment_attempt_id=None):
    now = now or timezone.now()
    reservations = SeatReservation.objects.filter(
        booking=booking,
        status=SeatReservation.Status.HELD,
        expires_at__gt=now,
    )
    if payment_attempt_id is not None:
        reservations = reservations.filter(payment_attempt_id=payment_attempt_id)
    active_seats = set(reservations.values_list("seat_code", flat=True))
    return active_seats == set(booking.seats or [])


def release_booking_holds(booking, now=None, payment_attempt_id=None):
    now = now or timezone.now()
    reservations = SeatReservation.objects.filter(
        booking=booking,
        status=SeatReservation.Status.HELD,
    )
    if payment_attempt_id is not None:
        reservations = reservations.filter(payment_attempt_id=payment_attempt_id)
    return reservations.update(status=SeatReservation.Status.RELEASED, expires_at=None, updated_at=now)


def expire_stale_holds(showtime_id):
    """Release timed-out holds and expire their open Stripe Checkout sessions."""
    now = timezone.now()
    session_ids = []
    with transaction.atomic():
        showtime = Showtime.objects.select_for_update().filter(pk=showtime_id).first()
        if not showtime:
            return
        stale = list(SeatReservation.objects.select_for_update().filter(
            showtime=showtime,
            status=SeatReservation.Status.HELD,
            expires_at__lte=now,
        ).values_list("booking_id", flat=True).distinct())
        SeatReservation.objects.filter(
            showtime=showtime,
            status=SeatReservation.Status.HELD,
            expires_at__lte=now,
        ).update(status=SeatReservation.Status.RELEASED, expires_at=None, updated_at=now)
        for booking_id in filter(None, stale):
            booking = BookingHistory.objects.select_for_update().filter(pk=booking_id).first()
            if not booking or booking.status != BookingHistory.Status.PENDING:
                continue
            if SeatReservation.objects.filter(
                booking=booking,
                status=SeatReservation.Status.HELD,
                expires_at__gt=now,
            ).exists():
                continue
            booking.status = BookingHistory.Status.CANCELLED
            booking.save(update_fields=["status"])
            pending_attempts = PaymentTransaction.objects.filter(
                booking=booking,
                status=PaymentTransaction.Status.PENDING,
            )
            session_ids.extend(pending_attempts.exclude(checkout_session_id__isnull=True).values_list(
                "checkout_session_id", flat=True
            ))
            pending_attempts.update(
                status=PaymentTransaction.Status.EXPIRED,
                error_message="The two-minute seat hold expired before payment completed.",
                updated_at=now,
            )
    _expire_stripe_sessions(session_ids)


def _expire_stripe_sessions(session_ids):
    from django.conf import settings
    import logging
    import stripe

    if not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        return
    logger = logging.getLogger(__name__)
    for session_id in session_ids:
        try:
            stripe.checkout.Session.expire(session_id, api_key=settings.STRIPE_SECRET_KEY)
        except stripe.StripeError:
            # A session may already have completed. The payment webhook will check
            # the hold timestamp and automatically request a refund if it is stale.
            logger.info("Stripe session %s could not be expired; webhook reconciliation will decide its outcome", session_id)
