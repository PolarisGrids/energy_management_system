"""MDMS EGSM reports proxy — spec 018 W4.T9.

Forwards ``/api/v1/reports/egsm/:category/:report`` → MDMS
``/api/v1/reports/egsm/:category/:report`` via the shared proxy plumbing.
Any query string and request body is forwarded unchanged.

Also exposes the CSV-download poll endpoint:
    ``GET /api/v1/reports/download?id=...``
which hits MDMS's S3+SQS pipeline download-log lookup.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response

from app.api.v1.endpoints._proxy_common import proxy_request
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User

log = logging.getLogger(__name__)

router = APIRouter()


@router.api_route(
    "/egsm/{category}/{report}",
    methods=["GET", "POST"],
)
async def egsm_report_proxy(
    category: str,
    report: str,
    request: Request,
    _: User = Depends(get_current_user),
) -> Response:
    """Proxy to MDMS EGSM report endpoint.

    Upstream path follows `/api/v1/reports/egsm/:category/:report` per
    `contracts/mdms-integration.md` (MDMS catalogues the 6 categories +
    ~52 reports).
    """
    return await proxy_request(
        request,
        base_url=settings.MDMS_BASE_URL,
        upstream_path=f"/api/v1/reports/egsm/{category}/{report}",
        integration_flag_name="MDMS_ENABLED",
        integration_name="mdms",
        api_key=settings.MDMS_API_KEY,
        connect_timeout=settings.MDMS_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.MDMS_READ_TIMEOUT_SECONDS,
    )


@router.get("/download")
async def egsm_report_download_poll(
    request: Request,
    _: User = Depends(get_current_user),
) -> Response:
    """Poll the MDMS CSV download pipeline for a prepared export.

    Takes ``?id=<download_token>`` and returns either a 202 (still generating)
    or a 200 with ``{url: <s3-presigned>}``. Frontend polls until ready then
    surfaces the URL to the user (toast / notification).
    """
    return await proxy_request(
        request,
        base_url=settings.MDMS_BASE_URL,
        upstream_path="/api/v1/reports/download",
        integration_flag_name="MDMS_ENABLED",
        integration_name="mdms",
        api_key=settings.MDMS_API_KEY,
        connect_timeout=settings.MDMS_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.MDMS_READ_TIMEOUT_SECONDS,
    )


@router.get("/categories")
async def egsm_report_categories(
    _: User = Depends(get_current_user),
) -> dict:
    """Static catalogue of the 6 EGSM categories exposed by MDMS.

    Kept static (and cheap) so the frontend can render the navigator without
    waiting on MDMS; the actual report list per category is fetched from
    ``/egsm/:category/index`` upstream.
    """
    return {
        "categories": [
            {"slug": "energy-audit", "name": "Energy Audit"},
            {"slug": "load-management", "name": "Load Management"},
            {"slug": "power-quality", "name": "Power Quality"},
            {"slug": "loss-analytics", "name": "Loss Analytics"},
            {"slug": "reliability-indices", "name": "Reliability Indices"},
            {"slug": "compliance", "name": "Compliance"},
        ]
    }
