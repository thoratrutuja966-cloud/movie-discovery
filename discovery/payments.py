"""Stripe Checkout helpers. All money amounts are calculated from server data."""

import logging
from datetime import datetime, timezone as datetime_timezone

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from .models import BookingHistory, PaymentTransaction, PaymentWebhookEvent, SeatReservation, Showtime
from .reservations import booking_has_active_hold, expire_stale_holds, release_booking_holds

logger = logging.getLogger(__name__)


class PaymentSetupError(Exception):
    pass


def stripe_is_configured():
    return bool(
        settings.STRIPE_SECRET_KEY.startswith("sk_test_")
        and settings.STRIPE_WEBHOOK_SECRET.startswith("whsec_")
        and settings.STRIPE_CURRENCY == "inr"
    )


def _stripe_api_key():
    if not stripe_is_configured():
        raise PaymentSetupError("Test-mode Stripe keys and a webhook secret are not configured yet.")
    return settings.STRIPE_SECRET_KEY


def _session_value(session, key, default=None):
    try:
        return session.get(key, default)
    except AttributeError:
        return getattr(session, key, default)


def _new_or_existing_attempt(booking_id):
    with transaction.atomic():
        showtime_id = BookingHistory.objects.filter(pk=booking_id).values_list("showtime_id", flat=True).first()
        if not showtime_id:
            raise BookingHistory.DoesNotExist
        Showtime.objects.select_for_update().get(pk=showtime_id)
        booking = BookingHistory.objects.select_for_update().select_related(
            "movie", "showtime", "showtime__theater", "user"
        ).get(pk=booking_id)
        if booking.status == BookingHistory.Status.CONFIRMED:
            return booking, None, "confirmed"
        if not booking_has_active_hold(booking):
            booking.status = BookingHistory.Status.CANCELLED
            booking.save(update_fields=["status"])
            PaymentTransaction.objects.filter(
                booking=booking, status=PaymentTransaction.Status.PENDING
            ).update(
                status=PaymentTransaction.Status.EXPIRED,
                error_message="The two-minute seat hold expired. Choose seats again to start a new booking.",
                updated_at=timezone.now(),
            )
            return booking, None, "hold_expired"

        attempt = booking.payment_attempts.select_for_update().filter(
            status=PaymentTransaction.Status.PENDING
        ).order_by("-created_at").first()
        if attempt and attempt.checkout_url and attempt.expires_at and attempt.expires_at <= timezone.now():
            attempt.status = PaymentTransaction.Status.EXPIRED
            attempt.save(update_fields=["status", "updated_at"])
            attempt = None
        if attempt and attempt.checkout_url:
            if not booking_has_active_hold(booking, payment_attempt_id=attempt.pk):
                return booking, None, "hold_expired"
            return booking, attempt, "existing"
        if attempt:
            if not booking_has_active_hold(booking, payment_attempt_id=attempt.pk):
                return booking, None, "hold_expired"
            # The first Stripe request may have succeeded even if its response was lost.
            # Reuse the same idempotency key/session instead of creating another charge.
            return booking, attempt, "resume"
        if not booking.showtime_id or booking.showtime.starts_at <= timezone.now():
            return booking, None, "showtime_passed"
        amount_minor = int(booking.total_amount * 100)
        attempt = PaymentTransaction.objects.create(
            booking=booking,
            amount_minor=amount_minor,
            currency=settings.STRIPE_CURRENCY.lower(),
        )
        SeatReservation.objects.filter(
            booking=booking,
            status=SeatReservation.Status.HELD,
            expires_at__gt=timezone.now(),
        ).update(payment_attempt=attempt)
        booking.status = BookingHistory.Status.PENDING
        booking.save(update_fields=["status"])
        return booking, attempt, "new"


