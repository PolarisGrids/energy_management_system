# Checklist: P0 Repo-Integrity Gaps (Wave 0)

Derived from `docs/GAPS.md` §0 and §1.1. These must be resolved before any other wave can claim completeness.

- [ ] `backend/app/models/meter.py` restored (imported from `__init__.py:2`, `endpoints/meters.py:7`, `sse.py`, `simulation_engine.py`, `seed_data.py:19`). Exports `Meter, Transformer, Feeder, MeterStatus, RelayState`.
- [ ] `backend/app/schemas/` populated: `alarms.py`, `der.py`, `meter.py`, `simulation.py`, `sensor.py`, `auth.py`, plus new `outage.py`, `report.py`, `app_builder.py`.
- [ ] `frontend/src/App.jsx` committed with all required routes registered: `/dashboard`, `/map`, `/alarms`, `/der`, `/energy`, `/reports`, `/hes`, `/mdms`, `/sensors`, `/simulation`, `/audit`, `/showcase`, `/reconciler`, `/av-control`, `/appbuilder`, `/settings`, `/admin`, `/ntl`, `/distribution`, `/system-mgmt`, `/data-accuracy`.
- [ ] Alembic baseline migration committed to `backend/alembic/versions/`; `create_all()` removed from backend lifespan; `alembic upgrade head` part of startup.
- [ ] `reconcilerAPI` exported from `frontend/src/services/api.js`.
- [ ] SSE auth moved from query string `?token=` to `Authorization: Bearer` header.
- [ ] Placeholder credentials removed from `backend/app/core/config.py` — replaced with Secrets Manager loader.
- [ ] `/map`, `/reconciler`, `/appbuilder` routes reachable in deployed build (Playwright passes on each).
- [ ] `Reconciler.jsx` mounts without crash (reconcilerAPI defined).
- [ ] `HESMirror.jsx` removed hard-coded `183 online / 42 offline / 15 tamper / 91.4% comm` fallback.
- [ ] `MDMSMirror.jsx` fixed NaN% on zero-denominator.
- [ ] `Dashboard.jsx` fallback `—` replaced with loading skeleton + error banner.
- [ ] `EnergyMonitoring.jsx` empty-array fallback replaced with loading/error state.
- [ ] `components/ui/` populated: Button, Card, KPI, Chart wrapper, Modal, Toast, Skeleton, ErrorBoundary.
- [ ] Cold container boot green on clean Postgres (docker-compose from scratch).
- [ ] Playwright smoke (`tests/e2e/smoke/`) passes on all registered routes — no 404, no console errors.

## Verification Commands

```bash
# From repo root
cd backend && pytest tests/unit tests/integration/smoke -x
cd frontend && npx playwright test tests/e2e/smoke --reporter=list
docker compose down -v && docker compose up -d --build && sleep 30 && ./scripts/smoke.sh
```
