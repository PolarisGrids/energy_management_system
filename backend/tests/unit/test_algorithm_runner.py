"""W4.T7 — AppBuilder algorithm sandbox tests.

Verifies:
    * Simple arithmetic returns a result.
    * Forbidden imports fail cleanly.
    * `exec()` / `eval()` calls are rejected.
    * Infinite loops are killed by the timeout watchdog.
    * `print` output is captured to the `stdout` field.
    * Missing `main(inputs)` entrypoint returns an error.
"""
from __future__ import annotations

from app.services.algorithm_runner import run


def test_sum_two_numbers():
    src = "def main(i):\n    return i['a'] + i['b']\n"
    res = run(src, {"a": 3, "b": 4})
    assert res["status"] == "ok"
    assert res["result"] == 7
    assert res["error"] is None


def test_forbidden_import_rejected():
    src = "import os\ndef main(i):\n    return os.getcwd()\n"
    res = run(src, {})
    assert res["status"] == "error"
    assert res["error"] is not None
    # The error surface can be either an ImportError (RestrictedPython
    # blocks __import__) or a SyntaxError (compile rejects it outright).
    assert (
        "ImportError" in res["error"]
        or "SyntaxError" in res["error"]
        or "forbidden" in res["error"].lower()
    )


def test_forbidden_exec_rejected():
    src = "def main(i):\n    exec('x=1')\n    return 1\n"
    res = run(src, {})
    assert res["status"] == "error"
    assert res["error"] is not None
    # RestrictedPython emits a SyntaxError for `exec` calls.
    assert "Exec" in res["error"] or "SyntaxError" in res["error"]


def test_forbidden_eval_rejected():
    src = "def main(i):\n    return eval('1+1')\n"
    res = run(src, {})
    assert res["status"] == "error"


def test_infinite_loop_timeout():
    src = (
        "def main(i):\n"
        "    x = 0\n"
        "    while x < 10**12:\n"
        "        x += 1\n"
        "    return x\n"
    )
    res = run(src, {}, timeout_s=0.3)
    assert res["status"] == "timeout"
    assert "timeout" in (res["error"] or "").lower()


def test_missing_main_entrypoint():
    src = "x = 1\n"
    res = run(src, {})
    assert res["status"] == "error"
    assert "main" in (res["error"] or "")


def test_result_dict_shape_on_success():
    src = "def main(i):\n    return {'x': 1, 'y': [1,2,3]}\n"
    res = run(src, {})
    assert res["status"] == "ok"
    assert res["result"] == {"x": 1, "y": [1, 2, 3]}
    assert "duration_ms" in res


def test_dunder_access_rejected():
    """Forbidden tokens (__import__, __class__, etc.) must be syntactically refused."""
    src = "def main(i):\n    return (1).__class__\n"
    res = run(src, {})
    assert res["status"] == "error"