def start_checkout(booking_id):
    api_key = _stripe_api_key()
    showtime_id = BookingHistory.objects.filter(pk=booking_id).values_list("showtime_id", flat=True).first()
    if showtime_id:
        expire_stale_holds(showtime_id)
    booking, attempt, state = _new_or_existing_attempt(booking_id)
    if state == "confirmed":
        return None, "confirmed"
    if state == "showtime_passed":
        return None, "showtime_passed"
    if state == "hold_expired":
        return None, "hold_expired"
    if state == "existing":
        return attempt.checkout_url, "ready"

    showtime = booking.showtime
    seats_count = len(booking.seats)
    base_url = settings.SITE_BASE_URL
    success_url = f"{base_url}{reverse('payment_success')}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base_url}{reverse('booking_history')}?payment=cancelled"
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            customer_email=booking.user.email or None,
            client_reference_id=str(booking.booking_id),
            metadata={
                "booking_id": str(booking.booking_id),
                "payment_transaction_id": str(attempt.pk),
            },
            line_items=[{
                "quantity": seats_count,
                "price_data": {
                    "currency": attempt.currency,
                    "unit_amount": int(showtime.ticket_price * 100),
                    "product_data": {
                        "name": booking.movie.title,
                        "description": (
                            f"{showtime.theater.name}, {showtime.theater.city} · "
                            f"{timezone.localtime(showtime.starts_at):%d %b %Y, %I:%M %p} · "
                            f"Seats: {', '.join(booking.seats)}"
                        )[:500],
                    },
                },
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            api_key=api_key,
            idempotency_key=str(attempt.idempotency_key),
        )
    except stripe.StripeError:
        # Keep this attempt pending and retry it with the same idempotency key.
        # A network timeout can happen after Stripe has already created the session.
        PaymentTransaction.objects.filter(pk=attempt.pk, status=PaymentTransaction.Status.PENDING).update(
            error_message="Stripe Checkout could not be reached. Retry the same payment attempt."
        )
        raise

    expiry = _session_value(session, "expires_at")
    expires_at = datetime.fromtimestamp(expiry, tz=datetime_timezone.utc) if expiry else None
    PaymentTransaction.objects.filter(pk=attempt.pk).update(
        checkout_session_id=_session_value(session, "id"),
        checkout_url=_session_value(session, "url", ""),
        expires_at=expires_at,
        error_message="",
    )
    return _session_value(session, "url"), "ready"


def process_checkout_session(session, payment_failed=False):
    """Reconcile a verified Stripe event or a server-retrieved Checkout Session."""
    session_id = _session_value(session, "id")
    metadata = _session_value(session, "metadata", {}) or {}
    attempt_id = _session_value(metadata, "payment_transaction_id")
    booking_ref = _session_value(metadata, "booking_id")
    if not session_id or not attempt_id or not booking_ref:
        return False

    enqueue_email = False
    with transaction.atomic():
        showtime_id = PaymentTransaction.objects.filter(
            pk=attempt_id, booking__booking_id=booking_ref
        ).values_list("booking__showtime_id", flat=True).first()
        if not showtime_id:
            return False
        # Use the same lock order as seat claims and hold expiration:
        # showtime first, then booking/payment rows.
        Showtime.objects.select_for_update().get(pk=showtime_id)
        attempt = PaymentTransaction.objects.select_for_update().select_related("booking").filter(
            pk=attempt_id, booking__booking_id=booking_ref
        ).first()
        if not attempt:
            return False
        if attempt.checkout_session_id and attempt.checkout_session_id != session_id:
            return False
        if not attempt.checkout_session_id:
            attempt.checkout_session_id = session_id
        booking = BookingHistory.objects.select_for_update().get(pk=attempt.booking_id)

        session_currency = (_session_value(session, "currency", "") or "").lower()
        session_amount = _session_value(session, "amount_total")
        if session_currency != attempt.currency or session_amount != attempt.amount_minor:
            return False

        payment_intent = _session_value(session, "payment_intent")
        if not isinstance(payment_intent, str):
            payment_intent = _session_value(payment_intent, "id", "") if payment_intent else ""

        if _session_value(session, "payment_status") == "paid":
            attempt.payment_intent_id = payment_intent or ""
            attempt.error_message = ""
            if booking.status == BookingHistory.Status.CONFIRMED and (
                attempt.status == PaymentTransaction.Status.SUCCEEDED
                or booking.payment_reference in {payment_intent, session_id}
            ):
                attempt.status = PaymentTransaction.Status.SUCCEEDED
            elif (
                attempt.status == PaymentTransaction.Status.PENDING
                and booking.status == BookingHistory.Status.PENDING
                and booking_has_active_hold(booking, payment_attempt_id=attempt.pk)
            ):
                attempt.status = PaymentTransaction.Status.SUCCEEDED
                booking.status = BookingHistory.Status.CONFIRMED
                booking.payment_reference = payment_intent or session_id
                booking.save(update_fields=["status", "payment_reference"])
                SeatReservation.objects.filter(
                    booking=booking,
                    payment_attempt=attempt,
                    status=SeatReservation.Status.HELD,
                ).update(status=SeatReservation.Status.BOOKED, expires_at=None, updated_at=timezone.now())
                enqueue_email = True
            else:
                # Checkout itself can outlive the two-minute seat hold. Never issue
                # a ticket for seats another customer may now own; refund the late payment.
                attempt.status = PaymentTransaction.Status.REFUND_PENDING
                attempt.refund_error = "Payment arrived after this payment attempt lost its seat hold. Automatic refund requested."
                another_payment_pending = PaymentTransaction.objects.filter(
                    booking=booking,
                    status=PaymentTransaction.Status.PENDING,
                ).exclude(pk=attempt.pk).exists()
                if booking.status != BookingHistory.Status.CONFIRMED and not another_payment_pending:
                    booking.status = BookingHistory.Status.CANCELLED
                    booking.payment_reference = payment_intent or session_id
                    booking.save(update_fields=["status", "payment_reference"])
                release_booking_holds(booking, payment_attempt_id=attempt.pk)
                if payment_intent:
                    transaction.on_commit(lambda pk=attempt.pk: _refund_expired_payment(pk))
            attempt.save(update_fields=["checkout_session_id", "status", "payment_intent_id", "error_message", "refund_error", "updated_at"])
        elif payment_failed and attempt.status == PaymentTransaction.Status.PENDING:
            attempt.status = PaymentTransaction.Status.EXPIRED if _session_value(session, "status") == "expired" else PaymentTransaction.Status.FAILED
            attempt.error_message = "Payment was not completed. You can retry from My bookings."
            attempt.save(update_fields=["checkout_session_id", "status", "error_message", "updated_at"])
            another_payment_pending = PaymentTransaction.objects.filter(
                booking=booking,
                status=PaymentTransaction.Status.PENDING,
            ).exclude(pk=attempt.pk).exists()
            if booking.status != BookingHistory.Status.CONFIRMED and not another_payment_pending:
                booking.status = (
                    BookingHistory.Status.CANCELLED
                    if _session_value(session, "status") == "expired"
                    else BookingHistory.Status.FAILED
                )
                booking.save(update_fields=["status"])
            release_booking_holds(booking, payment_attempt_id=attempt.pk)
        else:
            attempt.save(update_fields=["checkout_session_id", "updated_at"])

        if enqueue_email:
            transaction.on_commit(lambda pk=booking.pk: _queue_ticket_email(pk))
    return True


def _queue_ticket_email(booking_pk):
    # Reuse the booking email path without creating a module import cycle.
    from .views import _enqueue_ticket_email

    _enqueue_ticket_email(booking_pk)


def _refund_expired_payment(attempt_pk):
    attempt = PaymentTransaction.objects.filter(pk=attempt_pk).first()
    if not attempt or attempt.status != PaymentTransaction.Status.REFUND_PENDING:
        return
    if not attempt.payment_intent_id:
        PaymentTransaction.objects.filter(pk=attempt_pk).update(
            refund_error="Stripe did not return a PaymentIntent ID; manual refund review is required."
        )
        return
    try:
        refund = stripe.Refund.create(
            payment_intent=attempt.payment_intent_id,
            api_key=settings.STRIPE_SECRET_KEY,
            idempotency_key=f"seat-hold-expired-refund-{attempt.idempotency_key}",
        )
        refund_id = _session_value(refund, "id", "")
        refund_status = _session_value(refund, "status", "pending")
        PaymentTransaction.objects.filter(pk=attempt_pk).update(
            status=(PaymentTransaction.Status.REFUNDED if refund_status == "succeeded" else PaymentTransaction.Status.REFUND_PENDING),
            refund_id=refund_id,
            refund_error="" if refund_status == "succeeded" else f"Refund status: {refund_status}",
            updated_at=timezone.now(),
        )
    except stripe.StripeError as exc:
        logger.exception("Automatic refund failed for payment attempt %s", attempt_pk)
        PaymentTransaction.objects.filter(pk=attempt_pk).update(
            refund_error=str(exc)[:2000],
            updated_at=timezone.now(),
        )


def handle_webhook_event(event):
    """Persist event IDs and apply each Stripe webhook at most once."""
    event_id = _session_value(event, "id")
    event_type = _session_value(event, "type", "")
    if not event_id:
        return False
    event_object = _session_value(_session_value(event, "data", {}), "object", {})
    supported = {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
        "checkout.session.expired",
        "refund.updated",
    }
    try:
        with transaction.atomic():
            record = PaymentWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
            if event_type in supported:
                if event_type == "refund.updated":
                    process_refund_event(event_object)
                else:
                    failed = event_type in {"checkout.session.async_payment_failed", "checkout.session.expired"}
                    process_checkout_session(event_object, payment_failed=failed)
            record.processed_at = timezone.now()
            record.save(update_fields=["processed_at"])
    except IntegrityError:
        if PaymentWebhookEvent.objects.filter(event_id=event_id).exists():
            return True
        raise
    return False


def process_refund_event(refund):
    payment_intent = _session_value(refund, "payment_intent")
    if not isinstance(payment_intent, str):
        payment_intent = _session_value(payment_intent, "id", "") if payment_intent else ""
    if not payment_intent:
        return False
    refund_status = _session_value(refund, "status", "")
    PaymentTransaction.objects.filter(
        payment_intent_id=payment_intent,
        status=PaymentTransaction.Status.REFUND_PENDING,
    ).update(
        status=PaymentTransaction.Status.REFUNDED if refund_status == "succeeded" else PaymentTransaction.Status.REFUND_PENDING,
        refund_id=_session_value(refund, "id", ""),
        refund_error="" if refund_status == "succeeded" else f"Refund status: {refund_status}",
        updated_at=timezone.now(),
    )
    return True
