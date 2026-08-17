# Cycle 8 — Matter Analysis & Chronology (Functional Spec)

Date: 2026-08-17. Status: approved and implemented.

## Cycle-close notes (2026-08-17)

- Implemented as specified; 213 tests green. Live-verified in the demo: chronology delete removes an event (7 → 6), remove buttons render, and an injected `<img onerror>` manual event renders as inert text (`window.__xss` never fired, no element injected).
- The XSS fix is worth back-porting attention: it was the only unescaped `innerHTML` path found; a future `/security-review` pass across all render paths is still worthwhile.

## Behavior contract (after this cycle)

### 1. Manual timeline events survive every rebuild

- `merge_timeline(existing, extracted)` (in `services/analysis_orchestrator.py`): manual events (`source: "manual"`) from the existing timeline are preserved; extracted events are replaced by the fresh extraction; the combined list is re-sorted (`sort_timeline`).
- Used by **both** rebuild paths: `process_analysis_job` and the chat research branch. The machine never destroys the lawyer's hand-entered chronology — the same rule Cycle 7 gave the authority list.

### 2. Any timeline event is deletable

- `POST /timeline/delete` `{context_id, index, date, description}`: removes the event at `index` **only if** its date and description match the payload (guards against a stale client after a concurrent rebuild — mismatch returns `409`). Bad index → `400`. Returns the updated sorted timeline, same shape as `/timeline/add`.
- Applies to manual *and* extracted events — the lawyer curates the record; a wrong extracted date shouldn't be immortal until the next analysis run.
- Every chronology row gets a small remove action. Demo stubs it locally (non-persistent, like add).
- Error-code alignment: `/timeline/add` and `/timeline/delete` both return **404** for inaccessible matters (add currently says 403; Cycle 3 standardized matter routes on indistinguishable-404).

### 3. Security fix: timeline rendering escapes user content

`renderTimeline` currently injects `event.description` and `event.date` into HTML unescaped — a stored XSS reachable by any workspace member via a manual event. Both fields go through `escapeHtml`. (Ships regardless of the rest; it's the only unescaped render path found.)

## Out of scope

- Editing events in place (delete + re-add covers it for now).
- Strength-scoring methodology, statutes sourcing, Record-tab layout.
- Moving `sort_timeline` out of `services/llm.py` (cosmetic; noted for a later cleanup).

## Implementation notes

- `services/analysis_orchestrator.py`: `merge_timeline` + use in `process_analysis_job`; `services/chat_orchestrator.py`: import + use in `_research`.
- `routes/analyze.py`: delete endpoint + 404 alignment; `app.py`: `/timeline/delete` joins `PROTECTED_JSON_PATHS`.
- `static/script.js`: escape fix + remove buttons + delete call; `static/demo.js`: `/timeline/delete` stub.
- Tests: `tests/test_analysis_cycle8.py` — merge matrix, analysis-job preservation, research-branch preservation, delete route matrix (401/404/400/409/success), add-route 404 alignment.

## Verification

- `python -m pytest` green; `node --check` on touched JS.
- Demo spot-check when browser available: chronology renders escaped content, remove buttons present, demo delete updates the panel locally.
