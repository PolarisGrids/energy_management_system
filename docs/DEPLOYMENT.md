# Polaris EMS — Deployment

Two deployment paths: **Docker Compose** for local dev, **AWS EKS (dev profile)** for the live environment at https://vidyut360.dev.polagram.in.

## Topology

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  Frontend    │       │  Backend     │       │  PostgreSQL  │
│  Nginx SPA   │ ─────►│  FastAPI     │ ─────►│  16          │
│  (React 19)  │       │  (Uvicorn)   │       │              │
└──────────────┘       └──────────────┘       └──────────────┘
    :3001/:80             :8002/:8000             :5432
```

Nginx fronts the SPA and proxies `/api/` to FastAPI. SSE is proxied with buffering disabled (`proxy_buffering off`, 24h read timeout).

## Environments

| Env | URL | Infra |
|---|---|---|
| Local | `http://localhost:3001` | Docker Compose (`docker-compose.yml`) |
| Dev | `https://vidyut360.dev.polagram.in` | AWS EKS (dev profile), ALB ingress, PostgreSQL on EC2 |

## Local (Docker Compose)

```bash
cd repos/polaris_ems
docker compose up -d --build
```

Services defined in `docker-compose.yml`:
- `db` — `postgres:16-alpine`, healthcheck via `pg_isready`, data volume `db_data`
- `backend` — built from `backend/Dockerfile`, waits for db healthy, runs `seed_data.py` then `uvicorn`
- `frontend` — built from `frontend/Dockerfile`, Nginx serving `/dist` + reverse-proxy to backend

Ports: frontend `3001:80`, backend `8002:8000`, db `5432:5432`.

Reset DB:
```bash
docker compose down -v && docker compose up -d --build
```

## Backend Image

`backend/Dockerfile`:
```dockerfile
FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
RUN apt-get install build-essential libpq-dev curl
COPY requirements.txt . && RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "python scripts/seed_data.py && uvicorn app.main:app --host :: --port 8000"]
```

Key deps (`backend/requirements.txt`): FastAPI 0.115, Uvicorn 0.30, SQLAlchemy 2.0, Alembic 1.13, psycopg2-binary, Pydantic 2.9, python-jose, passlib/bcrypt, sse-starlette, numpy/scipy/shapely.

## Frontend Image

`frontend/Dockerfile`: Node 20 Alpine builder → `npm run build` → Nginx Alpine serves `/dist`. Custom `nginx.conf`:
- `/` → SPA fallback to `index.html`
- `/api/` → `http://backend:8000`
- `/api/v1/events/` → same upstream with `proxy_buffering off`, `proxy_read_timeout 86400s`

## AWS EKS Deployment

Pipeline is Jenkins-driven with ArgoCD GitOps.

`backend/Jenkinsfile`:
```groovy
@Library('smoc-jenkins-lib') _
smocPipeline(
    serviceName: 'polaris-ems-backend',
    ecrRepo: 'dev/polaris-ems/backend',
    gitopsPath: 'apps/polaris-ems-backend/dev-values.yaml'
)
```

Flow:
1. Commit to branch → Jenkins job triggered
2. `smocPipeline` builds Docker image, pushes to ECR `dev/polaris-ems/backend`
3. Jenkins bumps image tag in GitOps repo `apps/polaris-ems-backend/dev-values.yaml`
4. ArgoCD syncs the Helm release to EKS (dev cluster, ap-south-1)
5. ALB ingress publishes `https://vidyut360.dev.polagram.in`

Frontend has its own pipeline (mirrors pattern — not yet checked into this repo).

## Configuration

### Backend `.env`
Template lives in `backend/.env` (74 vars). Required in production:

| Var | Example | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://smoc:****@db:5432/smoc_ems` | Primary DB |
| `SECRET_KEY` | *(SSM)* | JWT signing |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | JWT lifetime |
| `ALLOWED_ORIGINS` | `https://vidyut360.dev.polagram.in` | CORS allowlist |
| `OTEL_COLLECTOR_ENDPOINT` | `http://otel-collector.observability.svc.cluster.local:4317` | Observability |
| `SERVICE_NAME` | `polaris-ems` | OTel resource |
| `DEPLOY_ENV` | `dev` | OTel env tag |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka-dev:9092` | Audit events |
| `HES_BASE_URL` | `http://hes-routing-service/…` | HES integration |
| `MDMS_BASE_URL` | `http://mdms-api/…` | MDMS integration |
| `TEAMS_WEBHOOK_URL` | *(SSM)* | Operator alerts |
| `SSE_HEARTBEAT_SECONDS` | `15` | SSE liveness |
| `SIM_TICK_SECONDS` | `2.0` | Sim engine cadence |

In dev EKS these are sourced from SSM Parameter Store `/dev/polaris-ems/*` and materialised into the Helm values / container env.

### Frontend `.env`
`frontend/.env` — compile-time only (baked into the Vite bundle):

| Var | Example |
|---|---|
| `VITE_API_BASE_URL` | `/api/v1` |
| `VITE_TEAMS_CLIENT_ID` | *(tenant client id)* |
| `VITE_TEAMS_TENANT_ID` | *(tenant id)* |
| `VITE_TEAMS_CONTEXT` | `standalone` |
| `VITE_MAPBOX_TOKEN` | *(optional — Leaflet uses OSM tiles)* |
| `VITE_APP_NAME` | `SMOC EMS` |
| `VITE_TENDER_REF` | `E2136DXLP` |

## Database

- **Local**: Postgres 16 container with seed script (`backend/scripts/seed_data.py`) on first boot
- **Dev**: PostgreSQL on EC2 (per project standard). Connect via bastion / VPC.

Bootstrapping a fresh DB:
```bash
docker compose exec backend python scripts/seed_data.py
```

## Observability

Polaris EMS participates in the shared LGTM stack on the `observability` EKS namespace:
- Traces → OTel Collector → Tempo (7d retention)
- Metrics → Prometheus (15d)
- Logs → structlog JSON → Loki (14d)
- Audit events → Kafka `mdms.audit.actions` → `action_audit_log` in CIS DB

Dashboards: *Service Overview*, *Meter Operations*, *Audit Trail*, *Infrastructure Health* (provisioned from `repos/infra/observability/dashboards/`).

## Health & Smoke

```bash
curl https://vidyut360.dev.polagram.in/health
curl https://vidyut360.dev.polagram.in/api/v1/meters/summary \
     -H "Authorization: Bearer $JWT"
curl -N https://vidyut360.dev.polagram.in/api/v1/events/stream \
     -H "Authorization: Bearer $JWT"
```

## Runbooks

- **Backend crashloop** — check `kubectl logs` for seed script errors; seed is idempotent but fails hard on schema drift. Recreate DB in dev via `docker compose down -v` (local) or targeted SQL (EKS).
- **Stale SSE** — Nginx buffering regressions are the common culprit; verify `proxy_buffering off` in the frontend nginx.conf and that ALB idle timeout ≥ 60s.
- **Alarm tsunami** — simulation engine leaks if `POST /simulation/{id}/reset` is skipped; always reset before starting a new scenario.

## Branch & Release Policy

- Use branch `eskom_dev` for dev deploys (never push to `main` / `staging` / `dev` from here).
- Image tags follow `<git-sha>-<build-number>`; ArgoCD tracks latest tag for the environment.
- Every release that touches running services is logged in `changelogs/YYYY-MM-DD.md`.
