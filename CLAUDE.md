# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Case Closed: an AI legal research assistant. Flask backend, server-rendered Jinja templates + vanilla JS/CSS frontend, Firestore as system of record, Gemini (Vertex AI) for model calls, CourtListener for case search, Document AI for OCR, Cloud Tasks for background jobs, Google Cloud Vector Search for semantic retrieval. Clerk handles identity (Google-only sign-in); Firebase Authentication is a temporary rollback path being phased out.

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

`config.AUTH_PROVIDER` selects `clerk` (default) or `firebase` (temporary rollback). `app.py`'s `login_manager.request_loader` branches on this at request time — Clerk session tokens are verified via `services/clerk_auth.py`, Firebase session cookies via `firebase_admin`. Migrated Firebase users carry their old UID as the Clerk `external_id`; the custom Clerk session claim `userId: {{user.external_id || user.id}}` is what makes the stable application user ID.

`PROTECTED_JSON_PATHS` in `app.py` controls whether an unauthenticated request to a given path gets a `401` JSON body vs. an HTML redirect to login. `app.py` self-checks at import time that every path listed there actually has a registered route — if you rename/remove a route referenced there, the app will fail fast on startup rather than silently start redirecting API callers.

### Retrieval / grounding

Chat answers are grounded: retrieval happens separately for private matter evidence (`services/retrieval.py`, tenant-filtered by `workspace_id`/`matter_id`) and shared law (`services/legal_corpus.py`, filtered by jurisdiction). The model may only cite source IDs present in its retrieval packet — `services/grounding.py`'s citation validator drops unknown IDs, and an answer with zero valid citations is replaced with an explicit insufficient-support response rather than shown as grounded. Production retrieval uses Vector Search (`VECTOR_SEARCH_ENABLED=true`); local dev falls back to lexical Firestore search under the same authorization/jurisdiction filters.

### Routes vs. services

`routes/` are thin Flask blueprints (registered in `routes/__init__.py`) handling HTTP concerns, auth, and job creation. Business logic lives in `services/` (one module per concern — `matters.py`, `tenancy.py`, `jobs.py`, `worker.py`, `retrieval.py`, `llm.py`, `courtlistener.py`, `document_ingestion.py`, etc.). `models/context.py` is a compatibility aggregate over the normalized matter records for older call sites.

## Key docs in this repo

- `README.md` — setup, env vars, Docker, full deployment/migration commands.
- `BACKEND_ARCHITECTURE.md` — full request/data flow, chat API contract, production setup checklist, cost-control flags (`ENABLE_VECTOR_SEARCH`, `ENABLE_LEGAL_CORPUS_SYNC`).
- `PRODUCT.md`, `DESIGN.md` — product/design specs (landing page, auth UI).
