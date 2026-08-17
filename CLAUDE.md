# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Case Closed: an AI legal research assistant. Flask backend, server-rendered Jinja templates + vanilla JS/CSS frontend, Firestore as system of record, Gemini (Vertex AI) for model calls, CourtListener for case search, Document AI for OCR, Cloud Tasks for background jobs, Google Cloud Vector Search for semantic retrieval. Clerk handles identity (Google-only sign-in, the sole provider).

The `clerk-nextjs/` directory is a separate scaffolded Next.js experiment, not part of the running application — don't treat it as part of the Flask app's architecture.

## Commands

```bash
# Run the app locally (port 5050 by default)
python app.py

# Run all tests
python -m pytest

# Run a single test file / test
python -m pytest tests/test_worker.py
python -m pytest tests/test_worker.py::WorkerTests::test_chat_job_dispatches_and_succeeds

# Install deps
pip install -r requirements.txt

# Preflight-check env vars for production without touching cloud resources
python scripts/preflight.py --production

# Deploy (no traffic) -> verify the tagged URL -> promote. Never edit the
# service's env in the console; it comes from deploy/cloudrun.*.yaml.
./scripts/deploy_cloud_run.sh --profile domain
./scripts/deploy_cloud_run.sh --profile domain --promote
./scripts/deploy_cloud_run.sh --rollback <revision>

# Firestore migration (legacy -> normalized workspace model)
python scripts/migrate_firestore_v2.py --report migration-report.json
python scripts/migrate_firestore_v2.py --apply --report migration-report-applied.json

# Firebase -> Clerk user migration (dry run, then --apply; --write-firestore-mapping only at cutover)
python scripts/migrate_firebase_user_to_clerk.py /tmp/caseclosed-firebase-users.json
```

Tests use `app.test_client()` against the real Flask app (see `tests/test_landing_routes.py`); no separate test server or fixture DB is spun up — Firestore/external calls are mocked per-test with `unittest.mock.patch`.

## Architecture

### Request flow: sync gateway, async work

Almost all mutating work (`/chat`, `/upload`, `/analyze`, `/draft`, `/intake`) is modeled as a **job**, not a synchronous handler:

1. Browser POSTs to a route; Flask authenticates + authorizes the matter, then creates a Firestore job doc under `workspaces/{workspace}/matters/{matter}/jobs/{job}` and returns `202` with `job_id`/`status_url`.
2. `client_message_id` (chat) makes the job ID deterministic, so retried requests don't duplicate work.
3. Locally (`TASKS_MODE=inline`), a daemon worker thread in the web process picks up the job. In production (`TASKS_MODE=cloud`), Cloud Tasks delivers it via OIDC-verified POST to `/internal/jobs/run`.
4. `services/worker.py` is the single dispatcher/status-machine entrypoint for all job types (chat, matter_analysis, document ingestion, account export) — this was deliberately unified from three separate hand-rolled polling loops (see git history around "Unify matter and account jobs onto one status machine").
5. Browser polls `GET /api/matters/{matter}/jobs/{job}` for `queued` → `running` → `succeeded`/`failed`/`cancelled`, with retry/cancel endpoints.

When adding a new mutating feature, follow this job pattern rather than doing the work inline in the route handler.

### Firestore data model

```
workspaces/{workspace_id}
  members/{uid}
  matters/{matter_id}
    state/current
    messages/{message_id}
    documents/{document_id}/text_chunks/{chunk_id}
    knowledge_chunks/{chunk_id}
    cases/{case_id}
    timeline_events/{event_id}
    drafts/current
    jobs/{job_id}
```

`matter_index` (top-level) is only a locator mapping opaque matter IDs to workspaces — it is never itself an authorization source. All matter access must go through `services.matters.require_matter`, which checks personal-workspace ownership or team membership (+ non-admin members must be assigned to the matter). Browser-side Firestore/Storage access is denied by security rules; **Flask is the only authorized data gateway**.

### Identity

