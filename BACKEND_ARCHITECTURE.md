# Backend architecture

Case Closed uses Flask as the authenticated gateway, Firestore as the system of record, Cloud Tasks for durable work, Gemini on Vertex AI for model calls, CourtListener for case search, Document AI for OCR, and Google Cloud Vector Search for semantic retrieval.

## Request and data flow

```text
Browser workspace
  │ POST /chat {matter_id, message, client_message_id}
  ▼
Flask authentication + matter authorization
  │ creates workspaces/{workspace}/matters/{matter}/jobs/{job}
  │ returns 202 + status_url
  ▼
Cloud Tasks ──OIDC──▶ POST /internal/jobs/run
  │
  ▼
Intent router
  ├─ matter update ─────▶ structured matter state
  ├─ grounded question ─▶ private matter chunks + shared law ─▶ Gemini
  └─ legal research ────▶ clarification ─▶ CourtListener ─▶ scoring/synthesis
  │
  ▼
Citation validator ─▶ assistant message + normalized panels + job result
  ▲
Browser polls GET /api/matters/{matter}/jobs/{job}
```

The API acknowledges chat without waiting for model or search calls. `client_message_id` produces a deterministic job ID, so retried browser requests do not create duplicate work or duplicate messages. A Firestore transaction claims queued jobs, and Cloud Tasks retries transient chat failures up to `JOB_MAX_ATTEMPTS`.

## Firestore ownership model

All matter access passes through `services.matters.require_matter`. Personal workspaces require the owner. Team workspaces require active membership and, for non-admin members, assignment to the matter.

```text
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

The top-level `matter_index` maps opaque matter IDs to workspaces. It is only a locator; authorization is still checked against the workspace and matter. Browser Firestore and Storage access is denied by rules—the Flask backend is the data gateway.

## Chat contract

Create work:

```http
POST /chat
Content-Type: application/json

{
  "matter_id": "...",
  "message": "What deadline does the uploaded notice establish?",
  "client_message_id": "browser-generated-uuid"
}
```

The response is `202 Accepted` with `job_id`, `status`, `progress`, and `status_url`. Polling returns `queued`, `running`, `succeeded`, `failed`, or `cancelled`, plus a stage and progress percentage. Failed/cancelled chat jobs can be retried with `POST .../retry`; active work can be cancelled with `DELETE .../jobs/{job_id}`.

Grounded answers return:

```json
{
  "status": "answer",
  "message": "...",
  "grounded": true,
  "citations": [{
    "source_id": "...",
    "source_type": "uploaded_document",
    "title": "notice.pdf",
    "locator": "chunk 2",
    "url": "",
    "quote": "..."
  }]
}
```

The model can cite only source IDs included in its retrieval packet. Unknown IDs are dropped; an answer without at least one valid citation is replaced with a transparent insufficient-support response. Matter-update acknowledgements are not legal answers and therefore do not require citations.

## Document ingestion and retention

Uploads are jobs too. In Cloud Tasks mode the original is staged under `staging/{workspace}/{matter}/{document}` only long enough for the worker to extract it. Native PDF text is attempted first; low-text PDFs use Document AI when configured. DOCX and TXT are supported; legacy DOC is rejected explicitly.

After extraction, only metadata, extracted text, and retrieval chunks are retained. The staging object is deleted in a `finally` block on success, failure, or cancellation. Configure a short Cloud Storage lifecycle rule on `staging/` as crash protection. There is intentionally no matter-document download endpoint.

## Knowledge retrieval

Matter document chunks carry `workspace_id` and `matter_id`. Shared-law chunks carry a canonical jurisdiction code and official source URL. Production retrieval uses separate Vector Search collections for private matter evidence and shared law. Local development falls back to lexical Firestore retrieval while applying the same matter authorization and jurisdiction filters.

`services.legal_corpus` registers federal, all 50 states, and DC. Official publishers have incompatible formats, so each enabled source is an explicit JSON adapter in `LEGAL_SOURCE_REGISTRY`; unconfigured jurisdictions are visible as `configuration_required`, not silently filled from unofficial mirrors. A protected daily endpoint, `POST /internal/legal-corpus/sync`, performs bounded syncs.

## Production setup checklist

1. Create the Cloud Tasks queue and grant its service account Cloud Run invoker access.
2. Set `TASKS_MODE=cloud`, the queue variables, worker URL/audience, and task service account. The worker verifies Google-signed OIDC tokens; the static worker token is an optional emulator fallback only.
3. Create private and shared Vector Search collections with the fields emitted by `services.retrieval`, then enable `VECTOR_SEARCH_ENABLED`.
4. Create a Document AI OCR processor and set its processor ID.
5. Add a Storage lifecycle rule that deletes `staging/` objects after one day or less.
6. Configure and validate each official jurisdiction adapter, then schedule the protected corpus endpoint daily.
7. Run the Firestore migration dry-run before `--apply`, deploy deny-all client rules, and monitor job failure rate, duration by stage, retrieval fallback warnings, and citation rejection rate.

Gemini inference uses a separate endpoint setting from regional infrastructure. The default `GEMINI_LOCATION=global` serves the GA fast/reasoning tiers (`gemini-3.5-flash-lite` and `gemini-3.6-flash`); use an approved `us` or `eu` endpoint when the deployment requires jurisdictional processing and the selected models support it.

Local development uses `TASKS_MODE=inline`; it preserves the same persisted job and polling contract but runs a daemon worker thread in the web process.

Repository tooling:

- `python scripts/preflight.py --production` validates environment variables without contacting cloud services.
- `scripts/provision_gcp.sh --check` prints the idempotent provisioning operations; `--apply` executes them after the required environment variables are supplied.
- `python scripts/create_document_ai_processor.py --apply` creates or reuses the OCR processor and prints its processor ID.
- `scripts/verify_gcp.sh` performs read-only post-deployment checks against Cloud Run, Cloud Tasks, Vector Search, Document AI, and Storage.

The Vector Search collections use a managed `text_embedding` field generated from each object’s `text` with `gemini-embedding-001`. Stored objects use `RETRIEVAL_DOCUMENT`; searches use `RETRIEVAL_QUERY`. Private inline filters are `workspace_id`, `matter_id`, and `included`; shared-law filters are `jurisdiction` and `source_type`.

Cost controls are opt-in: `ENABLE_VECTOR_SEARCH=true` provisions billed vector indexes, and `ENABLE_LEGAL_CORPUS_SYNC=true` provisions the daily scheduler. Both default to `false`; Firestore retrieval remains available when Vector Search is disabled. OIDC audiences use the Google-generated Cloud Run service root URL while worker targets append their route paths.
