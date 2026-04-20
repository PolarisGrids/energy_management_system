# Spec 018 — SMOC/EMS Full AMI Compliance

**Feature Branch**: `018-smoc-ems-full-compliance`
**Target**: Eskom Tender E2136DXLP demo points #4–#27. Demo day 21 Apr 2026. Production hardening continues post-demo.

## Artefacts

| File | Purpose |
|---|---|
| [`spec.md`](./spec.md) | 24 user stories + FR/NFR + SSOT contract + success criteria |
| [`plan.md`](./plan.md) | 6-wave implementation plan, tech context, risk register |
| [`data-model.md`](./data-model.md) | EMS-owned tables + Alembic baseline approach |
| [`quickstart.md`](./quickstart.md) | Dev bring-up, SSOT_MODE toggles, smoke checks |
| [`mdms-todos.md`](./mdms-todos.md) | MDMS-side changes this spec depends on — Umesh approval required |
| [`integration-test-matrix.md`](./integration-test-matrix.md) | 24 demo stories × E2E harness |
| [`contracts/mdms-integration.md`](./contracts/mdms-integration.md) | EMS→MDMS REST contract |
| [`contracts/hes-integration.md`](./contracts/hes-integration.md) | EMS↔HES REST + Kafka |
| [`contracts/simulator-cooperation.md`](./contracts/simulator-cooperation.md) | EMS↔Simulator narrow cooperation paths |
| [`checklists/p0-gaps.md`](./checklists/p0-gaps.md) | Wave-0 repo-integrity checklist |

## Sibling Spec

[`repos/simulator/specs/001-ami-full-data-generation/`](../../../simulator/specs/001-ami-full-data-generation/) — simulator data-generation compliance.

## Source-of-Truth Rule (Mandatory)

EMS reads **MDMS** for all metering/billing/VEE/tariff/CIS/NTL/reports; **HES** for commands + comm health + raw events. EMS owns only outage, DER, sensors, AppBuilder, dashboards, notifications, audit. Simulator publishes to HES exclusively; no direct simulator→EMS metering path.

## How To Work This Spec

1. Read `spec.md` end-to-end.
2. Create PR from `eskom_dev` → `018-smoc-ems-full-compliance`.
3. Pick a wave in `plan.md` (Wave 0 first — P0 gaps).
4. Use `/gsd:plan-phase` on this branch to generate `tasks.md` from the plan.
5. Use `/gsd:execute-phase` to work through tasks.
6. E2E tests in `backend/tests/integration/demo_compliance/` are the acceptance bar.
7. Any MDMS-side change MUST be escalated to Umesh via `mdms-todos.md` before branching MDMS code.