Clerk is the only identity provider (the Firebase Authentication rollback path was retired in Cycle 2 of the functional refresh; rollback story is `git revert` + redeploy). `app.py`'s `login_manager.request_loader` verifies Clerk session tokens via `services/clerk_auth.py`. Migrated Firebase users carry their old UID as the Clerk `external_id`; the custom Clerk session claim `userId: {{user.external_id || user.id}}` is what makes the stable application user ID. New accounts are created `access_status: pending` (early-access gate); accepting a team invitation approves them, and admins listed in `ADMIN_EMAILS` manage the rest at `/admin/access`.

`PROTECTED_JSON_PATHS` in `app.py` controls whether an unauthenticated request to a given path gets a `401` JSON body vs. an HTML redirect to login. `app.py` self-checks at import time that every path listed there actually has a registered route — if you rename/remove a route referenced there, the app will fail fast on startup rather than silently start redirecting API callers.

### Retrieval / grounding

Chat answers are grounded: retrieval happens separately for private matter evidence (`services/retrieval.py`, tenant-filtered by `workspace_id`/`matter_id`) and shared law (`services/legal_corpus.py`, filtered by jurisdiction). The model may only cite source IDs present in its retrieval packet — `services/grounding.py`'s citation validator drops unknown IDs, and an answer with zero valid citations is replaced with an explicit insufficient-support response rather than shown as grounded. Production retrieval uses Vector Search (`VECTOR_SEARCH_ENABLED=true`); local dev falls back to lexical Firestore search under the same authorization/jurisdiction filters.

### Routes vs. services

`routes/` are thin Flask blueprints (registered in `routes/__init__.py`) handling HTTP concerns, auth, and job creation. Business logic lives in `services/` (one module per concern — `matters.py`, `tenancy.py`, `jobs.py`, `worker.py`, `retrieval.py`, `llm.py`, `courtlistener.py`, `document_ingestion.py`, etc.). `models/context.py` is a compatibility aggregate over the normalized matter records for older call sites.

One exception: `routes/demo.py` (the public, unauthenticated `/demo` sandbox behind the landing page) imports no service layer at all — no `services.llm`, `services.firestore`, or `models` — so it structurally cannot reach Gemini, CourtListener, or Firestore. It's served entirely from a static fixture, with `static/demo.js` stubbing `window.fetch` client-side. `tests/test_demo_route.py` AST-parses the module's imports to keep this from regressing quietly; don't add a service import there to fix something, even temporarily.

### Deployment

Production is Cloud Run (`us-central1`, project `case-closed-491121`), fronted by a free Cloud Run **domain mapping** — not a load balancer, which would bill a forwarding rule even at zero traffic.

The thing that trips people up: `config.py` flips `ENVIRONMENT` to `production` whenever `K_SERVICE` is set, which is always true on Cloud Run, and `app.py` then runs `require_runtime_config(production=True)` **at import time**. So a missing env var doesn't degrade a request — it kills the gunicorn worker before it binds a port, and the deploy fails with "container failed to start and listen on port". `scripts/deploy_cloud_run.sh` preflights the rendered profile locally to catch this before a build is spent.

Env lives in two committed, secret-free profiles under `deploy/`: `cloudrun.runapp.yaml` (the `*.run.app` URL, Clerk *development* keys) and `cloudrun.domain.yaml` (the public domain, Clerk *production* keys). The split is not cosmetic — a Clerk production instance serves its Frontend API from `clerk.<domain>` and sets its cookie there, so a `pk_live_` key loaded from a `*.run.app` origin yields a third-party cookie and sign-in fails.

Cost posture is deliberate and worth preserving: `min-instances=0` with CPU throttling (Cloud Run free tier), `VECTOR_SEARCH_ENABLED=false` (Firestore lexical fallback instead of billed always-on index replicas), and `DOCUMENT_AI_PROCESSOR_ID` omitted (OCR bills per page with no free tier). Each has a one-line switch documented in the profile.

## Key docs in this repo

- `README.md` — setup, env vars, Docker, full deployment/migration commands.
- `BACKEND_ARCHITECTURE.md` — full request/data flow, chat API contract, production setup checklist, cost-control flags (`ENABLE_VECTOR_SEARCH`, `ENABLE_LEGAL_CORPUS_SYNC`).
- `PRODUCT.md`, `DESIGN.md` — product/design specs (landing page, auth UI).
