# Production Launch Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring SocialEval from a development-ready MVP to a production-launchable single-node cloud deployment with secure configuration, durable storage, operable background workers, and real deployment automation.

**Architecture:** Keep the current single-node MVP shape documented in `docs/architecture/SocialEval-mvp-cloud-sizing.md`: `Nginx + FastAPI + Celery + PostgreSQL + Redis`, but make that shape real in the repository through explicit runtime packaging, production env config, service management, and operational verification. Preserve the existing Python backend and Vite-built frontend, while replacing local-development assumptions around storage, cookies, CORS, email, and observability.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, Celery, Redis, PostgreSQL, React, TypeScript, Vite, Nginx, Docker/Compose or systemd, object storage

---

## Current Readiness Summary

**What is already in place**
- FastAPI API entrypoint exists in `src/api/main.py`
- Celery worker entrypoint exists in `src/tasks/celery_app.py`
- Database migrations exist under `alembic/`
- Frontend can build via `src/web/package.json`
- Core backend and frontend tests currently pass in local verification

**What blocks a clean production launch right now**
- No backend Dockerfile, frontend Dockerfile, production compose, Nginx template, or service unit files
- API still uses localhost-only CORS and non-HTTPS session cookie settings
- Uploads and report exports still write to local disk under `data/uploads` and `data/exports`
- Review-assignment email sender only logs, it does not send mail
- Production env values are incomplete: AI provider keys are blank, SMTP credentials are blank, and `SECRET_KEY` is still at the default placeholder
- Test coverage is still weighted toward unit and mocked API flows; there is no true production-like end-to-end pipeline verification in CI

## File Structure For This Launch Plan

**Deployment packaging**
- Create: `Dockerfile.api`
- Create: `src/web/Dockerfile`
- Create: `docker-compose.prod.yml`
- Create: `deploy/nginx/socialeval.conf`
- Create: `deploy/systemd/socialeval-api.service`
- Create: `deploy/systemd/socialeval-worker.service`
- Create: `deploy/systemd/socialeval-beat.service` (only if periodic jobs are introduced)

**Configuration and security**
- Modify: `.env.example`
- Modify: `src/core/config.py`
- Modify: `src/api/main.py`
- Modify: `src/web/src/lib/api.ts`
- Create: `docs/deployment/production-env.example.md`

**Durable storage and integrations**
- Modify: `src/core/storage.py`
- Modify: `src/reporting/exporters.py`
- Create: `src/core/object_storage.py`
- Modify: `src/core/email.py`
- Create: `tests/test_reporting/test_exporters.py`
- Create: `tests/test_review/test_assignment_email.py`

**Operational visibility and launch verification**
- Modify: `src/core/logging.py`
- Modify: `src/api/routers/health.py`
- Create: `.github/workflows/ci.yml`
- Create: `tests/integration/test_launch_smoke.py`
- Create: `docs/deployment/launch-checklist.md`
- Modify: `docs/deployment/SocialEval-deployment-and-operations-guide.md`

---

### Task 1: Production Runtime Packaging

**Files:**
- Create: `Dockerfile.api`
- Create: `src/web/Dockerfile`
- Create: `docker-compose.prod.yml`
- Create: `deploy/nginx/socialeval.conf`
- Create: `deploy/systemd/socialeval-api.service`
- Create: `deploy/systemd/socialeval-worker.service`
- Modify: `docs/deployment/SocialEval-deployment-and-operations-guide.md`

- [ ] **Step 1: Package the backend runtime**

Build a backend image that:
- installs project dependencies with `uv`
- runs Alembic separately, not inside app boot
- starts `uvicorn src.api.main:app` with production host/port

- [ ] **Step 2: Package the frontend runtime**

Create a frontend image or static artifact path that:
- runs `npm ci`
- runs `npm run build`
- serves `src/web/dist` behind Nginx

- [ ] **Step 3: Add a production compose topology**

Define a repository-owned production topology for:
- `api`
- `worker`
- `postgres`
- `redis`
- `nginx`

Include:
- volumes
- restart policies
- env file loading
- internal network wiring

