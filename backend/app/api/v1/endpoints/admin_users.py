"""Admin-only user CRUD (spec 015-rbac-ui-lib US2).

All endpoints here are gated by the ``users.manage`` capability. Every
mutation publishes an audit event via ``otel-common-py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
import secrets
import string
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.password_policy import PasswordPolicyError, validate_password
from app.core.permissions import USERS_MANAGE, require_permission
from app.core.security import get_password_hash
from app.db.base import get_db
from app.models.user import User, UserRole

try:
    from otel_common.audit import audit  # pragma: no cover
except ImportError:  # pragma: no cover
    async def audit(**kwargs):
        return None


router = APIRouter()


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.OPERATOR
    password: str


class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserAdminOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ResetPasswordOut(BaseModel):
    user_id: int
    one_time_password: str
    must_change_password: bool = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_otp(length: int = 16) -> str:
    """Generate an OTP that satisfies the password policy."""
    specials = "!@#$%^&*_-+=?"
    alphabet = string.ascii_letters + string.digits + specials
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        try:
            validate_password(candidate)
        except PasswordPolicyError:
            continue
        return candidate


def _active_admin_count(db: Session) -> int:
    return (
        db.query(User)
        .filter(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .count()
    )


@router.get("/", response_model=List[UserAdminOut])
def list_users(
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(USERS_MANAGE)),
):
    query = db.query(User)
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))
    if q:
        like = f"%{q}%"
        query = query.filter(
            (User.username.ilike(like)) | (User.email.ilike(like)) | (User.full_name.ilike(like))
        )
    return query.order_by(User.id).offset(offset).limit(min(limit, 200)).all()


@router.post("/", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(USERS_MANAGE)),
):
    try:
        validate_password(payload.password)
    except PasswordPolicyError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "password_policy", "message": str(e)},
        )
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="username already exists")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        password_changed_at=_now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    await audit(
        action_type="WRITE",
        action_name="create_user",
        entity_type="User",
        entity_id=str(user.id),
        request_data={"username": payload.username, "email": payload.email, "role": payload.role.value},
        status=201,
        method="POST",
        path="/api/v1/admin/users",
        user_id=str(current_user.id),
    )
    return user


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(USERS_MANAGE)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes: dict[str, dict] = {}

    if payload.email is not None and payload.email != user.email:
        changes["email"] = {"old": user.email, "new": payload.email}
        user.email = payload.email

    if payload.full_name is not None and payload.full_name != user.full_name:
        changes["full_name"] = {"old": user.full_name, "new": payload.full_name}
        user.full_name = payload.full_name

    if payload.role is not None and payload.role != user.role:
        # Guard last-admin demotion
        if user.role == UserRole.ADMIN and payload.role != UserRole.ADMIN:
            if _active_admin_count(db) <= 1:
                raise HTTPException(
                    status_code=409,
                    detail="At least one active administrator is required",
                )
        changes["role"] = {"old": user.role.value, "new": payload.role.value}
        user.role = payload.role

    if payload.is_active is not None and payload.is_active != user.is_active:
        # Guard disabling last admin
        if (
            user.role == UserRole.ADMIN
            and user.is_active
            and payload.is_active is False
            and _active_admin_count(db) <= 1
        ):
            raise HTTPException(
                status_code=409,
                detail="At least one active administrator is required",
            )
        changes["is_active"] = {"old": user.is_active, "new": payload.is_active}
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    await audit(
        action_type="WRITE",
        action_name="update_user",
        entity_type="User",
        entity_id=str(user.id),
        request_data={"changes": changes},
        status=200,
        method="PATCH",
        path=f"/api/v1/admin/users/{user_id}",
        user_id=str(current_user.id),
    )
    return user


@router.post("/{user_id}/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(USERS_MANAGE)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if (
        user.role == UserRole.ADMIN
        and user.is_active
        and _active_admin_count(db) <= 1
    ):
        raise HTTPException(
            status_code=409,
            detail="At least one active administrator is required",
        )
    user.is_active = False
    db.commit()
    await audit(
        action_type="WRITE",
        action_name="disable_user",
        entity_type="User",
        entity_id=str(user.id),
        status=204,
        method="POST",
        path=f"/api/v1/admin/users/{user_id}/disable",
        user_id=str(current_user.id),
    )
    return None


@router.post("/{user_id}/reset_password", response_model=ResetPasswordOut)
async def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(USERS_MANAGE)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    otp = _generate_otp()
    user.hashed_password = get_password_hash(otp)
    user.password_changed_at = _now()
    db.commit()
    await audit(
        action_type="WRITE",
        action_name="reset_password",
        entity_type="User",
        entity_id=str(user.id),
        status=200,
        method="POST",
        path=f"/api/v1/admin/users/{user_id}/reset_password",
        user_id=str(current_user.id),
    )
    return ResetPasswordOut(user_id=user.id, one_time_password=otp)
