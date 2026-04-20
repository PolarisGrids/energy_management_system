"""Python algorithm sandbox runner — spec 018 W4.T7.

Decision (research.md W4.T7):
    RestrictedPython (Zope) with a stripped globals environment. No file,
    network, or process access. Per-call timeout enforced via a worker
    thread + join. Errors return a structured response (never escape).

Contract
--------

    run(source: str, inputs: dict, timeout_s: float = 5.0) -> dict

Returned shape:

    {
      "status": "ok" | "error" | "timeout",
      "result": Any | None,
      "stdout": str,
      "error":  str | None,
      "duration_ms": int,
    }

The algorithm source MUST define a top-level ``main(inputs)`` callable.
``inputs`` is a plain dict. The return value of ``main`` is placed on
``result``. ``print`` writes to the captured ``stdout``.

RestrictedPython is an optional dep — if missing, the runner falls back to
a bare ``compile(..., "exec")`` with the same guarded globals. The guard
still blocks network / filesystem / subprocess / dynamic-import attempts,
but it is NOT a security boundary; RestrictedPython must be installed in
dev/prod deployments.
"""
from __future__ import annotations

import builtins
import io
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ── RestrictedPython import is optional (graceful local fallback). ──
try:
    from RestrictedPython import compile_restricted, safe_builtins, limited_builtins
    from RestrictedPython.Eval import (
        default_guarded_getiter,
        default_guarded_getitem,
    )
    from RestrictedPython.Guards import (
        guarded_iter_unpack_sequence,
        guarded_unpack_sequence,
        safer_getattr,
    )

    HAS_RESTRICTED = True
except Exception:  # pragma: no cover
    HAS_RESTRICTED = False
    compile_restricted = None  # type: ignore
    safe_builtins = {}  # type: ignore
    limited_builtins = {}  # type: ignore


# ── Allowed builtins — deliberately narrow. ──
# Everything the typical widget-logic / stats / math algorithm might need,
# without I/O, introspection, or dynamic import.
_ALLOWED_BUILTIN_NAMES = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "int",
    "len",
    "list",
    "map",
    "max",
    "min",
    "pow",
    "print",
    "range",
    "reversed",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
    "True",
    "False",
    "None",
}

_FORBIDDEN_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "input",
    "breakpoint",
    "__import__",
    "exit",
    "quit",
    "globals",
    "locals",
    "vars",
    "getattr",  # replaced by safer_getattr in RestrictedPython mode
    "setattr",
    "delattr",
    "memoryview",
    "help",
}


def _build_safe_builtins() -> Dict[str, Any]:
    """Filter stdlib builtins down to a safe subset."""
    allowed = {}
    for name in _ALLOWED_BUILTIN_NAMES:
        if hasattr(builtins, name):
            allowed[name] = getattr(builtins, name)
    # Replace ``print`` with a captured-sink ``print`` — actual binding
    # happens in ``_run_inline`` so stdout is redirected cleanly.
    return allowed


class SandboxError(Exception):
    """Raised for any sandbox-violation or compilation failure."""


def _reject_forbidden_tokens(source: str) -> None:
    """Fast syntactic guard for the most obvious escapes.

    This is belt-and-braces on top of RestrictedPython; even without the
    library installed the runner rejects attempts to call well-known escape
    hatches. Not a security boundary on its own.
    """
    # Very naive token scan; RestrictedPython does the heavy lifting.
    for forbidden in (
        "__import__",
        "__class__",
        "__bases__",
        "__subclasses__",
        "__globals__",
        "__builtins__",
        "__code__",
        "__dict__",
        "__getattribute__",
    ):
        if forbidden in source:
            raise SandboxError(f"forbidden identifier: {forbidden}")


def _compile(source: str):
    """Compile to a code object, preferring RestrictedPython."""
    _reject_forbidden_tokens(source)
    if HAS_RESTRICTED:
        code = compile_restricted(source, filename="<algorithm>", mode="exec")
        if code is None:
            raise SandboxError(
                "RestrictedPython rejected the source (compile returned None)"
            )
        return code
    # Fallback — plain compile. Not secure on its own; the caller should
    # install RestrictedPython in any non-local env.
    logger.warning(
        "algorithm_runner: RestrictedPython missing — falling back to plain compile"
    )
    return compile(source, "<algorithm>", "exec")


