# eskom_demonstration_ems — Consolidated polaris_ems Tree

Consolidated on 2026-04-21 from multiple worktrees/branches of `polaris_ems`.

## Sources

| Source | Branch | Worktree | Contribution |
|--------|--------|----------|--------------|
| Base | `eskom_dev` | `018-smoc-ems` | Deployed demo state + 018-nomock real-data wiring + 16 WIP files + untracked `specs/` |
| Overlay | `017-egsm-reports-postgres` | main | Phase-b additions: metrology, PostGIS, RBAC, outage/notifications, EGSM Postgres, docs/, devops/manifests, new FE pages |
| Sidecar | `017-egsm-reports-postgres` | main | 129 conflicting files staged in `.017_conflicts/` for manual review |

## Branch divergence

The two branches have **no common git ancestor** (`git merge-base` returned empty).
Each has developed independently:

- **`eskom_dev` has 25+ commits 017 lacks** — 018-nomock.* series (wire live MDMS APIs, drop mocks), 018-W4a (ANALYST/VIEWER RBAC enum), 018-deploy (idempotent migrations, alembic upgrade on startup), `fix(HESMirror)` real FOTA, `fix(smoc)` mirror repoint, UI polish.
- **`017-egsm-reports-postgres` has 56 commits eskom_dev lacks** — phase-b merge (013 metrology, 014 GIS/PostGIS, 015 RBAC+UI library, 016 notifications/outage) plus 017 EGSM Postgres migration (MDMS mirror, analytics) + polaris_ems baseline commit + GAPS fixes + CodePipeline buildspec.

## Worktrees consolidated

| Worktree | Branch | State |
|----------|--------|-------|
| `/home/ubuntu/dev_workspace` | `017-egsm-reports-postgres` | 4 modified + 2 untracked — copied |
| `/home/ubuntu/dev_workspace.wt/013-metrology` | `phase-b/013-metrology-ingest` | clean — ancestor of 017 |
| `/home/ubuntu/dev_workspace.wt/014-gis` | `phase-b/014-gis-postgis` | clean — ancestor of 017 |
| `/home/ubuntu/dev_workspace.wt/015-rbac` | `phase-b/015-rbac-ui-lib` | clean — ancestor of 017 |
| `/home/ubuntu/dev_workspace.wt/016-outage` | `phase-b/016-notifications-outage` | clean — ancestor of 017 |
| `/home/ubuntu/dev_workspace.wt/integration` | `phase-b/integration` | Dockerfile + alembic migration (already in 017) |
| `/home/ubuntu/dev_workspace.wt/018-smoc-ems` | `eskom_dev` | 16 WIP files + untracked — used as BASE |

## Layout

```
eskom_demonstration_ems/
├── backend/                # polaris_ems FastAPI — eskom_dev version + 017 new endpoints overlaid
├── frontend/               # polaris_ems React — eskom_dev version + 017 new pages/components overlaid
├── docs/                   # 017-only: API, DATABASE, DEPLOYMENT, FEATURES, GAPS, GIS, ROADMAP
├── devops/                 # eskom_dev buildspec + 017 manifests
├── k8s/                    # eskom_dev only
├── nginx/                  # both
├── ops/                    # eskom_dev only
├── repos/                  # eskom_dev only (contains specs/)
├── requirements/           # both (eskom_dev kept)
├── specs/                  # 018-smoc-ems WIP specs (untracked on 018 worktree)
├── .017_conflicts/         # 129 files with 017 version — FOR MANUAL REVIEW
└── INTEGRATION_NOTES.md    # this file
```

## Resolution strategy for conflicts

For the 129 files in `.017_conflicts/`, the **eskom_dev version is currently in the main tree**. To apply 017's version for any file:

```bash
cp .017_conflicts/<path> <path>
```

To see what differs:

```bash
diff -u <path> .017_conflicts/<path>
```

### Likely candidates to swap to 017 version

These are files where 017's phase-b changes may be newer/better than eskom_dev's version:

- `backend/alembic/versions/20260418_01_postgis_gis.py` — if you want the full PostGIS migration
- `backend/alembic/versions/20260418_02_outage_notifications.py` — outage/notifications tables
- `backend/alembic/versions/20260418_03_align_phase_a_015.py` — phase-a column alignment
- `backend/app/api/v1/endpoints/gis.py` — PostGIS layer API from phase-b/014
- `backend/app/api/v1/endpoints/outages.py` — outage endpoints from phase-b/016
- `backend/app/api/v1/endpoints/notifications.py` — notifications from phase-b/016
- `backend/app/api/v1/endpoints/reliability.py` — SAIDI/SAIFI calc from phase-b/016
- `backend/app/api/v1/endpoints/admin_metrology.py` — metrology admin from phase-b/013
- `backend/app/api/v1/router.py` — must register all endpoints from both branches

### Likely candidates to keep eskom_dev version

- `frontend/src/pages/AuditLog.jsx` — eskom_dev has 018-nomock (last-7-days default)
- `frontend/src/pages/Dashboard.jsx`, `Reports.jsx`, `DEREv.jsx`, `DERManagement.jsx`, etc. — 018-nomock live API wiring
- `frontend/src/pages/MDMSMirror.jsx`, `HESMirror.jsx` — live API repoint fixes
- `backend/app/api/v1/endpoints/hes_mirror.py` — real FOTA dispatch

## Recommendation

Do NOT copy this directory wholesale to production yet. The 129-file conflict set requires file-by-file judgement from the team that knows which branch's change is canonical for each file. Start by reviewing `.017_conflicts/backend/app/api/v1/router.py` — that one controls which endpoints are wired, so it must be a merge of both branches.
