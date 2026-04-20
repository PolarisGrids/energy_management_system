"""Password-policy acceptance + rejection tests.

Spec 015-rbac-ui-lib FR-010.
"""
import pytest

from app.core.password_policy import PasswordPolicyError, validate_password


@pytest.mark.parametrize(
    "pw",
    [
        "CorrectHorse#9!",      # 15 chars, all classes
        "Polaris-EMS-2026!",    # 17 chars
        "Str0ng!Passwordzz",    # 17 chars
        "A1b2C3d4E5f6!",        # 13 chars
    ],
)
def test_accepts_valid_passwords(pw):
    # Should not raise
    validate_password(pw)


@pytest.mark.parametrize(
    "pw,reason",
    [
        ("short1A!", "too short"),
        ("alllowercase123!", "no uppercase"),
        ("ALLUPPERCASE123!", "no lowercase"),
        ("NoDigitsHere!!!!", "no digit"),
        ("NoSpecials1234567", "no special"),
        ("password123", "missing multiple classes"),
        (" LeadingSpace1! ", "whitespace edges"),
    ],
)
def test_rejects_weak_passwords(pw, reason):
    with pytest.raises(PasswordPolicyError):
        validate_password(pw)
