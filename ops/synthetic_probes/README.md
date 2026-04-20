# Polaris EMS — Synthetic probe suite (spec 018 W5.T49)

Every 5 minutes a Kubernetes CronJob runs `probe.py`, which reads
`probes.yaml`, hits ~10 critical Polaris EMS endpoints, and emits OTLP
metrics to the observability OTel Collector DaemonSet.

## Metrics emitted

| Metric | Type | Labels |
| --- | --- | --- |
| `ems_synthetic_probe_duration_seconds` | histogram | `endpoint`, `method`, `status`, `result` |
| `ems_synthetic_probe_errors_total` | counter | `endpoint`, `method`, `reason` |

`result` is one of `pass` / `fail` / `timeout`.
`reason` is `unexpected_status:<code>`, `body_mismatch`, `slo_exceeded`, or `request_error`.

## Layout

```
ops/
  synthetic_probes/
    probes.yaml             # probe definitions (edit this to add/remove)
    probe.py                # runner
    requirements.txt        # pip deps
    Dockerfile              # container image
  k8s/
    synthetic-probe-cronjob.yaml
  grafana/
    polaris-ems-probes.json
```

## Local dry-run

```bash
cd ops/synthetic_probes
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export PROBE_BASE_URL=http://localhost:8000
export OTEL_COLLECTOR_ENDPOINT=http://localhost:4317    # or any OTLP sink
export PROBE_AUTH_TOKEN=<dev-jwt>                       # optional
python probe.py
```

The runner prints a JSON line summarizing the run to stdout; metrics flow
to the OTel Collector.

## Deploy

```bash
docker build -t <registry>/polaris-ems-synthetic-probe:<tag> ops/synthetic_probes/
docker push <registry>/polaris-ems-synthetic-probe:<tag>

# Create the bearer-token secret once:
kubectl -n polaris-ems create secret generic polaris-ems-probe-secret \
  --from-literal=PROBE_AUTH_TOKEN=<service-jwt>

# Render the CronJob (image.registry/image.tag placeholders come from Helm
# or can be substituted with envsubst for a plain kubectl apply):
envsubst < ops/k8s/synthetic-probe-cronjob.yaml | kubectl apply -f -
```

## Grafana

Import `ops/grafana/polaris-ems-probes.json` into the observability Grafana
(folder: "Polaris EMS"). It reads the shared Prometheus datasource.

## Alert rules (suggested — wire in Prometheus Alertmanager)

- `PolarisEmsCriticalProbeDown`: `increase(ems_synthetic_probe_errors_total{endpoint=~"backend_health|dashboards_index|outages_active|mdms_tariffs_proxy|hes_dcus"}[15m]) >= 2`, severity `critical`.
- `PolarisEmsProbeLatencyHigh`: `histogram_quantile(0.95, rate(ems_synthetic_probe_duration_seconds_bucket[15m])) > 5`, severity `warning`.
