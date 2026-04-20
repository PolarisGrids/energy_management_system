"""
/api/v1/mdms/* pass-through to MDMS (spec 018 W1.T3).

See `specs/018-smoc-ems-full-compliance/contracts/mdms-integration.md` for the
full upstream surface. This module intentionally does NOT attempt to model
every backing MDMS endpoint — MDMS owns the contract and EMS forwards every
method transparently so changes land without redeploying EMS.
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
async def mdms_proxy(path: str, request: Request, _: User = Depends(get_current_user)) -> Response:
    return await proxy_request(
        request,
        base_url=settings.MDMS_BASE_URL,
        upstream_path=f"/{path}",
        integration_flag_name="MDMS_ENABLED",
        integration_name="mdms",
        api_key=settings.MDMS_API_KEY,
        connect_timeout=settings.MDMS_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.MDMS_READ_TIMEOUT_SECONDS,
    )
