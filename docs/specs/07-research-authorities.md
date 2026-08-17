# Cycle 7 — Legal Research & Authorities (Functional Spec)

Date: 2026-08-17. Status: approved and implemented.

## Cycle-close notes (2026-08-17)

- Implemented as specified; 203 tests green. Live-verified in the demo: the Authority detail view loads "what this case is about" through `/case/describe` (fixture snippet appears after the stub's simulated think).
- Merge semantics: annotated survivors keep bookmarks/notes/follow-ups/treatment/description; re-found cases refresh `relevance_score`, `relevance_reason`, `relevance_dimensions`, `initial_score`, and `snippet`.
- Batch grading uses `SCORER_MODEL`; any unusable batch response falls back to the per-case `grade_case` loop for that round.

## Behavior contract (after this cycle)

### 1. Re-research preserves your work

- A case is **annotated** when it is bookmarked, has notes, or has follow-up Q&As. Annotated cases survive every research run.
- New results are merged via `merge_research_results(existing, fresh, cap=20)` (pure function in the orchestrator):
  - Keyed by `pdf_link` → `citation` → `title` (the pipeline's existing dedupe key).
  - A fresh result matching an annotated case **refreshes** its relevance fields (score, reason, dimensions, snippet) while keeping bookmarks, notes, follow-ups, cached treatment, and description.
  - Unannotated existing cases are replaced by the fresh list, as today.
  - The 20-case cap applies to *unannotated* results only — the user's annotated cases are never evicted by it.
  - Output sorted by relevance score, descending.

### 2. Wider net, batched grading

- `query_courtlistener` returns up to **10** results per query (was 4) → ~30 candidates across 3 rounds.
- Grading becomes **one model call per query round** (`services/llm.grade_cases_batch(summary, cases, analysis)` — strict-JSON array of `{index, score, reason, dimensions}`). Any batch failure falls back to the existing per-case `grade_case` loop for that round — wider research never breaks because one batch call hiccuped.
- Threshold (≥15), rerank-if-more-than-3, and the cap semantics above are unchanged.

### 3. `/case/describe` finally has a caller

The Authority detail view shows a "What this case is about" description: served from the case's cached `description` when present, otherwise fetched once from `/case/describe` (which caches it server-side — already built). Loading placeholder while fetching; failure shows nothing rather than an error card. The demo already behaves this way; the real app catches up.

### 4. Treatment checks are retryable; citations normalized

- `check_case_treatment` returns `checked: false` on API failure, rate limit, or missing cluster id — only real verdicts (`good` / `warning` / `negative`) are cached with `checked: true`. The route's blanket exception handler does the same. The lazy fetch-on-render loop then naturally retries next time the case is shown.
- CourtListener v4 sometimes returns `citation` as a list; `query_courtlistener` normalizes it to a comma-joined string (first two entries).

## Out of scope

- Statutes sourcing, strength scoring, timeline (Cycle 8 owns analysis/chronology).
- The shared legal corpus sync (machine endpoint; untouched).
- Authority tab visual redesign.
- Treatment methodology (keyword-based citing search stays; it's labelled as automated hint with "verify independently" tooltips).

## Implementation notes

- `services/chat_orchestrator.py`: `merge_research_results` + `_research` merge + batch-grading with per-case fallback.
- `services/llm.py`: `grade_cases_batch` (raises on unusable output so the caller falls back).
- `services/courtlistener.py`: `[:10]`, citation normalization, `checked: false` failure paths.
- `routes/chat.py`: treatment exception path `checked: false`.
- `static/script.js`: case detail description section + fetch; no other UI changes.
- Demo parity: `demo.js` `/case/describe` stub already exists; fixture cases carry real-verdict treatments (unchanged).
- Tests: `tests/test_research_cycle7.py` — merge-function matrix (annotated survive / refresh on rematch / cap exempts annotated / sort), batch grading unit + fallback, courtlistener limit + citation normalization + failure-not-cached, route exception path, and one `_research` integration test with the full mock harness asserting the merged list reaches `replace_matter_records`.

## Verification

- `python -m pytest` green.
- Demo spot-check when the browser is available: Authority detail shows the description (fixture snippet), treatment badges unchanged.
