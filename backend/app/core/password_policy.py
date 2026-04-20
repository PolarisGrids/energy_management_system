"""Password-policy validator (spec 015-rbac-ui-lib FR-010).

Policy: ≥ 12 chars, ≥ 1 upper, ≥ 1 lower, ≥ 1 digit, ≥ 1 special,
no whitespace-only differences.
"""
from __future__ import annotations

import re

_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"[0-9]")
_SPECIAL = re.compile(r"[!@#$%^&*()_+\-={}\[\];:'\",.<>/?|`~\\]")

MIN_LENGTH = 12


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the policy."""


def validate_password(pw: str) -> None:
    """Raise :class:`PasswordPolicyError` on any policy violation."""
    if not isinstance(pw, str):
        raise PasswordPolicyError("password must be a string")
    if len(pw) < MIN_LENGTH:
        raise PasswordPolicyError(
            f"password must be at least {MIN_LENGTH} characters"
        )
    if not _UPPER.search(pw):
        raise PasswordPolicyError("password must contain an uppercase letter")
    if not _LOWER.search(pw):
        raise PasswordPolicyError("password must contain a lowercase letter")
    if not _DIGIT.search(pw):
        raise PasswordPolicyError("password must contain a digit")
    if not _SPECIAL.search(pw):
        raise PasswordPolicyError("password must contain a special character")
    if pw.strip() != pw:
        raise PasswordPolicyError("password must not have leading/trailing whitespace")
