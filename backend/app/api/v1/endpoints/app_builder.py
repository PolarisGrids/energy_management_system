"""AppBuilder CRUD + publish workflow — spec 018 W4.T6 / W4.T7.

Endpoints
---------

    Apps
      GET    /api/v1/apps
      POST   /api/v1/apps
      GET    /api/v1/apps/{slug}                — latest version (any status)
      GET    /api/v1/apps/{slug}/versions
      GET    /api/v1/apps/{slug}/published
      PUT    /api/v1/apps/{slug}                — new version (DRAFT)
      POST   /api/v1/apps/{slug}/preview
      POST   /api/v1/apps/{slug}/publish        — role-gated
      POST   /api/v1/apps/{slug}/archive
      DELETE /api/v1/apps/{slug}                — archive all versions

    App-scope rules
      GET/POST/PUT/DELETE   /api/v1/app-rules
      POST                  /api/v1/app-rules/{slug}/publish

    Python algorithms
      GET/POST/PUT/DELETE   /api/v1/algorithms
      POST                  /api/v1/algorithms/{slug}/run        — sandbox exec
      POST                  /api/v1/algorithms/{slug}/preview    — same as run
      POST                  /api/v1/algorithms/{slug}/publish

The publish step is gated by the ``require_app_builder_publish`` FastAPI
dependency. Until Agent N's RBAC lands (Wave 4 RBAC track), that dependency
reads the ``X-User-Role`` header as a placeholder. TODO(RBAC): swap for the
real role-lookup when `app.core.rbac` is merged.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.app_builder import (
    AlgorithmDef,
    AppDef,
    PUBLISHABLE_FROM,
    RuleDef,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_PREVIEW,
    STATUS_PUBLISHED,
)
from app.models.user import User
from app.schemas.app_builder import (
    AlgorithmDefCreate,
    AlgorithmDefOut,
    AlgorithmDefUpdate,
    AlgorithmRunRequest,
    AlgorithmRunResponse,
    AppDefCreate,
    AppDefOut,
    AppDefUpdate,
    PublishRequest,
    RuleDefCreate,
    RuleDefOut,
    RuleDefUpdate,
)
from app.services import algorithm_runner

log = logging.getLogger(__name__)


# ── Placeholder RBAC dependency ──
# TODO(RBAC): replace with Agent N's real dep (`app.core.rbac.require_role`)
# once merged. For now we honour an ``X-User-Role`` header so tests and the
# frontend role-gate prototype can drive it.


def require_app_builder_publish(
    x_user_role: Optional[str] = Header(default=None),
    current_user: User = Depends(get_current_user),
) -> User:
    role = (x_user_role or "").strip().lower()
    # ADMIN always passes; the explicit publish role also passes.
    if role in {"app_builder_publish", "admin", "supervisor"}:
        return current_user
    if getattr(current_user, "role", None) and str(current_user.role).lower().endswith(
        "admin"
    ):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": {
                "code": "MISSING_APP_BUILDER_PUBLISH_ROLE",
                "message": "Publishing an app/rule/algorithm requires the "
                "'app_builder_publish' role.",
            }
        },
    )


# ── Helpers ──


def _latest_version(db: Session, model, slug: str):
    return (
        db.query(model)
        .filter(model.slug == slug)
        .order_by(model.version.desc())
        .first()
    )


def _published_row(db: Session, model, slug: str):
    return (
        db.query(model)
        .filter(model.slug == slug, model.status == STATUS_PUBLISHED)
        .order_by(model.version.desc())
        .first()
    )


def _existing_or_404(db: Session, model, slug: str):
    row = _latest_version(db, model, slug)
    if not row:
        raise HTTPException(status_code=404, detail=f"{model.__tablename__} not found")
    return row


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _archive_published_sibling(db: Session, model, slug: str) -> None:
    """Ensure only one PUBLISHED row per slug by archiving the current one."""
    existing = _published_row(db, model, slug)
    if existing:
        existing.status = STATUS_ARCHIVED


# ── Routers ────────────────────────────────────────────────────────────────


apps_router = APIRouter(prefix="/apps", tags=["app-builder-apps"])
rules_router = APIRouter(prefix="/app-rules", tags=["app-builder-rules"])
algos_router = APIRouter(prefix="/algorithms", tags=["app-builder-algorithms"])


# ─────────────────────────── Apps ───────────────────────────


@apps_router.get("", response_model=List[AppDefOut])
def list_apps(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return latest version per slug (optionally filtered by status)."""
    q = db.query(AppDef)
    if status_filter:
        q = q.filter(AppDef.status == status_filter.upper())
    rows = q.order_by(AppDef.slug, AppDef.version.desc()).all()
    # Collapse to latest per slug
    seen: set[str] = set()
    out: list[AppDef] = []
    for r in rows:
        if r.slug in seen:
            continue
        seen.add(r.slug)
        out.append(r)
    return out


