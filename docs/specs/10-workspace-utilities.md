# Cycle 10 — Workspace Utilities (Functional Spec)

Date: 2026-08-18. Status: approved and implemented.

## Cycle-close notes (2026-08-18)

- Implemented as specified; 228 tests green. Live-verified in the demo: searching "dispatch" returns `Dispatch_Log.txt` with a Document badge ranked first, and the Documents filter tab renders.
- Time-report archived rows can't be demoed (demo has no archived matters); covered by code review + the shared `archivedHistory` global from Cycle 3.

## Behavior contract (after this cycle)

### 1. Search stops paying for text it never reads

`services/matters.load_matter` gains `include_document_text=True` (default preserves today's behavior everywhere else). Global search passes `False`: document text chunks are never fetched during a search, so search cost stops scaling with uploaded-document volume. Search results are unchanged for existing types (search never looked inside document text anyway).

### 2. Documents are searchable by filename

New result type `document` (weight 7, between case titles and notes): matches against `uploaded_documents[].filename`. A "Documents" filter tab joins the quick-switcher; `content_types` accepts `"documents"` (included in the default set). Clicking a document result switches to its matter and opens the document manager.

### 3. Archived matters are labeled in results

`search_user_contexts` marks every result from an archived matter with `archived: true` (status comes from the `list_matters` summary already in hand); the switcher renders an "Archived" chip on those rows. Archived matters remain searchable — that's half the point of archiving.

### 4. The time report covers all logged time

The report lists active *and* archived matters (archived rows marked), and the grand total includes both. Billable time no longer vanishes when a matter is archived.

## Out of scope

- Semantic/vector search for the quick-switcher (retrieval infra is for chat).
- Shortcuts, dictation, and the timer mechanics — reviewed, healthy, untouched.
- Searching *inside* document text (would need the retrieval index, not substring scans; parked).

## Implementation notes

- `services/matters.py` (`load_matter`/`_load_documents` flag), `models/search.py` (light load, documents type, archived flag), `static/script.js` (badge/filter/click/report), `templates/workspace.html` (filter tab), demo parity: `demo.js` localSearch gains filename matching + fixture docs already exist.
- Tests: `tests/test_search_cycle10.py` — light-load flag respected and used by search, filename results + filter, archived flag propagation.

## Verification

`python -m pytest` green; `node --check`; demo spot-check (documents tab in switcher, filename hit, time report renders).
