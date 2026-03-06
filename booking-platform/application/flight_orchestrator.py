"""
application/flight_orchestrator.py

Coordinates flight search and seat reservation with the Airline Vendor MCP.
"""

import logging
from infrastructure.airline_client import airline_client
from infrastructure.repository import get_lock, bookings
from domain.booking import BookingStatus, BookingStateError
from application.booking_service import BookingError

logger = logging.getLogger(__name__)


async def search_flights(origin: str, destination: str, date: str) -> dict:
    """Delegate flight search to the airline vendor."""
    result = await airline_client.search_flights(origin, destination, date)
    return result


async def reserve_flight(booking_id: str) -> dict:
    """
    Reserve seats on the airline vendor for an existing CREATED booking.

    Transition: CREATED → SEAT_RESERVED

    Returns: { booking_id, reservation_id, expires_at, status }
    """
    with get_lock():
        booking = bookings.get(booking_id)
        if booking is None:
            raise BookingError("BOOKING_NOT_FOUND", f"Booking {booking_id!r} not found.")
        if booking.status != BookingStatus.CREATED:
            raise BookingError(
                "INVALID_BOOKING_STATE",
                f"Booking must be CREATED to reserve seats; currently {booking.status.value}.",
            )

    # Call vendor — outside lock to avoid blocking
    vendor_result = await airline_client.reserve_seats(
        flight_id=booking.flight_id,
        seat_count=booking.seat_count,
        client_reference=booking_id,
    )

    if not vendor_result.get("success"):
        raise BookingError(
            vendor_result.get("error", "VENDOR_ERROR"),
            vendor_result.get("message", "Airline vendor rejected reservation."),
        )

    with get_lock():
        booking.reservation_id = vendor_result["reservation_id"]
        try:
            booking.transition_to(BookingStatus.SEAT_RESERVED)
        except BookingStateError as e:
            raise BookingError("INVALID_BOOKING_STATE", str(e)) from e

    logger.info(
        "Seat reserved: booking=%s reservation=%s",
        booking_id, booking.reservation_id,
    )

    return {
        "booking_id": booking_id,
        "reservation_id": booking.reservation_id,
        "expires_at": vendor_result.get("expires_at"),
        "status": booking.status.value,
    }