- [ ] **Step 4: Add host-managed service definitions**

Provide `systemd` unit files for teams that do not want full containerization.

- [ ] **Step 5: Verify packaging locally**

Run:
```bash
docker build -f Dockerfile.api .
docker build -f src/web/Dockerfile src/web
docker compose -f docker-compose.prod.yml config
```

Expected:
- both images build successfully
- compose file validates without schema or env interpolation errors

### Task 2: Production Configuration And Security Hardening

**Files:**
- Modify: `.env.example`
- Modify: `src/core/config.py`
- Modify: `src/api/main.py`
- Modify: `src/web/src/lib/api.ts`
- Create: `docs/deployment/production-env.example.md`
- Test: `tests/test_api/test_auth_flow.py`

- [ ] **Step 1: Expand the settings model for production**

Add explicit settings for:
- `APP_ENV`
- `ALLOWED_ORIGINS`
- `SESSION_COOKIE_SECURE`
- `SESSION_COOKIE_DOMAIN`
- `PUBLIC_BASE_URL`
- `API_BASE_URL`
- object storage credentials and bucket names

- [ ] **Step 2: Remove development-only defaults from runtime behavior**

Replace hardcoded:
- localhost CORS allowlist
- `https_only=False`
- implicit local API base assumptions

With env-driven settings that fail clearly in production misconfiguration.

- [ ] **Step 3: Refresh env documentation**

Update `.env.example` so production operators can fill:
- real `SECRET_KEY`
- AI provider keys
- SMTP credentials
- database and Redis endpoints
- object storage config

- [ ] **Step 4: Add security-focused regression tests**

Cover:
- session cookie secure flag behavior
- origin allowlist parsing
- auth continuing to work under production config

- [ ] **Step 5: Verify hardening changes**

Run:
```bash
uv run pytest tests/test_api/test_auth_flow.py -q
npm --prefix src/web run build
```

Expected:
- auth tests pass
- frontend still builds with env-driven API base handling

### Task 3: Durable File Storage And Report Persistence

**Files:**
- Create: `src/core/object_storage.py`
- Modify: `src/core/storage.py`
- Modify: `src/reporting/exporters.py`
- Modify: `src/core/config.py`
- Create: `tests/test_reporting/test_exporters.py`
- Create: `tests/test_api/test_storage_integration.py`

- [ ] **Step 1: Introduce a storage abstraction**

Split storage responsibilities into:
- upload persistence
- report export persistence
- local filesystem backend
- object storage backend

- [ ] **Step 2: Keep local storage as a dev fallback**

Do not break current local workflows. Production should be able to switch to object storage without changing business logic.

- [ ] **Step 3: Persist production artifacts to object storage**

Move these artifacts off local ephemeral disk:
- uploaded papers
- exported PDF reports
- exported JSON reports
- optional future audit archives

- [ ] **Step 4: Add tests for both storage modes**

Cover:
- local path persistence
- object storage key generation
- exporter metadata persistence

- [ ] **Step 5: Verify storage behavior**

Run:
```bash
uv run pytest tests/test_reporting/test_exporters.py tests/test_api/test_storage_integration.py -q
```

Expected:
- both local and object-storage code paths are covered
- report export records keep stable references to stored artifacts

### Task 4: Real Email Delivery, Worker Operations, And Recoverability

**Files:**
- Modify: `src/core/email.py`
- Modify: `src/tasks/celery_app.py`
- Modify: `src/tasks/evaluation_task.py`
- Modify: `src/api/routers/admin.py`
- Create: `tests/test_review/test_assignment_email.py`
- Create: `tests/test_tasks/test_worker_retries.py`

- [ ] **Step 1: Replace log-only email behavior with SMTP delivery**

Support:
- SMTP auth
- sender identity
- subject/body template
- timeout and error handling

- [ ] **Step 2: Make worker retry behavior explicit**

Ensure production workers have clear retry policy for:
- transient provider failures
- SMTP failures where appropriate
- Redis/network reconnect cases

- [ ] **Step 3: Preserve administrator recovery controls**

