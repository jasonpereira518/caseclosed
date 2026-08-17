# Cycle 4 — Client Intake (Functional Spec)

Date: 2026-08-17. Status: approved and implemented.

## Cycle-close notes (2026-08-17)

- Implemented as specified; 169 tests green. Live-verified in the demo: intake modal prefills every field (including the role radio) from the fixture's stored intake; the header role selector syncs from `state.role` ("Plaintiff" from the fixture) and persists selections.
- **Found during implementation:** the header role dropdown offered *Defendant / Prosecutor* — a criminal-law leftover that didn't match intake's vocabulary at all. It now offers the same four roles as the intake radio (plaintiff / defendant / third party / witness), which is what `/matter/role` validates.
- Demo fixture updated for parity: intake uses `user_role` (matching the real payload shape) and the matter carries root `role: "plaintiff"`.

## Behavior contract (after this cycle)

### 1. Intake jurisdiction is authoritative for research

When `state.intake.jurisdiction` is set, retrieval and case-law filtering use it. The LLM-extracted jurisdiction (`analysis.jurisdiction[s]`) is only the fallback for matters whose intake never specified one. Explicit user input outranks model inference. Applies to the chat orchestrator's grounded-answer retrieval and its research branch.

### 2. Intake is editable: prefill + replace

- **Prefill:** opening the intake modal on a matter with stored intake pre-fills every field from `state.intake` (including key-date rows and the role radio). A fresh matter opens blank.
- **Replace, don't stack:** the `CASE INTAKE` block written into the matter description is delimited by explicit markers (`===== CASE INTAKE =====` / `===== END CASE INTAKE =====`). Resubmission replaces the marked block in place; only when no marked block exists (first submission, or a legacy pre-marker matter) is it appended. `state.intake` is overwritten as today.
- **Chat log:** the first submission appends the intake block as a user message (as today); a resubmission appends a message headed `CASE INTAKE (UPDATED)` so the conversation records the change without pretending it was the first.
- **Title rule:** the case title becomes the matter title when the matter title is still `"New Session"` **or** still equals the *previous* intake's case title (i.e. the user never manually renamed). A manual rename is never overwritten.
- Analysis re-queues on every submission (unchanged).

### 3. One party-role, wired end-to-end

`state.role` becomes the single source of truth for "which side does this lawyer represent":

- Intake's role radio writes it on submit.
- The header ROLE dropdown reads it (via the loaded matter) and writes it through a new `POST /matter/role` `{context_id, role}` endpoint (synchronous field patch; allowed values plaintiff / defendant / third party / witness, case-insensitive). The current dropdown is write-only into a dead variable; that variable now round-trips.
- Header dropdown and intake radio stay in sync because both read the reloaded matter state.
- **Prompts:** when `state.role` is set, chat answers (grounded Q&A and research) and generated drafts are told the client's role ("the lawyer represents the {role}") so output argues from the right side's perspective. No role set → prompts unchanged.
- Default remains visually "Defendant" in the header, but nothing is persisted until the user actually chooses or submits intake.

### 4. Hygiene

- Intake errors surface through the app's toast system; the browser `alert()` goes away.
- Role-validation error styling moves from inline JS styles to a CSS class (`.intake-role-error`).

## Out of scope

- Changing the intake field set, jurisdiction list, or modal layout (visual pass).
- Back-filling markers into legacy descriptions (first resubmission on a legacy matter appends one marked block; the old unmarked text is left as history).
- Feeding role into the analysis-extraction chain (it extracts *all* parties' roles; the client-role perspective matters for answers/drafts, not extraction).

## Implementation notes

- `PROTECTED_JSON_PATHS` in `app.py` gains `/matter/role` (literal path, startup-asserted).
- `_jurisdiction` in `services/chat_orchestrator.py` gains the intake-first preference; call sites pass the matter's intake.
- Role line injection: `services/chat_orchestrator.py` (answer + research prompt assembly) and `services/draft*` path (`process_draft_job` → `draft_legal_document`).
- Frontend: `setupIntakeModal` (script.js) gets prefill from a `currentIntake` global set in `applyContextToUI` (matters.js); header role selector persists via the new endpoint and initializes from loaded state. `demo.js` stubs `/matter/role` with a local OK (harmless, resets on reload).
- Files: `routes/intake.py`, `routes/context.py` (role endpoint), `app.py`, `services/chat_orchestrator.py`, draft job path, `static/script.js`, `static/matters.js`, `static/demo.js`, `static/app.css`, tests `tests/test_intake_cycle4.py` + updates to existing intake/chat tests.

## Verification

- `python -m pytest` green.
- Live (demo can't submit intake — server-side checks via tests; browser check on `/demo` limited to modal open/prefill wiring not regressing).
- Unit-verified: block replacement idempotence, title rule matrix (New Session / matches old intake title / manually renamed), role persistence + allowed values, jurisdiction preference order, role line present in prompt assembly when set and absent when not.
