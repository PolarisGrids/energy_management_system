# Security Review Checklist — spec 018 (Polaris EMS SMOC compliance)

**Owner**: Akshay Kumar
**Reviewer**: _TBD_ (assign before 2026-04-19 EOD)
**Scope**: All commits on branch `018-smoc-ems-full-compliance` up to the
  pre-demo tag.
**Goal**: zero P0/P1 findings prior to the 21 April demo (satisfies
  SC-002 and plan Gate D "security review clean").

Run via `/security-review` skill or manually against the branch diff
(`git diff main...018-smoc-ems-full-compliance`).

---

## OWASP Top-10 (2021) — status matrix

| # | Category | Status | Evidence / Notes |
| --- | --- | --- | --- |
| A01 | Broken Access Control | PASS (verify) | RBAC enforced on 24 mutating endpoints via `require_role()` dependency (W4.T13). Verify each proxy route also forwards role context. |
| A02 | Cryptographic Failures | PASS (verify) | All inter-service traffic HTTPS via ingress; TLS verification on (probe + loadtest set `PROBE_TLS_VERIFY=true`). JWT signed with RS256 (Cognito) — confirm `verify_signature=True` in `app/core/security.py`. |
| A03 | Injection | PASS (verify) | SQLAlchemy ORM + bound parameters throughout; alarm-rule algorithm runner migrated to RestrictedPython sandbox (W4.T7). Confirm no raw SQL strings in `backend/app/`. |
| A04 | Insecure Design | PASS | SSOT_MODE tri-state forces explicit opt-in for mirror/strict. EMS persists only IDs from upstream (spec §Scope). |
| A05 | Security Misconfiguration | PARTIAL | Placeholder creds removed (W1.T2). CSP headers NOT yet added (gap — see below). CORS still permissive on `/api/v1/*` for dev — restrict before demo. |
| A06 | Vulnerable & Outdated Components | GAP | No automated dep scan in CI yet. Run `pip-audit` + `npm audit` manually pre-demo; track in `changelogs/2026-04-18.md`. |
| A07 | Identification & Auth Failures | PASS (verify) | SSE auth moved from query string to `Authorization` header (W0.T8); legacy `?token=` path removed. Verify no frontend code still appends token to SSE URL. |
| A08 | Software & Data Integrity Failures | PARTIAL | Container images pinned by tag; SHA pin TODO. Helm charts sourced from private registry. |
| A09 | Security Logging & Monitoring Failures | PASS | Audit trail on all writes via Kafka → `action_audit_log` (W2.T13); OTel traces on every request; synthetic probes monitor critical routes (W5.T49). |
| A10 | Server-Side Request Forgery | PASS (verify) | HES/MDMS proxy clients restrict `base_url` to env-configured hosts only; no user-supplied URLs. Confirm `_proxy_common.py` rejects scheme/host overrides. |

Legend: **PASS** = verified, **PASS (verify)** = implemented; reviewer to re-verify, **PARTIAL** = partially mitigated, **GAP** = no control yet.

---

## Spec-018 specific findings to validate

Each item below was closed during Waves 0–4; reviewer should confirm
with a short code-walk.

- [ ] **SSE auth in header (not query string)** — W0.T8 closed. Check:
  - Backend: `app/api/v1/endpoints/sse.py` reads `Authorization` header only.
  - Frontend: `frontend/src/services/sse.ts` uses `EventSource` polyfill that supports headers OR switches to fetch-stream; no `?token=` in URL.
  - Grep: `grep -R "token=" frontend/src --include="*.ts*"` must not hit SSE URLs.

- [ ] **Placeholder credentials removed** — W1.T2 closed. Check:
  - No `"changeme"`, `"password123"`, `"admin"` literals in `backend/app/**`.
  - `.env.example` documents every key but holds no real secrets.
  - `docker-compose.yml` references env vars, not inline creds.

- [ ] **RBAC on 24 mutating endpoints** — W4.T13 closed. Check:
  - Grep for `@router.(post|put|patch|delete)` — each must chain a `require_role(...)` dependency.
  - Analyst role cannot reach `/admin/*` routes (Playwright test `us_rbac_*.spec.ts` green — SC-007).

- [ ] **RestrictedPython sandbox on algorithm runner** — W4.T7 closed. Check:
  - `app/services/alarm_rule_runner.py` imports `RestrictedPython`; compile uses `compile_restricted`; globals allow-list is explicit.
  - Unit test exercises a malicious payload (`__import__('os').system(...)`) and confirms it raises.

- [ ] **Audit trail on all writes** — W2.T13 closed. Check:
  - Every POST/PUT/PATCH/DELETE path calls `await audit(...)` or is covered by the FastAPI middleware that auto-audits.
  - Kafka topic `mdms.audit.actions` receives events (verify via `kcat` or Grafana audit trail dashboard).

---

## Known gaps (acknowledged — tracked for post-demo)

| Gap | Severity | Mitigation before demo | Owner |
| --- | --- | --- | --- |
| No per-IP / per-user rate limiting | P2 | Ingress-level NGINX `limit_req` for `/api/v1/*` (already on MDMS ingress — mirror config) | Ops |
| No Content-Security-Policy header | P2 | Add strict CSP via FastAPI middleware or ingress response-headers; default-src 'self' with explicit allow for Grafana iframe | Backend |
| No SCA/dep-scan in CI | P2 | Manual `pip-audit --strict` + `npm audit --production` run logged in changelogs/ before demo | Akshay |
| No penetration test | P3 | Schedule for post-demo (Wave 6) | Security team |
| Container images not pinned to SHA | P3 | Pin in Helm values after demo | Ops |
| CORS too permissive in dev | P2 | Restrict to known frontend origin list in `backend/app/main.py` | Backend |

---

## Action checklist for reviewer

Work top-to-bottom; mark items `[x]` when complete. Log any new finding
at the bottom with P0/P1/P2/P3 severity.

- [ ] Pull branch and run `git log --stat main...018-smoc-ems-full-compliance`.
- [ ] Walk every item in the OWASP matrix above; flip any PASS (verify) → PASS or GAP.
- [ ] Walk every spec-018 finding; tick each `[ ]` or open an issue.
- [ ] Run `/security-review` skill against the PR bundle; paste findings here.
- [ ] Run `pip-audit --requirement backend/requirements.txt` — attach output.
- [ ] Run `npm audit --prefix frontend --production` — attach output.
- [ ] Grep for high-risk patterns:
  - `eval(`, `exec(`, `subprocess.`, `pickle.loads(`
  - `"password"`, `"secret"`, `sk_live_`, `AKIA`
  - `ALLOW_INSECURE`, `VERIFY=False`, `verify_signature=False`
- [ ] Confirm every Dockerfile in this spec uses a non-root user (the
  probe image does — `USER 65532:65532`).
- [ ] Confirm no secrets committed — scan the diff for anything resembling
  a JWT, AWS key, or DB URL with a password.

## Reviewer findings (fill in)

- [ ] _No P0/P1 findings_ (target state for Gate D sign-off).

| ID | Severity | Area | Description | Remediation | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
|    |          |      |             |             |       |        |

---

## Sign-off

- Reviewer: _________________________  Date: __________
- Approver: _________________________  Date: __________
- Result: [ ] Clean  [ ] Clean with P2 follow-ups  [ ] Blocked
