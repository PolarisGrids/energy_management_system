#!/usr/bin/env python3
"""Polaris EMS synthetic probe runner (spec 018, W5.T49).

Reads ``probes.yaml`` next to this file, issues one GET per probe, and emits
OTLP metrics to the OTel Collector gRPC endpoint configured via
``OTEL_COLLECTOR_ENDPOINT`` (defaults to the in-cluster DaemonSet service).

Environment:
    PROBE_BASE_URL              e.g. https://vidyut360.dev.polagram.in
    PROBE_AUTH_TOKEN            JWT used for ``auth: bearer`` probes (optional)
    OTEL_COLLECTOR_ENDPOINT     OTLP gRPC endpoint
    DEPLOY_ENV                  dev | stag | prod (resource attribute)
    PROBE_TIMEOUT_SECONDS       overrides default_timeout_seconds

Exits 0 on successful *run* (even if individual probes failed — failures are
visible in metrics). Exits 2 on configuration errors.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

SERVICE_NAME = "polaris-ems-synthetic-probe"
DEFAULT_OTEL_ENDPOINT = "http://otel-collector.observability.svc.cluster.local:4317"


@dataclass
class ProbeSpec:
    name: str
    path: str
    auth: str
    expected_status: list[int]
    body_contains: str | None
    timeout_seconds: float
    critical: bool


def _load_config(path: Path) -> tuple[str, list[ProbeSpec], float]:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    base_url_env = raw.get("base_url_env", "PROBE_BASE_URL")
    base_url = os.environ.get(base_url_env)
    if not base_url:
        print(
            f"FATAL: {base_url_env} env var is not set; cannot resolve target",
            file=sys.stderr,
        )
        sys.exit(2)

    default_timeout = float(
        os.environ.get("PROBE_TIMEOUT_SECONDS")
        or raw.get("default_timeout_seconds", 10)
    )

    specs: list[ProbeSpec] = []
    for item in raw.get("probes", []):
        exp = item.get("expected_status", 200)
        if isinstance(exp, int):
            exp = [exp]
        specs.append(
            ProbeSpec(
                name=item["name"],
                path=item["path"],
                auth=item.get("auth", "none"),
                expected_status=[int(x) for x in exp],
                body_contains=item.get("body_contains"),
                timeout_seconds=float(item.get("timeout_seconds", default_timeout)),
                critical=bool(item.get("critical", False)),
            )
        )
    return base_url.rstrip("/"), specs, default_timeout


def _init_meter_provider() -> MeterProvider:
    endpoint = os.environ.get("OTEL_COLLECTOR_ENDPOINT", DEFAULT_OTEL_ENDPOINT)
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "deployment.environment": os.environ.get("DEPLOY_ENV", "dev"),
        }
    )
    exporter = OTLPMetricExporter(endpoint=endpoint, insecure=endpoint.startswith("http://"))
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5_000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider


def _classify_result(
    spec: ProbeSpec, status: int, body_sample: str, elapsed_s: float
) -> tuple[str, str | None]:
    """Return (result, reason) where result is 'pass'|'fail'|'timeout'."""
    if status == 0:
        return "timeout", "request_error"
    if status not in spec.expected_status:
        return "fail", f"unexpected_status:{status}"
    if spec.body_contains and spec.body_contains not in body_sample:
        return "fail", "body_mismatch"
    if elapsed_s > spec.timeout_seconds:
        return "fail", "slo_exceeded"
    return "pass", None


def run(probes_path: Path) -> int:
    base_url, specs, _ = _load_config(probes_path)
    provider = _init_meter_provider()
    meter = metrics.get_meter(SERVICE_NAME)

    duration_hist = meter.create_histogram(
        "ems_synthetic_probe_duration_seconds",
        unit="s",
        description="Probe request duration",
    )
    errors_counter = meter.create_counter(
        "ems_synthetic_probe_errors_total",
        description="Probe failures (non-pass outcomes)",
    )
    up_gauge = meter.create_observable_gauge(
        "ems_synthetic_probe_up",
        callbacks=[],
        description="1 if last probe run passed, else 0",
    )
    # Observable gauge callbacks are hard to thread through a one-shot cron
    # invocation; instead we also emit a synchronous up counter as a bool
    # via `errors_counter`/`duration_hist` label `result=pass|fail|timeout`.
    _ = up_gauge  # reserved for a future long-running daemon mode

    token = os.environ.get("PROBE_AUTH_TOKEN", "")
    any_critical_failed = False
    results: list[dict[str, Any]] = []

    with httpx.Client(
        base_url=base_url,
        headers={"User-Agent": "polaris-ems-synthetic-probe/1.0"},
        follow_redirects=False,
        verify=os.environ.get("PROBE_TLS_VERIFY", "true").lower() != "false",
    ) as client:
        for spec in specs:
            headers: dict[str, str] = {}
            if spec.auth == "bearer" and token:
                headers["Authorization"] = f"Bearer {token}"

            start = time.perf_counter()
            status = 0
            body_sample = ""
            try:
                resp = client.get(spec.path, headers=headers, timeout=spec.timeout_seconds)
                status = resp.status_code
                body_sample = resp.text[:2048]
            except httpx.TimeoutException:
                status = 0
                body_sample = ""
            except httpx.HTTPError as exc:
                status = 0
                body_sample = f"error:{type(exc).__name__}"
            elapsed = time.perf_counter() - start

            result, reason = _classify_result(spec, status, body_sample, elapsed)
            attrs = {
                "endpoint": spec.name,
                "method": "GET",
                "status": str(status),
                "result": result,
            }
            duration_hist.record(elapsed, attrs)
            if result != "pass":
                errors_counter.add(
                    1,
                    {
                        "endpoint": spec.name,
                        "method": "GET",
                        "reason": reason or "unknown",
                    },
                )
                if spec.critical:
                    any_critical_failed = True
            results.append(
                {
                    "endpoint": spec.name,
                    "status": status,
                    "result": result,
                    "reason": reason,
                    "duration_s": round(elapsed, 4),
                    "critical": spec.critical,
                }
            )

    # stdout line for kubectl logs / Loki ingestion
    print(
        json.dumps(
            {
                "probe_run": {
                    "service": SERVICE_NAME,
                    "base_url": base_url,
                    "results": results,
                    "critical_failure": any_critical_failed,
                }
            }
        )
    )

    # Flush metrics before exit; CronJob will tear down the pod
    try:
        provider.force_flush(timeout_millis=5_000)
        provider.shutdown()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    default_cfg = Path(__file__).with_name("probes.yaml")
    cfg_path = Path(os.environ.get("PROBE_CONFIG_PATH", str(default_cfg)))
    sys.exit(run(cfg_path))
