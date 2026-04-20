# Quickstart: Spec 018 SMOC/EMS

## Prerequisites

- Dev EKS access (AWS profile `dev`, ap-south-1).
- `eskom_dev` branch checked out; branch `018-smoc-ems-full-compliance` created from it.
- Simulator deployed (dev EKS) with preset `demo-21-apr-2026` pending Ops lock.
- HES + MDMS reachable on dev cluster.

## Boot EMS in Each SSOT_MODE

```bash
# Disabled (offline dev) — uses seeded Postgres only
cd backend
export SSOT_MODE=disabled
export HES_ENABLED=false
export MDMS_ENABLED=false
export KAFKA_ENABLED=false
uvicorn app.main:app --reload

# Mirror (demo fallback) — reads upstream with cache fallback
export SSOT_MODE=mirror
export HES_ENABLED=true HES_BASE_URL=http://hes-routing-service.hes.svc.cluster.local:8080
export MDMS_ENABLED=true MDMS_BASE_URL=http://mdms-api.mdms.svc.cluster.local:8080
export KAFKA_ENABLED=true KAFKA_BOOTSTRAP=kafka.dev.polagram.internal:9092
export KAFKA_SASL_USER=... KAFKA_SASL_PASS=...
uvicorn app.main:app

# Strict (production) — upstream or error
export SSOT_MODE=strict
# same vars as mirror; no fallback behaviour
```

## Frontend

```bash
cd frontend
export VITE_API_BASE=http://localhost:8000
pnpm dev
# open http://localhost:5173
```

## Run E2E Demo Compliance Suite

```bash
# Backend integration
cd backend
pytest tests/integration/demo_compliance/ -v --tb=short

# Frontend Playwright
cd frontend
npx playwright test tests/e2e/demo_compliance/ --reporter=html

# Full combined via harness skill
# (from root)
/e2e-test
```

## Deploy to Dev EKS

```bash
git push origin 018-smoc-ems-full-compliance
# CodePipeline dev-polaris-ems-backend and dev-polaris-ems-frontend auto-trigger
# Monitor
aws --profile dev --region ap-south-1 codepipeline list-pipeline-executions --pipeline-name dev-polaris-ems-backend --max-items 3
```

## Smoke Checks After Deploy

```bash
kubectl --context dev -n polaris-ems get pods
curl -k https://vidyut360.dev.polagram.in/api/v1/health
curl -k https://vidyut360.dev.polagram.in/api/v1/mdms/vee/summary?date=2026-04-18 -H "Authorization: Bearer ..."
```

## Troubleshooting

- `SSOT_MODE=strict` and MDMS unreachable: banner shown; fix by scaling mdms-api or flipping to mirror.
- Kafka lag: check `polaris-ems-*` consumer group on Grafana; restart consumer deployment.
- AppBuilder publish fails: check `app_def` table migration applied; RBAC role includes `app_builder_publish`.
- Outage correlator not opening incidents: verify `hesv2.meter.events` messages are arriving; check correlator config thresholds.