def _build_globals() -> Dict[str, Any]:
    """Assemble the execution globals dict passed to ``exec``."""
    if HAS_RESTRICTED:
        # RestrictedPython requires specific helper names in globals.
        g: Dict[str, Any] = {
            "__builtins__": {**safe_builtins, **limited_builtins, **_build_safe_builtins()},
            "_getiter_": default_guarded_getiter,
            "_getitem_": default_guarded_getitem,
            "_getattr_": safer_getattr,
            "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
            "_unpack_sequence_": guarded_unpack_sequence,
            # Allow in-place operators (x += 1) via RestrictedPython helpers.
            "_inplacevar_": lambda op, x, y: _INPLACE[op](x, y),
            "_write_": lambda x: x,  # no-op; we don't guard attribute writes
        }
    else:
        g = {"__builtins__": _build_safe_builtins()}

    # Explicitly strip dangerous names in case a fallback build leaked them.
    for f in _FORBIDDEN_NAMES:
        g["__builtins__"].pop(f, None)  # type: ignore[union-attr]
    return g


# Mapping used by RestrictedPython's `_inplacevar_` helper.
_INPLACE = {
    "+=": lambda a, b: a + b,
    "-=": lambda a, b: a - b,
    "*=": lambda a, b: a * b,
    "/=": lambda a, b: a / b,
    "//=": lambda a, b: a // b,
    "%=": lambda a, b: a % b,
    "**=": lambda a, b: a ** b,
    "<<=": lambda a, b: a << b,
    ">>=": lambda a, b: a >> b,
    "&=": lambda a, b: a & b,
    "|=": lambda a, b: a | b,
    "^=": lambda a, b: a ^ b,
}


# ── Core runner ──


def _run_inline(
    source: str, inputs: Dict[str, Any], stdout_sink: io.StringIO
) -> Dict[str, Any]:
    """Synchronously compile + execute the algorithm in a guarded namespace.

    We do NOT use ``contextlib.redirect_stdout`` here because it mutates
    ``sys.stdout`` globally and therefore blocks thread-local reasoning
    (the main thread's stdout would be redirected too, deadlocking other
    writers). Instead we inject a captured ``print`` into the sandboxed
    builtins so output is collected without touching ``sys.stdout``.
    """
    code = _compile(source)
    g = _build_globals()
    g["inputs"] = inputs

    def _captured_print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        stdout_sink.write(sep.join(str(a) for a in args) + end)

    # Install the captured ``print`` into the sandbox builtins.
    bi = g.get("__builtins__")
    if isinstance(bi, dict):
        bi["print"] = _captured_print

    exec(code, g)  # noqa: S102 — intentional sandboxed exec
    main: Optional[Callable] = g.get("main")
    if main is None or not callable(main):
        raise SandboxError("algorithm source must define a callable main(inputs)")
    return main(inputs)


def run(
    source: str,
    inputs: Optional[Dict[str, Any]] = None,
    timeout_s: float = 5.0,
) -> Dict[str, Any]:
    """Execute ``source`` in the sandbox. Returns structured result dict.

    Never raises — errors / timeouts are returned in the response envelope.
    """
    inputs = inputs or {}
    stdout_sink = io.StringIO()
    result_holder: Dict[str, Any] = {}
    err_holder: Dict[str, str] = {}
    start = time.perf_counter()

    def _target():
        try:
            result_holder["value"] = _run_inline(source, inputs, stdout_sink)
        except SandboxError as se:
            err_holder["error"] = f"SandboxError: {se}"
        except SyntaxError as se:
            err_holder["error"] = f"SyntaxError: {se}"
        except Exception as exc:  # noqa: BLE001
            err_holder["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)
    duration_ms = int((time.perf_counter() - start) * 1000)

    if thread.is_alive():
        # NOTE: CPython has no safe way to kill a thread; the daemon thread
        # will continue running until it returns or the process exits. For a
        # hard kill, a subprocess-based runner would be needed — tracked in
        # research.md as a follow-up.
        return {
            "status": "timeout",
            "result": None,
            "stdout": stdout_sink.getvalue(),
            "error": f"execution exceeded {timeout_s}s timeout",
            "duration_ms": duration_ms,
        }

    if "error" in err_holder:
        return {
            "status": "error",
            "result": None,
            "stdout": stdout_sink.getvalue(),
            "error": err_holder["error"],
            "duration_ms": duration_ms,
        }

    return {
        "status": "ok",
        "result": result_holder.get("value"),
        "stdout": stdout_sink.getvalue(),
        "error": None,
        "duration_ms": duration_ms,
    }
