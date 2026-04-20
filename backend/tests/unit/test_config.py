"""Unit tests for the spec-018 feature-flag matrix (W1.T1)."""
from __future__ import annotations

import os
from importlib import reload

import pytest


def _fresh_settings(env: str):
    """Reload config with a specific DEPLOY_ENV, isolated from the process env."""
    # Remove any overrides that would pin a flag to a non-default.
    for k in (
        "SSOT_MODE",
        "HES_ENABLED",
        "MDMS_ENABLED",
        "KAFKA_ENABLED",
        "MDMS_NTL_ENABLED",
        "TARIFF_INCLINING_ENABLED",
        "SMART_INVERTER_COMMANDS_ENABLED",
        "SCHEDULED_REPORTS_ENABLED",
    ):
        os.environ.pop(k, None)
    os.environ["DEPLOY_ENV"] = env
    from app.core import config as _cfg

    reload(_cfg)
    return _cfg


@pytest.mark.parametrize(
    "env,expected",
    [
        (
            "prod",
            dict(
                SSOT_MODE="strict",
                HES_ENABLED=True,
                MDMS_ENABLED=True,
                KAFKA_ENABLED=True,
                MDMS_NTL_ENABLED=True,
                TARIFF_INCLINING_ENABLED=True,
                SMART_INVERTER_COMMANDS_ENABLED=True,
                SCHEDULED_REPORTS_ENABLED=True,
            ),
        ),
        (
            "dev",
            dict(
                SSOT_MODE="mirror",
                HES_ENABLED=True,
                MDMS_ENABLED=True,
                KAFKA_ENABLED=True,
                MDMS_NTL_ENABLED=True,
                TARIFF_INCLINING_ENABLED=True,
                SMART_INVERTER_COMMANDS_ENABLED=True,
                SCHEDULED_REPORTS_ENABLED=True,
            ),
        ),
        (
            "local",
            dict(
                SSOT_MODE="disabled",
                HES_ENABLED=False,
                MDMS_ENABLED=False,
                KAFKA_ENABLED=False,
                MDMS_NTL_ENABLED=False,
                TARIFF_INCLINING_ENABLED=False,
                SMART_INVERTER_COMMANDS_ENABLED=False,
                SCHEDULED_REPORTS_ENABLED=False,
            ),
        ),
    ],
)
def test_env_default_matrix(env, expected):
    cfg = _fresh_settings(env)
    s = cfg.settings
    assert s.SSOT_MODE.value == expected["SSOT_MODE"]
    for k, v in expected.items():
        if k == "SSOT_MODE":
            continue
        assert getattr(s, k) is v, f"{env}: {k} expected {v}, got {getattr(s, k)}"


def test_env_override_wins_over_default():
    """Explicit env var for a flag must NOT be stomped by the env-default overlay."""
    os.environ["DEPLOY_ENV"] = "dev"
    os.environ["HES_ENABLED"] = "false"
    from app.core import config as _cfg

    reload(_cfg)
    try:
        assert _cfg.settings.HES_ENABLED is False
        # But flags not set in env still get the env's default (mirror/dev = true).
        assert _cfg.settings.MDMS_ENABLED is True
    finally:
        os.environ.pop("HES_ENABLED", None)
