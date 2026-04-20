"""Small helper: extract current OTel trace_id as 32-char hex.

If OpenTelemetry is not initialised (dev / unit test), returns None so callers
can happily persist NULL into command_log.trace_id.
"""
from __future__ import annotations

from typing import Optional


def current_trace_id() -> Optional[str]:
    try:
        from opentelemetry import trace  # type: ignore
    except Exception:  # pragma: no cover
        return None
    span = trace.get_current_span()
    if span is None:
        return None
    ctx = span.get_span_context()
    if not getattr(ctx, "is_valid", False):
        return None
    return format(ctx.trace_id, "032x")
