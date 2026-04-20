"""Scheduled EGSM-report worker — spec 018 W4.T10.

Design
------
* APScheduler ``AsyncIOScheduler`` running alongside FastAPI.
* Each ``scheduled_report`` row (enabled=1) is installed as a
  ``CronTrigger`` based on ``schedule_cron``.
* When a cron tick fires, ``_execute`` runs:
      1. Call MDMS via ``mdms_client.get(report_ref_path)``.
      2. Render the JSON response to a PDF (reportlab).
      3. Send email to recipients via the notification service (Agent L).
         Fallback: ``smtplib.SMTP`` via ``settings.SMTP_*`` until the
         notification module exposes ``send_email``.
      4. Update ``last_run_at`` / ``last_status`` / ``last_error``.
* ``notify_change()`` is called from the CRUD endpoints to trigger a
  re-sync of the in-memory scheduler.

Report ref conventions
----------------------
``report_ref`` is stored like ``egsm:<category>:<report>``; this is mapped
to ``/api/v1/reports/egsm/<category>/<report>`` when calling MDMS. Any
``params`` are forwarded as the query string.
"""
from __future__ import annotations

import asyncio
import io
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Optional

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.app_builder import ScheduledReport
from app.schemas.app_builder import ScheduledReportRunResult

log = logging.getLogger(__name__)

# ── Optional deps ────────────────────────────────────────────────────────────
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    HAS_APSCHEDULER = True
except Exception:  # pragma: no cover
    HAS_APSCHEDULER = False
    AsyncIOScheduler = None  # type: ignore
    CronTrigger = None  # type: ignore

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdfcanvas

    HAS_REPORTLAB = True
except Exception:  # pragma: no cover
    HAS_REPORTLAB = False

# Notification-service hook (Agent L). Import is best-effort; fall back to
# SMTP if unavailable. TODO(Agent L): swap to notification_service.send_email
# once that API is finalised.
try:
    from app.services import notification_service  # type: ignore

    HAS_NOTIFICATION_SERVICE = True
except Exception:
    notification_service = None  # type: ignore
    HAS_NOTIFICATION_SERVICE = False


# ── Module state ─────────────────────────────────────────────────────────────
_scheduler: Optional["AsyncIOScheduler"] = None
_change_event: asyncio.Event | None = None


def notify_change() -> None:
    """Ping the background loop to reload schedules."""
    ev = _change_event
    if ev is not None:
        try:
            ev.set()
        except Exception:  # pragma: no cover
            pass


# ── MDMS call helper ─────────────────────────────────────────────────────────


def _report_ref_to_path(report_ref: str) -> str:
    """Convert ``egsm:category:report`` → ``/api/v1/reports/egsm/category/report``."""
    parts = report_ref.split(":")
    if len(parts) != 3 or parts[0] != "egsm":
        raise ValueError(f"unsupported report_ref {report_ref!r}")
    _, category, report = parts
    return f"/api/v1/reports/egsm/{category}/{report}"


async def _fetch_report(report_ref: str, params: dict) -> dict:
    """Call MDMS for the report payload. Used by cron runs + run-now."""
    import httpx  # local import; httpx already in requirements

    path = _report_ref_to_path(report_ref)
    headers = {"user-agent": f"polaris-ems/scheduled-report/{settings.APP_NAME}"}
    if settings.MDMS_API_KEY:
        headers["x-api-key"] = settings.MDMS_API_KEY
    async with httpx.AsyncClient(
        base_url=settings.MDMS_BASE_URL,
        timeout=httpx.Timeout(
            connect=settings.MDMS_CONNECT_TIMEOUT_SECONDS,
            read=settings.MDMS_READ_TIMEOUT_SECONDS,
            write=settings.MDMS_READ_TIMEOUT_SECONDS,
            pool=settings.MDMS_READ_TIMEOUT_SECONDS,
        ),
    ) as client:
        resp = await client.get(path, params=params, headers=headers)
    resp.raise_for_status()
    return resp.json()


# ── PDF rendering ────────────────────────────────────────────────────────────


def _render_pdf(title: str, payload: dict) -> bytes:
    """Very simple JSON-to-PDF renderer.

    For demo-grade reports the PDF is a title + readable JSON dump. A richer
    template per report category is tracked in the post-demo backlog.
    """
    if not HAS_REPORTLAB:
        # Plain-text fallback — useful for tests, NOT for prod.
        body = f"{title}\n\n{payload!r}".encode("utf-8")
        return body

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, height - 50, title[:90])
    c.setFont("Helvetica", 9)
    y = height - 80
    # Serialise with json for stable formatting, then wrap long lines.
    import json

    text = json.dumps(payload, indent=2, default=str)
    for line in text.splitlines():
        if y < 40:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = height - 40
        c.drawString(40, y, line[:110])
        y -= 11
    c.showPage()
    c.save()
    return buf.getvalue()


# ── Email delivery ───────────────────────────────────────────────────────────


