"""
/api/v1/hes/* pass-through to HES routing-service (spec 018 W1.T4).

Uses the same trace-context + feature-flag gating helpers as the MDMS proxy.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.api.v1.endpoints._proxy_common import proxy_request
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def hes_proxy(path: str, request: Request, _: User = Depends(get_current_user)) -> Response:
    return await proxy_request(
        request,
        base_url=settings.HES_BASE_URL,
        upstream_path=f"/{path}",
        integration_flag_name="HES_ENABLED",
        integration_name="hes",
        api_key=settings.HES_API_KEY,
        connect_timeout=settings.HES_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.HES_READ_TIMEOUT_SECONDS,
    )
