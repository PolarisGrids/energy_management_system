# Polaris EMS — Claude Code context

## Deployment

| Item | Value |
|---|---|
| **AWS account** | `703623468956` / `ap-south-1` |
| **AWS CLI profile** | `dev` (`~/.aws/config`) |
| **CodePipeline** | `dev-polaris-ems` — triggered by push to branch `eskom_dev` |
| **EKS cluster** | `dev-cluster` |
| **K8s namespace** | `polaris-ems` |
| **Deployments** | `polaris-ems-backend` · `polaris-ems-frontend` |
| **Live URL** | `https://vidyut360.dev.polagram.in` |
| **ECR repos** | `703623468956.dkr.ecr.ap-south-1.amazonaws.com/dev/polaris-ems/{backend,frontend}` |

### Key commands
```bash
# Authenticate kubectl
aws --profile dev eks update-kubeconfig --name dev-cluster --region ap-south-1

# Check pipeline
aws --profile dev codepipeline get-pipeline-state --name dev-polaris-ems --region ap-south-1

# Trigger deploy — push main → eskom_dev
git push origin main:eskom_dev

# Rollback
kubectl -n polaris-ems rollout undo deployment/polaris-ems-backend
kubectl -n polaris-ems rollout undo deployment/polaris-ems-frontend
```

## Local dev
```bash
docker-compose up --build        # backend :8002, frontend :3001, postgres :5432
```
Credentials: `smoc / smoc_pass` · DB: `smoc_ems`

## Git branching
- `main` — stable, source of truth for PRs
- `eskom_dev` — pipeline trigger branch (push `main → eskom_dev` to deploy)
- Feature branches: `feat/<name>`

## DER simulator
`backend/app/services/der_sim.py` — asyncio background task started in `lifespan`.
- Back-fills 30 days of history for any asset with stale (>2h old) telemetry at startup.
- Inserts one row per asset every 5 minutes thereafter.
- Controlled by env var `DER_SIM_ENABLED` (default `1`). Set to `0` to disable.