async def _send_email(
    subject: str, body: str, recipients: list[str], pdf_bytes: bytes, pdf_name: str
) -> int:
    """Dispatch the PDF. Returns count of recipients actually sent."""
    if HAS_NOTIFICATION_SERVICE and hasattr(notification_service, "send_email"):
        # Agent-L integration (future). TODO: confirm exact signature once
        # notification_service lands.
        try:
            await notification_service.send_email(  # type: ignore[attr-defined]
                subject=subject,
                body=body,
                recipients=recipients,
                attachments=[(pdf_name, pdf_bytes, "application/pdf")],
            )
            return len(recipients)
        except Exception as exc:  # pragma: no cover
            log.warning("notification_service.send_email failed, falling back: %s", exc)

    # SMTP fallback
    if not (settings.SMTP_ENABLED and settings.SMTP_USERNAME and settings.SMTP_PASSWORD):
        log.warning("SMTP disabled — skipping email delivery for %s", subject)
        return 0

    def _send_sync() -> int:
        sent = 0
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            for rcpt in recipients:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_USERNAME}>"
                msg["To"] = rcpt
                msg.set_content(body)
                msg.add_attachment(
                    pdf_bytes,
                    maintype="application",
                    subtype="pdf",
                    filename=pdf_name,
                )
                try:
                    smtp.send_message(msg)
                    sent += 1
                except Exception as exc:  # pragma: no cover
                    log.error("failed to send to %s: %s", rcpt, exc)
        return sent

    return await asyncio.to_thread(_send_sync)


# ── Core execution ───────────────────────────────────────────────────────────


async def _execute(row_id: str) -> ScheduledReportRunResult:
    started = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        row = (
            session.query(ScheduledReport)
            .filter(ScheduledReport.id == row_id)
            .first()
        )
        if row is None:
            return ScheduledReportRunResult(
                scheduled_report_id=row_id,
                status="error",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                error="scheduled_report not found",
            )

        try:
            payload = await _fetch_report(row.report_ref, row.params or {})
            pdf_bytes = _render_pdf(row.name, payload)
            body = (
                f"Scheduled report: {row.name}\n"
                f"Ref: {row.report_ref}\n"
                f"Generated at: {started.isoformat()}\n\n"
                "See attached PDF for details."
            )
            pdf_name = f"{row.name.replace(' ', '_')}.pdf"
            sent = await _send_email(
                subject=f"[Polaris EMS] {row.name}",
                body=body,
                recipients=row.recipients or [],
                pdf_bytes=pdf_bytes,
                pdf_name=pdf_name,
            )
            row.last_run_at = started
            row.last_status = "ok"
            row.last_error = None
            session.commit()
            return ScheduledReportRunResult(
                scheduled_report_id=row_id,
                status="ok",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                bytes_sent=len(pdf_bytes),
                recipients_sent=sent,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("scheduled_report %s failed", row_id)
            row.last_run_at = started
            row.last_status = "error"
            row.last_error = f"{type(exc).__name__}: {exc}"[:500]
            session.commit()
            return ScheduledReportRunResult(
                scheduled_report_id=row_id,
                status="error",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                error=str(exc),
            )
    finally:
        session.close()


async def run_once(row_id: str) -> ScheduledReportRunResult:
    """Public helper — execute a schedule immediately (used by run-now)."""
    return await _execute(row_id)


# ── Scheduler lifecycle ──────────────────────────────────────────────────────


async def _sync_jobs() -> None:
    """Rebuild scheduler jobs from the DB."""
    assert _scheduler is not None
    _scheduler.remove_all_jobs()
    session = SessionLocal()
    try:
        rows = (
            session.query(ScheduledReport)
            .filter(ScheduledReport.enabled == 1)
            .all()
        )
        for r in rows:
            try:
                trigger = CronTrigger.from_crontab(r.schedule_cron)
            except Exception as exc:  # pragma: no cover
                log.warning(
                    "invalid cron %r for scheduled_report %s: %s",
                    r.schedule_cron,
                    r.id,
                    exc,
                )
                continue
            _scheduler.add_job(
                _execute,
                trigger=trigger,
                args=[r.id],
                id=f"sr-{r.id}",
                replace_existing=True,
            )
    finally:
        session.close()


async def start() -> None:
    """Boot the APScheduler loop. No-op if APScheduler isn't available."""
    global _scheduler, _change_event
    if not HAS_APSCHEDULER:
        log.warning(
            "APScheduler not installed — scheduled_report worker disabled"
        )
        return
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.start()
    _change_event = asyncio.Event()
    await _sync_jobs()

    async def _watcher():
        assert _change_event is not None
        while True:
            await _change_event.wait()
            _change_event.clear()
            try:
                await _sync_jobs()
            except Exception as exc:  # pragma: no cover
                log.error("scheduled_report watcher sync failed: %s", exc)

    asyncio.create_task(_watcher(), name="scheduled-report-watcher")


async def stop() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
