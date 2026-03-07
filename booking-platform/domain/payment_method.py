"""
domain/payment_method.py  –  Saved payment method (no raw card data stored).
"""

from dataclasses import dataclass


@dataclass
class PaymentMethod:
    payment_token: str       # opaque token — used with payment gateway
    user_id: str
    masked_card_number: str  # e.g. "**** **** **** 4242"
    expiry: str              # e.g. "12/26"
    is_default: bool = False

    def to_dict(self) -> dict:
        return {
            "payment_token": self.payment_token,
            "user_id": self.user_id,
            "masked_card_number": self.masked_card_number,
            "expiry": self.expiry,
            "is_default": self.is_default,
        }
