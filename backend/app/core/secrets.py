"""
AWS Parameter Store / Secrets Manager loader (spec 018 W1.T2).

Resolves secret values at process start and overlays them onto the pydantic
`Settings` object. Supports two path families:

* ``/...``   → AWS SSM Parameter Store path (GetParameter WithDecryption=True)
* ``arn:aws:secretsmanager:...`` or bare secret-name → Secrets Manager

When the process runs without AWS credentials (local dev, CI), this module is a
no-op; ``Settings`` keeps whatever it read from ``.env`` / process env.

Config-side plumbing:

* ``SECRET_PATHS`` (colon-separated) lists the identifiers to preload.
* Each identifier's *last path segment* (or the secret ID itself) is uppercased
  and used as the ``Settings`` attribute name. Example::

      SECRET_PATHS="/polaris-ems/dev/HES_API_KEY:/polaris-ems/dev/MDMS_API_KEY"

  will populate ``settings.HES_API_KEY`` and ``settings.MDMS_API_KEY``.

* A secret value that is JSON (``{"key": "val"}``) is flattened: each object
  key becomes a `Settings` attribute (uppercased).

The module is deliberately tolerant: any single fetch error is logged and
skipped. Missing optional secrets must not crash startup — the integration
layer is already feature-flagged.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_BOTO3_AVAILABLE: bool | None = None


def _boto3_available() -> bool:
    global _BOTO3_AVAILABLE
    if _BOTO3_AVAILABLE is not None:
        return _BOTO3_AVAILABLE
    try:  # pragma: no cover — depends on runtime env
        import boto3  # noqa: F401

        _BOTO3_AVAILABLE = True
    except Exception:
        _BOTO3_AVAILABLE = False
    return _BOTO3_AVAILABLE


def _ssm_client(region: str):
    import boto3  # type: ignore

    return boto3.client("ssm", region_name=region)


def _secrets_client(region: str):
    import boto3  # type: ignore

    return boto3.client("secretsmanager", region_name=region)


def _fetch_ssm(path: str, region: str) -> str | None:
    try:
        resp = _ssm_client(region).get_parameter(Name=path, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception as exc:  # pragma: no cover — network
        logger.warning("ssm fetch failed for %s: %s", path, exc)
        return None


def _fetch_secret(identifier: str, region: str) -> str | None:
    try:
        resp = _secrets_client(region).get_secret_value(SecretId=identifier)
        return resp.get("SecretString") or resp.get("SecretBinary")
    except Exception as exc:  # pragma: no cover — network
        logger.warning("secretsmanager fetch failed for %s: %s", identifier, exc)
        return None


def _resolve(identifier: str, region: str) -> Any:
    """Return the secret's raw string (or None). Caller decides JSON-parse."""
    if identifier.startswith("/"):
        return _fetch_ssm(identifier, region)
    # Everything else goes through Secrets Manager (ARN or bare name).
    return _fetch_secret(identifier, region)


def _attr_name(identifier: str) -> str:
    """Derive a Settings attr name from the secret's last path segment."""
    tail = identifier.rstrip("/").split("/")[-1]
    # arn:aws:secretsmanager:<region>:<acct>:secret:<name>-<suffix>
    if tail.startswith("secret:"):
        tail = tail.split(":", 1)[-1]
    # strip the random Secrets Manager suffix if present (-abc123)
    if "-" in tail and len(tail.rsplit("-", 1)[-1]) == 6:
        tail = tail.rsplit("-", 1)[0]
    return tail.upper().replace("-", "_")


def _apply(settings: "Settings", key: str, value: Any) -> None:
    if not hasattr(settings, key):
        logger.info("secrets: skip unknown settings attr %s", key)
        return
    current = type(getattr(settings, key, None))
    # Coerce bools / ints if the field expects them.
    if current is bool and isinstance(value, str):
        value = value.strip().lower() in {"1", "true", "yes", "on"}
    elif current is int and isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    setattr(settings, key, value)
    logger.debug("secrets: overlaid %s", key)


def overlay_secrets(settings: "Settings") -> None:
    """Pull each ``SECRET_PATHS`` identifier and overlay it onto ``settings``.

    Called exactly once from ``app.core.config._load_settings()``.
    """
    env_flag = os.environ.get("POLARIS_EMS_DISABLE_SECRETS", "").lower()
    if env_flag in {"1", "true", "yes"}:
        return
    if getattr(settings, "DEPLOY_ENV", None) and str(settings.DEPLOY_ENV) == "local":
        # Local dev uses .env only.
        return
    if not _boto3_available():
        logger.info("boto3 unavailable; skipping secrets overlay")
        return

    region = getattr(settings, "AWS_REGION", "ap-south-1")
    paths = (getattr(settings, "SECRET_PATHS", "") or "").strip()
    if not paths:
        return

    for identifier in [p.strip() for p in paths.split(":") if p.strip()]:
        raw = _resolve(identifier, region)
        if raw is None:
            continue
        # JSON payload? flatten to multiple settings attributes.
        try:
            payload = json.loads(raw) if isinstance(raw, str) else None
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            for k, v in payload.items():
                _apply(settings, str(k).upper().replace("-", "_"), v)
        else:
            _apply(settings, _attr_name(identifier), raw)
