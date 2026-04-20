"""W4.T10 — scheduled report worker unit tests.

Covers the pure helpers (report_ref parsing, PDF render, notify_change).
Integration-level cron + email tests live in the integration suite with
testcontainers.
"""
from __future__ import annotations

import pytest

from app.services import scheduled_report_worker as srw


def test_report_ref_parse_ok():
    path = srw._report_ref_to_path("egsm:energy-audit:feeder-loss")
    assert path == "/api/v1/reports/egsm/energy-audit/feeder-loss"


def test_report_ref_parse_invalid():
    with pytest.raises(ValueError):
        srw._report_ref_to_path("not-a-ref")
    with pytest.raises(ValueError):
        srw._report_ref_to_path("not-egsm:foo:bar")


def test_render_pdf_returns_bytes():
    pdf = srw._render_pdf("Title", {"key": "value", "rows": [1, 2, 3]})
    assert isinstance(pdf, (bytes, bytearray))
    assert len(pdf) > 50
    # reportlab PDFs start with %PDF-
    if srw.HAS_REPORTLAB:
        assert pdf.startswith(b"%PDF-")


def test_notify_change_noop_without_loop():
    # Should never raise even when no scheduler loop is active.
    srw.notify_change()
