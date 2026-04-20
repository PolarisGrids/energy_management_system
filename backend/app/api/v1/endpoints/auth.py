from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rbac import get_permissions
from app.core.security import create_access_token, verify_password
from app.db.base import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services.audit_publisher import publish_audit

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    start = perf_counter()
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        await publish_audit(
            action_type="WRITE",
            action_name="user_login_failed",
            entity_type="User",
            entity_id=payload.username,
            method="POST",
            path=str(request.url.path),
            response_status=401,
            duration_ms=int((perf_counter() - start) * 1000),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        await publish_audit(
            action_type="WRITE",
            action_name="user_login_disabled",
            entity_type="User",
            entity_id=str(user.id),
            method="POST",
            path=str(request.url.path),
            response_status=403,
            user_id=str(user.id),
            duration_ms=int((perf_counter() - start) * 1000),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    # Spec 018 W4.T13 — embed resolved permissions in the JWT so downstream
    # middleware / deps don't need to re-resolve them on every request.
    perms = sorted(get_permissions(user))
    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "permissions": perms,
    })
    await publish_audit(
        action_type="WRITE",
        action_name="user_login",
        entity_type="User",
        entity_id=str(user.id),
        method="POST",
        path=str(request.url.path),
        response_status=200,
        user_id=str(user.id),
        duration_ms=int((perf_counter() - start) * 1000),
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        permissions=perms,
    )


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    # Pydantic's `from_attributes` can't pick `permissions` off the SQLAlchemy
    # User (it's not a column) — build the response explicitly.
    perms = sorted(get_permissions(current_user))
    return UserOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        permissions=perms,
    )
