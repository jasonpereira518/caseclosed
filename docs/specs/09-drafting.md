# Cycle 9 — Drafting (Functional Spec)

Date: 2026-08-17. Status: approved and implemented.

## Cycle-close notes (2026-08-17)

- Implemented as specified; 222 tests green. Live-verified in the demo: Edit opens a textarea with the fixture memo, Save is demo-blocked with a toast, Cancel restores the read view, Export button coexists with edit mode (exports the on-screen text, unsaved edits included).
- Export docx assertions covered by parsing the generated file with python-docx in tests (BRIEF vs MEMORANDUM title, FROM carries the user's name, filename from matter title).

## Behavior contract (after this cycle)

### 1. Drafts are genuinely editable

- The Draft panel gains an **Edit** mode: a plain textarea over the draft text with explicit **Save** / **Cancel**. Save persists through new `POST /draft/save` `{context_id, draft_text}` → `drafts/current` (404 for inaccessible matters, 400 for empty text). Export always uses what's on screen, edits included.
- The landing FAQ / README's "drafts remain editable" claim becomes true.

### 2. Export reflects the document

- The docx title follows the stored `draft_type`: `MEMORANDUM` or `BRIEF`.
- `FROM:` prefills with the signed-in user's display name (fallback email); `TO:` stays `[Recipient]`.
- The download filename comes from the server's matter-title-based name — the frontend parses `Content-Disposition` instead of hardcoding `legal_memo.docx`.

### 3. Generate confirms before replacing an existing draft

Two-step confirm on the Generate button (same pattern as document delete): when a draft exists, the first click arms "Replace draft?", the second proceeds. No browser dialogs.

### 4. Hygiene

`/draft` validates `doc_type` ∈ {memo, brief} (400 otherwise) — previously any string flowed into the LLM prompt verbatim.

## Out of scope

- Rich-text editing, versioning/history, additional document types or export formats (PDF).
- Draft prompt/structure changes (Cycle 4 already added role-awareness).

## Implementation notes

- `routes/draft.py`: validation, `/draft/save`, export title/FROM/filename; `app.py`: `/draft/save` path. `static/script.js`: edit mode, filename parse, two-step generate. `static/demo.js`: `/draft/save` → demo-blocked. Tests: `tests/test_draft_cycle9.py` (validation, save matrix, export docx assertions via python-docx parse).

## Verification

`python -m pytest` green; `node --check`; demo spot-check (edit mode togglable, save blocked with toast).
