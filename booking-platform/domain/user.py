"""
domain/user.py  –  Platform user entity.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    user_id: str
    name: str
    email: str
    auto_payment_enabled: bool = False
    default_payment_token: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "auto_payment_enabled": self.auto_payment_enabled,
            "default_payment_token": self.default_payment_token,
        }
