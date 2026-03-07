"""
domain/booking.py

Booking aggregate root with a strict state machine.

States:
    CREATED → SEAT_RESERVED → PAYMENT_PENDING → CONFIRMED
                                              → PAYMENT_FAILED → PAYMENT_PENDING (retry)
              SEAT_RESERVED → CANCELLED
              SEAT_RESERVED → EXPIRED
              PAYMENT_PENDING → EXPIRED
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class BookingStatus(str, Enum):
    CREATED = "CREATED"
    SEAT_RESERVED = "SEAT_RESERVED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# Terminal states — no further transitions allowed
TERMINAL_STATES = {
    BookingStatus.CONFIRMED,
    BookingStatus.CANCELLED,
    BookingStatus.EXPIRED,
}

# Allowed transitions
_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.CREATED: {BookingStatus.SEAT_RESERVED},
    BookingStatus.SEAT_RESERVED: {
        BookingStatus.PAYMENT_PENDING,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.PAYMENT_PENDING: {
        BookingStatus.CONFIRMED,
        BookingStatus.PAYMENT_FAILED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.PAYMENT_FAILED: {BookingStatus.PAYMENT_PENDING},
    BookingStatus.CONFIRMED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.EXPIRED: set(),
}


class BookingStateError(Exception):
    """Raised on illegal state transition."""
    def __init__(self, current: BookingStatus, target: BookingStatus):
        super().__init__(
            f"Cannot transition booking from {current.value} → {target.value}"
        )
        self.error_code = "INVALID_BOOKING_STATE"


@dataclass
class Booking:
    booking_id: str
    user_id: str
    flight_id: str
    seat_count: int
    total_amount: Decimal
    currency: str
    status: BookingStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    # Filled in as lifecycle progresses
    reservation_id: Optional[str] = None
    vendor_booking_reference: Optional[str] = None
    payment_id: Optional[str] = None

    def transition_to(self, new_status: BookingStatus) -> None:
        allowed = _TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise BookingStateError(self.status, new_status)
        self.status = new_status
        self.updated_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def is_expired(self) -> bool:
        from datetime import timezone
        return __import__("datetime").datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self) -> dict:
        return {
            "booking_id": self.booking_id,
            "user_id": self.user_id,
            "flight_id": self.flight_id,
            "seat_count": self.seat_count,
            "total_amount": str(self.total_amount),
            "currency": self.currency,
            "status": self.status.value,
            "reservation_id": self.reservation_id,
            "vendor_booking_reference": self.vendor_booking_reference,
            "payment_id": self.payment_id,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