@apps_router.post("", response_model=AppDefOut, status_code=201)
def create_app(
    payload: AppDefCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if _latest_version(db, AppDef, payload.slug):
        raise HTTPException(status_code=409, detail="slug already exists")
    row = AppDef(
        id=_uuid(),
        slug=payload.slug,
        version=1,
        name=payload.name,
        description=payload.description,
        author_user_id=str(current_user.id),
        status=STATUS_DRAFT,
        definition=payload.definition,
        required_role=payload.required_role,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@apps_router.get("/{slug}", response_model=AppDefOut)
def get_app_latest(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _existing_or_404(db, AppDef, slug)


@apps_router.get("/{slug}/versions", response_model=List[AppDefOut])
def list_app_versions(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(AppDef)
        .filter(AppDef.slug == slug)
        .order_by(AppDef.version.desc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="app not found")
    return rows


@apps_router.get("/{slug}/published", response_model=AppDefOut)
def get_app_published(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = _published_row(db, AppDef, slug)
    if not row:
        raise HTTPException(status_code=404, detail="no published version")
    return row


@apps_router.put("/{slug}", response_model=AppDefOut)
def update_app(
    slug: str,
    payload: AppDefUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new DRAFT version incrementing the latest version number."""
    latest = _existing_or_404(db, AppDef, slug)
    new_row = AppDef(
        id=_uuid(),
        slug=slug,
        version=latest.version + 1,
        name=payload.name or latest.name,
        description=payload.description
        if payload.description is not None
        else latest.description,
        author_user_id=str(current_user.id),
        status=STATUS_DRAFT,
        definition=payload.definition if payload.definition is not None else latest.definition,
        required_role=payload.required_role
        if payload.required_role is not None
        else latest.required_role,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


@apps_router.post("/{slug}/preview", response_model=AppDefOut)
def preview_app(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = _existing_or_404(db, AppDef, slug)
    if row.status not in (STATUS_DRAFT, STATUS_PREVIEW):
        raise HTTPException(
            status_code=409,
            detail=f"cannot preview from status {row.status}",
        )
    row.status = STATUS_PREVIEW
    db.commit()
    db.refresh(row)
    return row


@apps_router.post("/{slug}/publish", response_model=AppDefOut)
def publish_app(
    slug: str,
    payload: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_app_builder_publish),
):
    row = _existing_or_404(db, AppDef, slug)
    if row.status not in PUBLISHABLE_FROM:
        raise HTTPException(
            status_code=409,
            detail=f"cannot publish from status {row.status}",
        )
    _archive_published_sibling(db, AppDef, slug)
    row.status = STATUS_PUBLISHED
    row.published_at = _now()
    row.approved_by = str(current_user.id)
    db.commit()
    db.refresh(row)
    return row


@apps_router.post("/{slug}/archive", response_model=AppDefOut)
def archive_app(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_app_builder_publish),
):
    row = _existing_or_404(db, AppDef, slug)
    row.status = STATUS_ARCHIVED
    db.commit()
    db.refresh(row)
    return row


@apps_router.delete("/{slug}", status_code=204)
def delete_app(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_app_builder_publish),
):
    rows = db.query(AppDef).filter(AppDef.slug == slug).all()
    if not rows:
        raise HTTPException(status_code=404, detail="app not found")
    for r in rows:
        r.status = STATUS_ARCHIVED
    db.commit()


# ─────────────────────────── App-scope Rules ───────────────────────────


@rules_router.get("", response_model=List[RuleDefOut])
def list_rules(
    app_slug: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(RuleDef)
    if app_slug:
        q = q.filter(RuleDef.app_slug == app_slug)
    if status_filter:
        q = q.filter(RuleDef.status == status_filter.upper())
    rows = q.order_by(RuleDef.slug, RuleDef.version.desc()).all()
    seen: set[str] = set()
    out = []
    for r in rows:
        if r.slug in seen:
            continue
        seen.add(r.slug)
        out.append(r)
    return out


@rules_router.post("", response_model=RuleDefOut, status_code=201)
def create_rule(
    payload: RuleDefCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if _latest_version(db, RuleDef, payload.slug):
        raise HTTPException(status_code=409, detail="slug already exists")
    row = RuleDef(
        id=_uuid(),
        slug=payload.slug,
        version=1,
        name=payload.name,
        author_user_id=str(current_user.id),
        status=STATUS_DRAFT,
        definition=payload.definition,
        app_slug=payload.app_slug,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@rules_router.get("/{slug}", response_model=RuleDefOut)
def get_rule(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _existing_or_404(db, RuleDef, slug)


@rules_router.put("/{slug}", response_model=RuleDefOut)
def update_rule(
    slug: str,
    payload: RuleDefUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    latest = _existing_or_404(db, RuleDef, slug)
    row = RuleDef(
        id=_uuid(),
        slug=slug,
        version=latest.version + 1,
        name=payload.name or latest.name,
        author_user_id=str(current_user.id),
        status=STATUS_DRAFT,
        definition=payload.definition if payload.definition is not None else latest.definition,
        app_slug=payload.app_slug if payload.app_slug is not None else latest.app_slug,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@rules_router.post("/{slug}/publish", response_model=RuleDefOut)
def publish_rule(
    slug: str,
    payload: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_app_builder_publish),
):
    row = _existing_or_404(db, RuleDef, slug)
    if row.status not in PUBLISHABLE_FROM:
        raise HTTPException(
            status_code=409, detail=f"cannot publish from status {row.status}"
        )
    _archive_published_sibling(db, RuleDef, slug)
    row.status = STATUS_PUBLISHED
    row.published_at = _now()
    row.approved_by = str(current_user.id)
    db.commit()
    db.refresh(row)
    return row


@rules_router.delete("/{slug}", status_code=204)
def delete_rule(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_app_builder_publish),
):
    rows = db.query(RuleDef).filter(RuleDef.slug == slug).all()
    if not rows:
        raise HTTPException(status_code=404, detail="rule not found")
    for r in rows:
        r.status = STATUS_ARCHIVED
    db.commit()


# ─────────────────────────── Algorithms ───────────────────────────


@algos_router.get("", response_model=List[AlgorithmDefOut])
def list_algorithms(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(AlgorithmDef)
        .order_by(AlgorithmDef.slug, AlgorithmDef.version.desc())
        .all()
    )
    seen: set[str] = set()
    out = []
    for r in rows:
        if r.slug in seen:
            continue
        seen.add(r.slug)
        out.append(r)
    return out


@algos_router.post("", response_model=AlgorithmDefOut, status_code=201)
def create_algorithm(
    payload: AlgorithmDefCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if _latest_version(db, AlgorithmDef, payload.slug):
        raise HTTPException(status_code=409, detail="slug already exists")
    row = AlgorithmDef(
        id=_uuid(),
        slug=payload.slug,
        version=1,
        name=payload.name,
        description=payload.description,
        author_user_id=str(current_user.id),
        status=STATUS_DRAFT,
        source=payload.source,
        definition=payload.definition,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@algos_router.get("/{slug}", response_model=AlgorithmDefOut)
def get_algorithm(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _existing_or_404(db, AlgorithmDef, slug)


@algos_router.get("/{slug}/versions", response_model=List[AlgorithmDefOut])
def list_algorithm_versions(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(AlgorithmDef)
        .filter(AlgorithmDef.slug == slug)
        .order_by(AlgorithmDef.version.desc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="algorithm not found")
    return rows


@algos_router.put("/{slug}", response_model=AlgorithmDefOut)
def update_algorithm(
    slug: str,
    payload: AlgorithmDefUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    latest = _existing_or_404(db, AlgorithmDef, slug)
    row = AlgorithmDef(
        id=_uuid(),
        slug=slug,
        version=latest.version + 1,
        name=payload.name or latest.name,
        description=payload.description
        if payload.description is not None
        else latest.description,
        author_user_id=str(current_user.id),
        status=STATUS_DRAFT,
        source=payload.source if payload.source is not None else latest.source,
        definition=payload.definition
        if payload.definition is not None
        else latest.definition,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@algos_router.post("/{slug}/run", response_model=AlgorithmRunResponse)
def run_algorithm(
    slug: str,
    payload: AlgorithmRunRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Execute the latest version in the sandbox. Used for Preview + REST runs."""
    row = _existing_or_404(db, AlgorithmDef, slug)
    res = algorithm_runner.run(
        row.source,
        inputs=payload.inputs,
        timeout_s=payload.timeout_seconds,
    )
    return AlgorithmRunResponse(**res)


@algos_router.post("/{slug}/preview", response_model=AlgorithmDefOut)
def preview_algorithm(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = _existing_or_404(db, AlgorithmDef, slug)
    if row.status not in (STATUS_DRAFT, STATUS_PREVIEW):
        raise HTTPException(
            status_code=409, detail=f"cannot preview from status {row.status}"
        )
    row.status = STATUS_PREVIEW
    db.commit()
    db.refresh(row)
    return row


@algos_router.post("/{slug}/publish", response_model=AlgorithmDefOut)
def publish_algorithm(
    slug: str,
    payload: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_app_builder_publish),
):
    row = _existing_or_404(db, AlgorithmDef, slug)
    if row.status not in PUBLISHABLE_FROM:
        raise HTTPException(
            status_code=409, detail=f"cannot publish from status {row.status}"
        )
    _archive_published_sibling(db, AlgorithmDef, slug)
    row.status = STATUS_PUBLISHED
    row.published_at = _now()
    row.approved_by = str(current_user.id)
    db.commit()
    db.refresh(row)
    return row


@algos_router.delete("/{slug}", status_code=204)
def delete_algorithm(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_app_builder_publish),
):
    rows = db.query(AlgorithmDef).filter(AlgorithmDef.slug == slug).all()
    if not rows:
        raise HTTPException(status_code=404, detail="algorithm not found")
    for r in rows:
        r.status = STATUS_ARCHIVED
    db.commit()
