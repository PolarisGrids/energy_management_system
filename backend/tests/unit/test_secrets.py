"""Unit tests for the AWS secrets loader (W1.T2)."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

from app.core import secrets as secrets_mod


def _fake_settings(**kwargs):
    defaults = dict(
        DEPLOY_ENV="dev",
        AWS_REGION="ap-south-1",
        SECRET_PATHS="",
        HES_API_KEY=None,
        MDMS_API_KEY=None,
        TWILIO_AUTH_TOKEN=None,
        SMTP_PASSWORD=None,
        HES_ENABLED=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_noop_when_boto3_missing():
    s = _fake_settings(SECRET_PATHS="/polaris-ems/dev/HES_API_KEY")
    with patch.object(secrets_mod, "_boto3_available", return_value=False):
        secrets_mod.overlay_secrets(s)
    assert s.HES_API_KEY is None


def test_noop_in_local_env():
    s = _fake_settings(DEPLOY_ENV="local", SECRET_PATHS="/polaris-ems/dev/HES_API_KEY")
    with patch.object(secrets_mod, "_boto3_available", return_value=True), patch.object(
        secrets_mod, "_resolve"
    ) as resolve:
        secrets_mod.overlay_secrets(s)
    resolve.assert_not_called()


def test_ssm_string_payload_is_applied_to_matching_attr():
    s = _fake_settings(SECRET_PATHS="/polaris-ems/dev/HES_API_KEY")
    with patch.object(secrets_mod, "_boto3_available", return_value=True), patch.object(
        secrets_mod, "_resolve", return_value="shh-real-hes-key"
    ):
        secrets_mod.overlay_secrets(s)
    assert s.HES_API_KEY == "shh-real-hes-key"


def test_json_payload_flattens_into_multiple_attrs():
    s = _fake_settings(SECRET_PATHS="/polaris-ems/dev/all-keys")
    payload = '{"hes_api_key": "K1", "mdms_api_key": "K2", "twilio_auth_token": "K3"}'
    with patch.object(secrets_mod, "_boto3_available", return_value=True), patch.object(
        secrets_mod, "_resolve", return_value=payload
    ):
        secrets_mod.overlay_secrets(s)
    assert s.HES_API_KEY == "K1"
    assert s.MDMS_API_KEY == "K2"
    assert s.TWILIO_AUTH_TOKEN == "K3"


def test_bool_coercion_on_overlay():
    s = _fake_settings(SECRET_PATHS="/polaris-ems/dev/HES_ENABLED")
    with patch.object(secrets_mod, "_boto3_available", return_value=True), patch.object(
        secrets_mod, "_resolve", return_value="true"
    ):
        secrets_mod.overlay_secrets(s)
    assert s.HES_ENABLED is True


def test_env_flag_disables_overlay():
    s = _fake_settings(SECRET_PATHS="/polaris-ems/dev/HES_API_KEY")
    os.environ["POLARIS_EMS_DISABLE_SECRETS"] = "1"
    try:
        with patch.object(secrets_mod, "_resolve") as resolve:
            secrets_mod.overlay_secrets(s)
        resolve.assert_not_called()
    finally:
        os.environ.pop("POLARIS_EMS_DISABLE_SECRETS", None)
