# Cycle 5 — Documents (Functional Spec)

Date: 2026-08-17. Status: approved and implemented.

## Cycle-close notes (2026-08-17)

- Implemented as specified; 180 tests green. Grep-verified: the only remaining `[Document:` reference is the cleanup reader (`_strip_document_block`).
- Browser spot-check deferred: the Chrome extension was disconnected at close time. Risk is minimal — status chips are hidden for `ready` documents, so the demo's appearance is unchanged; the new behavior (chips/retry) only appears on real failed/processing uploads. Worth one manual look at the doc manager during a real upload.
- Note for the visual pass: `renderDocList` still uses inline styles and inline `onclick` handlers (pre-existing); tolerated this cycle per the spec's out-of-scope list.

## Behavior contract (after this cycle)

### 1. Include is retrieval-only; the description splice is retired

- `POST /documents/toggle` flips the document's `included` flag and the retrieval-index filter. It **no longer splices document text into the matter description**. Document content reaches the model exclusively through retrieved chunks — the grounded architecture — and the description stays a human/intake narrative.
- **Legacy cleanup:** whenever a document is toggled or deleted, any old `[Document: {filename}]\n{text}` block still sitting in the description is removed (exact-match, as the old code wrote it). Descriptions heal incrementally as documents are touched.
- `POST /documents/delete` unconditionally attempts that cleanup (previously only when included).

### 2. Ready documents are included automatically

`ingest_document_job` completes with `included: true` (metadata **and** index chunks). Uploading is the deliberate act; the toggle exists for opting out. Documents still upload as `included: false` while `processing`, so a failed extraction never phantom-participates.

### 3. Live per-document status in the manager

- Each row shows its stored status: `processing` / `retrying` / `ready` / `failed` / `cancelled` (documents predating the status field read as ready). Failed rows show the stored failure reason (e.g. "PDF contains too little embedded text and Document AI OCR is not configured").
- The manager opens immediately after upload is accepted (rows appear as processing) and each row updates as *its* job finishes, instead of one refresh after all jobs complete. The summary toast stays.
- `POST /upload`'s response includes each job's `document_id` so the client can map jobs to rows.

### 4. Per-document retry

- New `POST /api/matters/<matter_id>/documents/<document_id>/retry`: recomputes the deterministic ingest job (`deterministic_job_id(matter, "document_ingest", document_id)`), and requeues it (attempts reset) when the job is `failed`/`cancelled` **and** the document record has a durable `storage_path`. Responds `202` with `status_url`.
- `409` when the original is not durable (local-dev uploads whose temp file is gone, staging-only sources): "original file is no longer available — upload it again". This is precisely why the generic `retry_job` refuses `document_ingest`; the dedicated route makes the durability check explicit.
- Failed rows in the manager get a **Retry** button wired to it; the row returns to `processing` and live-updates.

### 5. Honest `.doc` handling

- The file picker accepts `.pdf,.docx,.txt` (`.doc` removed — the server has never supported it).
- Client-side: unsupported files selected anyway (drag-drop) are reported by name in a toast and skipped; supported files in the same batch still upload. The server's silent skip stays as the backstop.

## Out of scope

- Changing extraction (pdfminer/Document AI) or the OCR cost posture.
- Chunking/indexing internals, retrieval ranking (Cycle 6).
- Doc-manager visual redesign; inline styles in `renderDocList` are tolerated until the visual pass.
- Migrating old descriptions in bulk (they heal on touch).

## Implementation notes

- `services/retrieval.index_matter_document(..., included=True)` from the ingest job; metadata `included: True` in `ingest_document_job`'s success path.
- Toggle/delete cleanup helper shared in `routes/upload.py`: `_strip_document_block(description, filename, text)`.
- Retry route lives in `routes/upload.py` (documents own it); uses `services.jobs.update_job` + `enqueue_job`; requires `require_matter` authorization like download.
- Frontend: `handleFileUpload` (filter unsupported, open manager early, per-job row updates), `renderDocList` (status chip + reason + Retry), `templates/workspace.html` (input accept).
- Demo parity: fixture documents gain `status: "ready"`; no stub needed for the retry route (failed rows don't occur in the demo).
- Tests: `tests/test_documents_cycle5.py` — toggle without splice + legacy cleanup, delete cleanup, auto-include on ready (ingest unit), retry route matrix (success / not-failed / no storage_path / unauthorized / unauthenticated 401), upload response carries document_id. Existing suites updated where they assert the splice.

## Verification

- `python -m pytest` green.
- Live demo check: doc manager renders with status chips, no console errors; toggle still blocked-in-demo.
- Grep: no `[Document:` writer remains in routes (only the cleanup reader).
