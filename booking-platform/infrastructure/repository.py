"""
infrastructure/repository.py

Thread-safe in-memory stores for the Booking Platform.
Pre-seeded with two mock users and their payment methods.
"""

import threading
from domain.user import User
from domain.payment_method import PaymentMethod

_LOCK = threading.Lock()

# ── Stores ───────────────────────────────────────────────────────
bookings: dict = {}          # booking_id   → Booking
users: dict = {}             # user_id      → User
payment_methods: dict = {}   # payment_token → PaymentMethod


def get_lock() -> threading.Lock:
    return _LOCK


def get_user_payment_methods(user_id: str) -> list[PaymentMethod]:
    """Return all payment methods for a given user."""
    with _LOCK:
        return [pm for pm in payment_methods.values() if pm.user_id == user_id]


def get_user_bookings(user_id: str) -> list:
    """Return all bookings for a given user."""
    with _LOCK:
        return [b for b in bookings.values() if b.user_id == user_id]


def _seed() -> None:
    """Pre-populate users and payment methods."""
    # ── Users ─────────────────────────────────────────────────────
    alice = User(
        user_id="USR-001",
        name="Alice",
        email="alice@airbook.example.com",
        auto_payment_enabled=True,
        default_payment_token="PM-ALICE-001",
    )
    bob = User(
        user_id="USR-002",
        name="Bob",
        email="bob@airbook.example.com",
        auto_payment_enabled=False,
        default_payment_token=None,
    )

    # ── Payment Methods ───────────────────────────────────────────
    alice_card = PaymentMethod(
        payment_token="PM-ALICE-001",
        user_id="USR-001",
        masked_card_number="**** **** **** 4242",
        expiry="12/26",
        is_default=True,
    )

    with _LOCK:
        users[alice.user_id] = alice
        users[bob.user_id] = bob
        payment_methods[alice_card.payment_token] = alice_card


# Seed on import
_seed()
