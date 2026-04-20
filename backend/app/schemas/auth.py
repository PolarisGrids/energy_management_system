from typing import List

from pydantic import BaseModel
from app.models.user import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    full_name: str
    role: UserRole
    # Spec 018 W4.T12/T13 — frontend uses permissions for menu/route guards.
    permissions: List[str] = []


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    # Spec 018 W4.T12 — served by `/auth/me` so the frontend can re-gate the
    # UI on reload without a fresh login.
    permissions: List[str] = []

    model_config = {"from_attributes": True}
