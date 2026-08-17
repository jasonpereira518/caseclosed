# Cycle 6 — Chat Core (Functional Spec)

Date: 2026-08-17. Status: approved and implemented.

## Cycle-close notes (2026-08-17)

- Implemented as specified; 190 tests green, no live model calls in the suite (any classifier failure — including "no credentials in CI" — lands on the regex fallback by design).
- `classify_intent` kept its name as the heuristic (existing tests pin it); `resolve_intent` is the model-first entry point.
- No frontend or demo changes were needed: intent logic is entirely server-side and the demo's seeded answers bypass it.
- Live-model behavior (classification quality) is worth a spot-check next time the app runs against real Gemini — every misclassification degrades gracefully to the old behavior, never to an error.

## Behavior contract (after this cycle)

### 1. Intent is decided by a fast-model classifier, with the regex as fallback

- New `services/llm.classify_chat_intent(message)` (CHAT_FAST_MODEL, strict-JSON) labels each message one of: `legal_research`, `grounded_question`, `matter_summary`, `matter_update`, `acknowledgment`.
- The orchestrator uses it via `resolve_intent(message)`: an invalid label or any classifier failure falls back to the existing regex heuristic (renamed, kept verbatim) — chat never breaks because the classifier hiccuped.
- The pending-clarifying-questions override is unchanged: while questions are outstanding, the next message continues research.
- "Tell me about the weaknesses in our case" is a question now, not a record update.

### 2. Acknowledgments touch nothing

`acknowledgment` ("thanks", "ok got it", greetings) gets a brief canned reply, writes nothing to the record, runs no analysis, and reports `grounded: false, citations: []`. Real fact-sharing (`matter_update`) still folds into the description and re-runs extraction as today.

### 3. Grounded answers see the recent conversation

- `_answer` passes the last **6 turns** (user/assistant, each truncated to ~800 chars) into `answer_from_sources` as a new `history` argument. The prompt carries them under "RECENT CONVERSATION — context only, never cite it"; the closed citation set and insufficient-support fallback are unchanged (history is never a citable source).
- The research branch's clarify check (`check_if_more_info_needed`) receives the same history (optional param, default None) so it stops re-asking things already answered in conversation.

### 4. Hygiene

`matter_update`'s canned confirmation reports `grounded: false` (it cites nothing). No frontend change needed — rendering is unchanged.

## Out of scope

- Research pipeline internals (grading threshold, rerank, 20-cap) — Cycle 7.
- Timeline replace-vs-merge asymmetry — Cycle 8.
- Composer mode selector / explicit intent override (rejected in favor of LLM-only).
- Streaming, message editing, or chat-history UI changes.

## Implementation notes

- `services/chat_orchestrator.py`: `_heuristic_intent` (old `classify_intent` body), `resolve_intent`, `_acknowledge` branch, `_recent_turns(matter, limit=6)`, history pass-through; `_update_matter` grounded flag.
- `services/llm.py`: `classify_chat_intent` (strict JSON `{"intent": ...}`, raises on garbage so the orchestrator falls back); `check_if_more_info_needed(..., history=None)`.
- `services/grounding.py`: `answer_from_sources(..., history=None)`.
- Demo parity: none needed (intent logic is server-side; seeded demo answers bypass it).
- Tests: `tests/test_chat_cycle6.py` — classifier trust + fallback matrix, acknowledgment writes nothing, history reaches the grounding prompt with the never-cite rule, matter_update honesty; `classify_chat_intent` unit tests with a mocked model. Existing chat/worker suites updated only if they pinned the old classify path.

## Verification

- `python -m pytest` green.
- Manual: unchanged demo (seeded); real-app behavior validated by unit coverage (classifier calls are mocked — no live model calls in tests).
