"""
application/payment_orchestrator.py

Coordinates payment flows with the Payment Gateway MCP.

Key rules:
  - initiate_payment() must only be called after SEAT_RESERVED
  - Booking transitions to PAYMENT_PENDING immediately on payment creation
  - Final CONFIRMED state only happens after confirm_reservation() succeeds
  - reconcile_payment() handles lost webhooks
"""

import logging
from infrastructure.payment_client import payment_client
from infrastructure.airline_client import airline_client
from infrastructure.repository import get_lock, bookings, users, payment_methods
from domain.booking import BookingStatus, BookingStateError
from application.booking_service import BookingError
from config import WEBHOOK_CALLBACK_URL

logger = logging.getLogger(__name__)


async def initiate_payment(
    booking_id: str,
    payment_token: str | None = None,
) -> dict:
    """
    Create a payment at the gateway and move booking → PAYMENT_PENDING.

    Args:
        booking_id:    The booking to pay for.
        payment_token: Saved payment token (Mode A) or None for redirect (Mode B).

    Returns:
        { booking_id, payment_id, status }
    """
    with get_lock():
        booking = bookings.get(booking_id)
        if booking is None:
            raise BookingError("BOOKING_NOT_FOUND", f"Booking {booking_id!r} not found.")
        if booking.status != BookingStatus.SEAT_RESERVED:
            raise BookingError(
                "INVALID_BOOKING_STATE",
                f"Booking must be SEAT_RESERVED to initiate payment; currently {booking.status.value}.",
            )

    # Create payment at gateway
    gateway_result = await payment_client.create_payment(
        merchant_reference=booking_id,     # idempotency key
        amount=str(booking.total_amount),
        currency=booking.currency,
        callback_url=WEBHOOK_CALLBACK_URL,
    )

    if not gateway_result.get("success"):
        raise BookingError(
            gateway_result.get("error", "GATEWAY_ERROR"),
            gateway_result.get("message", "Payment gateway rejected payment creation."),
        )

    with get_lock():
        booking.payment_id = gateway_result["payment_id"]
        try:
            booking.transition_to(BookingStatus.PAYMENT_PENDING)
        except BookingStateError as e:
            raise BookingError("INVALID_BOOKING_STATE", str(e)) from e

    logger.info(
        "Payment initiated: booking=%s payment=%s",
        booking_id, booking.payment_id,
    )

    return {
        "booking_id": booking_id,
        "payment_id": booking.payment_id,
        "status": booking.status.value,
        "message": (
            "Payment is processing. You will be notified via webhook when complete."
            if payment_token
            else "Redirect user to complete payment. Waiting for webhook confirmation."
        ),
    }


async def handle_payment_success(booking_id: str) -> dict:
    """
    Called by the webhook handler when payment SUCCESS is received.

    Flow: confirm_reservation() → CONFIRMED
    Idempotent: ignores if already CONFIRMED.
    """
    with get_lock():
        booking = bookings.get(booking_id)
        if booking is None:
            logger.warning("Webhook SUCCESS for unknown booking %s", booking_id)
            return {"error": "BOOKING_NOT_FOUND"}

        if booking.status == BookingStatus.CONFIRMED:
            logger.info("Webhook duplicate ignored — booking %s already CONFIRMED.", booking_id)
            return {"booking_id": booking_id, "status": "CONFIRMED"}

        if booking.status != BookingStatus.PAYMENT_PENDING:
            logger.warning(
                "Webhook SUCCESS for booking %s in unexpected state %s",
                booking_id, booking.status.value,
            )
            return {"error": "UNEXPECTED_STATE", "status": booking.status.value}

        reservation_id = booking.reservation_id

    # Confirm the seat with the airline vendor
    confirm_result = await airline_client.confirm_reservation(reservation_id)

    if confirm_result.get("success"):
        with get_lock():
            booking.vendor_booking_reference = confirm_result.get("vendor_booking_reference")
            booking.transition_to(BookingStatus.CONFIRMED)
        logger.info(
            "Booking CONFIRMED: booking=%s vendor_ref=%s",
            booking_id, booking.vendor_booking_reference,
        )
        return {"booking_id": booking_id, "status": "CONFIRMED", "vendor_booking_reference": booking.vendor_booking_reference}
    else:
        # Vendor confirm failed — log for manual review
        logger.error(
            "Vendor confirm FAILED for booking %s (reservation=%s): %s",
            booking_id, reservation_id, confirm_result,
        )
        return {"error": "VENDOR_CONFIRM_FAILED", "booking_id": booking_id}


async def handle_payment_failure(booking_id: str) -> dict:
    """
    Called by the webhook handler when payment FAILED is received.

    Flow: cancel_reservation() → PAYMENT_FAILED
    Idempotent: ignores if already in terminal state.
    """
    with get_lock():
        booking = bookings.get(booking_id)
        if booking is None:
            return {"error": "BOOKING_NOT_FOUND"}

        if booking.is_terminal():
            return {"booking_id": booking_id, "status": booking.status.value}

        reservation_id = booking.reservation_id

    # Release the seat hold
    if reservation_id:
        await airline_client.cancel_reservation(reservation_id)

    with get_lock():
        booking.transition_to(BookingStatus.PAYMENT_FAILED)

    logger.info("Booking PAYMENT_FAILED: booking=%s", booking_id)
    return {"booking_id": booking_id, "status": "PAYMENT_FAILED"}


async def reconcile_payment(booking_id: str) -> dict:
    """
    Manually check payment status and attempt to confirm if payment succeeded
    but webhook was lost.
    """
    with get_lock():
        booking = bookings.get(booking_id)
        if booking is None:
            raise BookingError("BOOKING_NOT_FOUND", f"Booking {booking_id!r} not found.")
        payment_id = booking.payment_id

    if not payment_id:
        return {"booking_id": booking_id, "message": "No payment initiated yet."}

    # Query gateway
    status_result = await payment_client.get_payment_status(payment_id)

    if not status_result.get("success"):
        return {"error": status_result.get("error"), "booking_id": booking_id}

    gw_status = status_result.get("status")
    logger.info("Reconcile booking=%s gateway_status=%s", booking_id, gw_status)

    if gw_status == "SUCCESS":
        with get_lock():
            if booking.status != BookingStatus.CONFIRMED:
                pass  # will attempt confirm below
            else:
                return {"booking_id": booking_id, "status": "CONFIRMED", "note": "Already confirmed."}

        return await handle_payment_success(booking_id)

    return {
        "booking_id": booking_id,
        "gateway_payment_status": gw_status,
        "booking_status": booking.status.value,
    }
