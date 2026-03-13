"""
jobs/booking_expiry_job.py

Background thread that expires bookings that have passed their expires_at.
Runs every 60 seconds.

Affected statuses: SEAT_RESERVED, PAYMENT_PENDING
For each expired:
  1. Cancel reservation with airline vendor (best-effort)
  2. Transition booking → EXPIRED
"""

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

import config
from domain.booking import BookingStatus
import infrastructure.repository as repo

logger = logging.getLogger(__name__)

# Main event loop for async vendor calls
_event_loop: Optional[asyncio.AbstractEventLoop] = None

EXPIRABLE_STATES = {BookingStatus.SEAT_RESERVED, BookingStatus.PAYMENT_PENDING}


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


def _run_expiry_once() -> int:
    """
    Scan bookings and expire stale ones.
    Vendor cancellation is dispatched asynchronously.

    Returns: number of bookings expired.
    """
    now = datetime.now(timezone.utc)
    expired_count = 0

    with repo.get_lock():
        to_expire = [
            b for b in repo.bookings.values()
            if b.status in EXPIRABLE_STATES and b.expires_at <= now
        ]

    for booking in to_expire:
        logger.info(
            "Expiring booking %s (status=%s, expired_at=%s)",
            booking.booking_id, booking.status.value, booking.expires_at.isoformat(),
        )

        # Best-effort cancel vendor reservation
        if booking.reservation_id and _event_loop:
            from infrastructure.airline_client import airline_client
            future = asyncio.run_coroutine_threadsafe(
                airline_client.cancel_reservation(booking.reservation_id),
                _event_loop,
            )
            try:
                future.result(timeout=5)
            except Exception:
                logger.warning(
                    "Could not cancel reservation %s during expiry.",
                    booking.reservation_id,
                )

        with repo.get_lock():
            booking.transition_to(BookingStatus.EXPIRED)

        expired_count += 1

    return expired_count


def _expiry_loop(interval_seconds: int, stop_event: threading.Event) -> None:
    logger.info("Booking expiry job started (interval=%ds).", interval_seconds)
    while not stop_event.wait(timeout=interval_seconds):
        try:
            count = _run_expiry_once()
            if count:
                logger.info("Expiry job: expired %d booking(s).", count)
        except Exception:
            logger.exception("Expiry job encountered an error.")
    logger.info("Booking expiry job stopped.")


def start_expiry_job(interval_seconds: int = None) -> threading.Event:
    interval = interval_seconds or config.EXPIRY_JOB_INTERVAL_SECONDS
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_expiry_loop,
        args=(interval, stop_event),
        daemon=True,
        name="BookingExpiryJob",
    )
    thread.start()
    return stop_event
