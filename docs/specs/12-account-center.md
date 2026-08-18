# Cycle 12 — Account Center (Functional Spec)

Date: 2026-08-18. Status: approved and implemented.

## Cycle-close notes (2026-08-18)

- Implemented as specified; 243 tests green. The export test builds a real in-memory ZIP and asserts `time.json` contents plus the latest-only cleanup call.
- Export cleanup is best-effort (logged, never fails a successful export); avatar object deletion likewise best-effort with the field clear as the source of truth.
- Account page needs a real Clerk session — the Remove-photo control is flagged for Jason's next signed-in look alongside Cycle 11's team UI.

## Behavior contract (after this cycle)

### 1. Exports include logged time

Each matter in the export ZIP gains `time.json`: `{"total_seconds", "entries": [{seconds, created_at}, ...]}` via a new `services/matters.list_time_entries(matter_id, uid)` (authorized like every other matter read). The portable archive of a billable-hours tool finally carries the hours.

### 2. Only the latest export is retained

When a new export uploads successfully, older objects under `users/{uid}/exports/` are deleted (`services/storage.delete_prefix_except(prefix, keep_path)`). Bounded storage; the fresh signed link is the one that matters. Deletion failures are logged, never fail the export.

### 3. Avatars are removable

`DELETE /api/account/avatar`: deletes the stored object (best-effort), clears `avatar_storage_path` from the user doc, returns the refreshed profile. A Remove-photo control joins the avatar form.

## Out of scope

- Export format changes beyond time.json; profile field set; deletion semantics (reviewed, solid).

## Implementation notes

- `services/matters.py` (`list_time_entries`), `services/storage.py` (`delete_prefix_except`), `services/account_export.py` (time.json + cleanup call), `routes/account.py` (avatar DELETE), `templates/account.html` + `static/account.js` (Remove control).
- Tests: `tests/test_account_cycle12.py` — time.json content in a real in-memory ZIP (storage mocked), cleanup keeps only the new object, avatar DELETE matrix (401 / success clears field + deletes object / no-avatar no-op).

## Verification

`python -m pytest` green; `node --check static/account.js`. Account page needs a real session — covered by tests, flagged for Jason's next signed-in look.
