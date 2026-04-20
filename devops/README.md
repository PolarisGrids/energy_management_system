# Polaris EMS — Deployment

## Pipeline

- **Provider**: AWS CodePipeline → CodeBuild → ECR → EKS (same account, `703623468956` / `ap-south-1`).
- **Pipeline**: `dev-polaris-ems`.
- **Source**: CodeStarSourceConnection tracking branch `eskom_dev`.
- **Build**: CodeBuild project `dev-polaris-ems` (ARM64, `aws/codebuild/amazonlinux-aarch64-standard:3.0`).
- **Buildspec**: `devops/dev-buildspec.yaml` (this directory).
- **Target cluster**: `dev-cluster` (EKS, `ap-south-1`).
- **Namespace**: `polaris-ems`.
- **Deployments**: `polaris-ems-backend` (port 8000, FastAPI) and `polaris-ems-frontend` (port 80, nginx+SPA).
- **ECR repos**: `dev/polaris-ems/backend`, `dev/polaris-ems/frontend`.
- **Ingress**: `vidyut360.dev.polagram.in` → frontend service (ALB internal, then exposed via ingress).

## Flow

1. Dev pushes to `eskom_dev`.
2. CodeStarSourceConnection fires the pipeline.
3. CodeBuild (`dev-polaris-ems`):
   - Builds `backend/Dockerfile` → `dev/polaris-ems/backend:{latest, $IMAGE_TAG}`.
   - Builds `frontend/Dockerfile` → `dev/polaris-ems/frontend:{latest, $IMAGE_TAG}`.
   - Pushes both to ECR.
   - `kubectl set image ...` on each Deployment with the immutable `$IMAGE_TAG` so Kubernetes rolls.
   - `kubectl rollout status ... --timeout=5m` on both.
4. Pods come up, ingress routes traffic, `https://vidyut360.dev.polagram.in` is live.

## Pre-rollout migrations

CodeBuild deliberately does NOT run Alembic — a broken migration must never be auto-deployed. Run migrations from an authorized workstation **before** pushing changes that expect new tables/columns:

```bash
# First time only — tell Alembic the existing create_all()-seeded schema is baseline:
./devops/apply-migrations.sh stamp 20260418_0001

# After that, every release:
./devops/apply-migrations.sh upgrade
```

The script execs `alembic` inside the currently-running `polaris-ems-backend` pod, so it uses the pod's `DATABASE_URL`.

## Manifests

`manifests/*.live-snapshot.yaml` are read-only captures of the currently-running `kubectl get -o yaml` for backend/frontend Deployments, Services, and Ingress. They serve as documentation only — the pipeline does not `kubectl apply` them. If you need to change env vars, ports, or resource limits, run `kubectl -n polaris-ems edit deploy/polaris-ems-backend` and then refresh the snapshot with:

```bash
kubectl -n polaris-ems get deploy polaris-ems-backend -o yaml > devops/manifests/backend-live-snapshot.yaml
```

## Env vars set on the live backend deployment

| Var | Value (current) | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:***@mdms.dev.polagram.in:5432/smoc_ems` | Shared EC2 Postgres (dev MDMS host). |
| `SECRET_KEY` | `smoc-eskom-demo-secret-key-2026-***` | Move to SSM before prod. |
| `DEBUG` | `false` | — |
| `KAFKA_ENABLED` | `false` | Leave off until HES Kafka reachable + `KAFKA_BOOTSTRAP_SERVERS` set. |
| `HES_ENABLED` | `false` | — |
| `MDMS_ENABLED` | `false` | — |
| `SMTP_ENABLED`/`TWILIO_ENABLED`/`TEAMS_ENABLED`/`FIREBASE_ENABLED` | `false` | All senders in log-only mode. |

To activate metrology ingest in dev, set on the Deployment via `kubectl edit`:

```yaml
env:
- name: METROLOGY_INGEST_ENABLED
  value: "true"
- name: KAFKA_BOOTSTRAP_SERVERS
  value: "<hes-kafka-endpoint>:9092"
- name: MDMS_VEE_DATABASE_URL
  value: "postgresql://<ro-user>:<pw>@<vee-host>:5432/vee_db"
```

No code changes are required — these are read by `backend/app/core/config.py` at startup.

## Rolling back

```bash
kubectl -n polaris-ems rollout undo deployment/polaris-ems-backend
kubectl -n polaris-ems rollout undo deployment/polaris-ems-frontend
```

Or pin a specific tag:

```bash
kubectl -n polaris-ems set image deploy/polaris-ems-backend backend=703623468956.dkr.ecr.ap-south-1.amazonaws.com/dev/polaris-ems/backend:<previous-IMAGE_TAG>
```

## Jenkins — removed

The previous `backend/Jenkinsfile` was an obsolete artefact from a pre-CodePipeline experiment. CodePipeline is the single source of truth for CI/CD; the file has been deleted.
