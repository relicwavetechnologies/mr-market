from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, stored: str) -> bool:
    try:
        return _hasher.verify(stored, plain)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False
