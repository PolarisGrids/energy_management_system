"""Unit tests for `/api/v1/health` rollup logic (W1.T10)."""
from __future__ import annotations

import os
from importlib import reload

import pytest


def _reload_with_mode(mode: str):
    os.environ["DEPLOY_ENV"] = "dev"
    os.environ["SSOT_MODE"] = mode
    from app.core import config as _cfg

    reload(_cfg)
    from app.api.v1.endpoints import health as _h

    reload(_h)
    return _h


def _components(db="ok", redis="ok", kafka="ok", hes="ok", mdms="ok"):
    return {
        "db": {"status": db},
        "redis": {"status": redis},
        "kafka": {"status": kafka},
        "hes": {"status": hes},
        "mdms": {"status": mdms},
    }


def test_all_ok_is_ok():
    h = _reload_with_mode("strict")
    assert h._roll_up(_components()) == "ok"


def test_db_fail_is_fail():
    h = _reload_with_mode("mirror")
    assert h._roll_up(_components(db="fail")) == "fail"


def test_strict_mode_mdms_fail_is_fail():
    h = _reload_with_mode("strict")
    assert h._roll_up(_components(mdms="fail")) == "fail"


def test_mirror_mode_mdms_fail_is_degraded():
    h = _reload_with_mode("mirror")
    assert h._roll_up(_components(mdms="fail")) == "degraded"


def test_kafka_fail_is_degraded_in_any_mode():
    h = _reload_with_mode("mirror")
    assert h._roll_up(_components(kafka="fail")) == "degraded"
    h = _reload_with_mode("strict")
    assert h._roll_up(_components(kafka="fail")) == "degraded"
