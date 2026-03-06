"""
application/booking_service.py

Core CRUD for Booking entities.
Does NOT call vendors directly — that is handled by orchestrators.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import infrastructure.repository as repo
from domain.booking import Booking, BookingStatus, BookingStateError
from config import BOOKING_HOLD_MINUTES

logger = logging.getLogger(__name__)


class BookingError(Exception):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message

    def to_dict(self) -> dict:
        return {"error": self.error_code, "message": self.message}


# ──────────────────────────────────────────────────────────────────

def create_booking(
    user_id: str,
    flight_id: str,
    seat_count: int,
    price_per_seat: str,
    currency: str,
) -> dict:
    """
    Create a new booking in CREATED state.

    Returns: booking.to_dict()
    Raises:  BookingError(USER_NOT_FOUND)
    """
    with repo.get_lock():
        if user_id not in repo.users:
            raise BookingError("USER_NOT_FOUND", f"User {user_id!r} not found.")

    now = datetime.now(timezone.utc)
    total = Decimal(price_per_seat) * seat_count

    booking = Booking(
        booking_id=f"BOOK-{uuid.uuid4().hex[:10].upper()}",
        user_id=user_id,
        flight_id=flight_id,
        seat_count=seat_count,
        total_amount=total,
        currency=currency,
        status=BookingStatus.CREATED,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(minutes=BOOKING_HOLD_MINUTES),
    )

    with repo.get_lock():
        repo.bookings[booking.booking_id] = booking

    logger.info("Booking created: %s (user=%s, flight=%s)", booking.booking_id, user_id, flight_id)
    return booking.to_dict()


def get_booking(booking_id: str) -> dict:
    with repo.get_lock():
        booking = repo.bookings.get(booking_id)
    if booking is None:
        raise BookingError("BOOKING_NOT_FOUND", f"Booking {booking_id!r} not found.")
    return booking.to_dict()


def list_user_bookings(user_id: str) -> list[dict]:
    return [b.to_dict() for b in repo.get_user_bookings(user_id)]


def cancel_booking(booking_id: str) -> dict:
    """Cancel a booking that is in SEAT_RESERVED state."""
    with repo.get_lock():
        booking = repo.bookings.get(booking_id)
        if booking is None:
            raise BookingError("BOOKING_NOT_FOUND", f"Booking {booking_id!r} not found.")
        try:
            booking.transition_to(BookingStatus.CANCELLED)
        except BookingStateError as e:
            raise BookingError("INVALID_BOOKING_STATE", str(e)) from e

    logger.info("Booking cancelled: %s", booking_id)
    return {"booking_id": booking_id, "status": "CANCELLED"}