Keep the existing admin retry and close-task flows working with real async execution.

- [ ] **Step 4: Add worker-path regression tests**

Cover:
- successful assignment email send
- email failure surfacing
- retry metadata on task failures

- [ ] **Step 5: Verify async operational behavior**

Run:
```bash
uv run pytest tests/test_review/test_assignment_email.py tests/test_tasks/test_worker_retries.py -q
```

Expected:
- notifications are tested without requiring live SMTP
- failure and retry paths are no longer untested launch risks

### Task 5: Observability, Health Signals, And CI Gates

**Files:**
- Modify: `src/core/logging.py`
- Modify: `src/api/main.py`
- Modify: `src/api/routers/health.py`
- Create: `.github/workflows/ci.yml`
- Create: `tests/integration/test_launch_smoke.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Wire application logging at startup**

Ensure JSON logging is actually initialized for:
- API boot
- Celery worker boot
- exception paths

- [ ] **Step 2: Expand health endpoints**

Add layered checks for:
- app liveness
- database connectivity
- Redis connectivity
- optional object storage connectivity

- [ ] **Step 3: Add CI as a non-optional launch gate**

CI should run:
- backend tests
- frontend tests
- frontend build
- lint if introduced

- [ ] **Step 4: Add a launch smoke test suite**

Smoke test should cover:
- login
- upload
- task status polling
- report fetch
- review queue visibility

- [ ] **Step 5: Verify the release gate**

Run:
```bash
uv run pytest
npm --prefix src/web test
npm --prefix src/web run build
```

Expected:
- all required pre-launch checks pass from a clean environment

### Task 6: Final Launch Rehearsal And Go-Live Checklist

**Files:**
- Create: `docs/deployment/launch-checklist.md`
- Modify: `docs/deployment/SocialEval-deployment-and-operations-guide.md`
- Modify: `README.md`

- [ ] **Step 1: Write the operator checklist**

Checklist must include:
- server provisioning
- secret injection
- DNS and TLS
- database migration
- first admin account bootstrap
- worker start
- smoke verification
- rollback trigger

- [ ] **Step 2: Write the rollback plan**

Define:
- what constitutes a failed release
- how to roll back app version
- how to protect database compatibility during rollout

- [ ] **Step 3: Rehearse once in a staging-like environment**

Do one full dry run with:
- clean database
- real Redis
- real Postgres
- production-like env vars
- at least one full upload-to-report flow

- [ ] **Step 4: Capture launch sign-off**

Require explicit sign-off for:
- product scope
- security
- infrastructure
- operations

- [ ] **Step 5: Execute production launch**

Run only after all prior tasks are complete and verified.

---

## Recommended Rollout Order

1. Complete Task 2 first so production configuration stops being implicit.
2. Complete Task 1 next so the deployment target becomes reproducible.
3. Complete Task 3 before storing user data in cloud production.
4. Complete Task 4 before involving real experts and mail notifications.
5. Complete Task 5 before treating passing local tests as a release signal.
6. Complete Task 6 only after the system is already staging-ready.

## Launch Gate Definition

The project should be considered ready for first cloud production only when all of the following are true:

- A new machine can be provisioned from repo-owned deployment assets without tribal knowledge.
- `SECRET_KEY`, AI keys, SMTP credentials, database endpoints, Redis endpoints, and storage credentials are injected from production env only.
- File uploads and exported reports no longer depend on local ephemeral disk as the primary production persistence path.
- HTTPS termination, secure session cookies, and explicit origin allowlists are enabled.
- API, worker, Postgres, Redis, and frontend can be restarted independently with documented commands.
- CI, smoke tests, and one staging rehearsal all pass on the exact release candidate.

## Risks If Launch Happens Before This Plan

- Lost files or reports after host replacement because runtime data is still local-disk-centric
- Session leakage or broken browser auth in production because cookie and CORS behavior are still development-shaped
- Review emails silently not sending because the current mail path is log-only
- Operational debugging gaps because structured logging exists in code but is not yet wired into startup
- Manual, non-reproducible deployment causing configuration drift between environments
