# Cycle 3 — Workspaces & Matters (Functional Spec)

Date: 2026-08-16. Status: approved and implemented.

## Cycle-close notes (2026-08-16)

- Implemented as specified; 154 tests green. Live-verified in the demo: sidebar renders post-split, Archive menu item present (blocked with a toast in demo mode), archived section hidden when empty, seeded chat + citations still work.
- The full CONTEXT MANAGEMENT section (463 lines) moved to `static/matters.js` — nothing had to stay behind; `script.js` is down to ~3,070 lines.
- **Pre-deploy step for Jason (unchanged):** run `python scripts/migrate_firestore_v2.py --report migration-report.json` against production and confirm the report is a no-op before shipping, since the lazy legacy migration no longer exists as a safety net.
- Switch/rename/archive/delete on an inaccessible matter now all return 404 (previously 403/500); the frontend treats any non-OK switch as "refresh the list".

## Behavior contract (after this cycle)

### 1. Matter archiving

A matter now has a lifecycle: **active → archived → (reopened | permanently deleted)**.

- `POST /contexts/archive` `{context_id}` sets the matter's root `status` to `"archived"`; `POST /contexts/unarchive` `{context_id}` sets it back to `"active"`. Both require the same authorization as delete. All matter data (messages, documents, analysis, draft, time) is untouched.
- `GET /contexts` returns **active matters only** by default, plus an `archived_count`. `GET /contexts?include_archived=1` also returns archived matters (each row carries `status`).
- Archived matters are excluded from every auto-selection path: `GET /context`'s fallback chain, `/contexts` auto-create, delete's next-matter pick, and workspace activation. Archiving the currently-active matter behaves exactly like deleting it: the backend switches to the next active matter (or auto-creates) and returns the same switch payload.
- **Sidebar:** each session card's menu gains "Archive". Below the active list, an "Archived (n)" toggle section lists archived matters with "Reopen" and "Delete" actions. Clicking an archived matter's card does nothing except via Reopen (an archived matter can't silently become active). Simple functional markup; styling deferred.
- **Demo parity:** `demo.js` stubs `/contexts/archive` and `/contexts/unarchive` as demo-blocked mutations (matching new/rename/delete); the fixture matter has no `status`, which reads as active.

### 2. Legacy migration retired

The lazy `user_contexts` → workspace-model migration is deleted: `_migrate_legacy_context`, `_migrate_legacy_for_user`, and the per-load scan in `list_user_contexts`, plus the legacy fallbacks in `get_context` / `get_context_or_default` / `get_or_create_context`. `scripts/migrate_firestore_v2.py` **stays** as the explicit tool.

**Pre-deploy step for Jason:** run `python scripts/migrate_firestore_v2.py --report migration-report.json` once against production and confirm the report shows nothing left to migrate before shipping this cycle. (Lazy adoption has been running since the migration, so this is expected to be a no-op — but verify, don't assume.)

### 3. Auto-create stays (explicitly chosen)

A workspace is never empty: `GET /context`, `GET /contexts`, delete, archive, and workspace activation all auto-create a "New Session" when no active matter exists. Now documented as intended behavior.

### 4. Hygiene

- **Lightweight authorization.** `context_belongs_to_user`, rename, archive, and delete authorize via `services.matters.require_matter` (locator + membership only) instead of loading every subcollection. `/contexts/switch` loads the full matter **once** (it currently loads twice). `rename_context` patches only the title.
- **Honest error codes.** A matter that doesn't exist *or* isn't accessible returns **404** on switch/rename/archive/delete (previously 403, and 500 for failed deletes) — not-found and forbidden are indistinguishable by design, matching `require_matter`'s "the index is never an authorization source" stance.
- **Deduplicated switch payload.** One `_switch_payload(context_id, user_id)` helper serves `/contexts/switch`, `/contexts/delete`'s fallback, and archive's fallback; the 35 duplicated lines in delete go away.
- The info-level keys/counts debug log on every switch is removed.

### 5. script.js split (cross-cutting rule 3)

The CONTEXT MANAGEMENT section is materially touched, so it moves out of the monolith into **`static/matters.js`** (sidebar list, context load/switch/create/rename/delete/archive, workspace switcher), loaded before `script.js` and sharing its globals the same way `job-poller.js` does. Best-effort: if entanglement makes any specific function unsafe to move this cycle, it stays and the tracker records it.

## Out of scope

- Renaming the context/matter API vocabulary (parked; would touch every JS consumer).
- Honest-empty-workspace UI (explicitly rejected in favor of auto-create).
- Sidebar/archived-section styling (visual pass).

## Implementation notes

- `_is_protected_json_path` in `app.py` gains `/contexts/archive` and `/contexts/unarchive` (401-JSON, not redirect, for unauthenticated calls). The startup assertion only checks `PROTECTED_JSON_PATHS`; these live in the inline contexts set beside `/contexts/new` etc.
- `status` is already a `ROOT_FIELDS` member with default `"active"` (`default_context()`); archiving is a `patch_matter(root={"status": ...})`. Older matters lacking the field read as active.
- `list_user_contexts(user_id, workspace_id, include_archived=False)` filters on `status != "archived"`.
- Files: `routes/context.py`, `routes/account.py` (activation's matter pick), `models/context.py`, `app.py` (path set), `static/matters.js` (new), `static/script.js` (section removed), `templates/workspace.html` (script tag + archived section container), `static/demo.js` (stubs), `static/app.css` (minimal archived-section styles), tests `tests/test_matter_lifecycle.py` (new) + updates.
- Tests follow the repo pattern: route-level with `unittest.mock.patch` of the models/tenancy functions imported into `routes.context`; models-level with patched `services.matters` primitives. A guard test asserts the legacy-migration symbols are gone from `models.context`.

## Verification

- `python -m pytest` green.
- Live: archive a matter → it leaves the sidebar and appears under Archived; reopen restores it; archiving the active matter switches cleanly; delete from Archived works; `/demo` unaffected (chips/tour/CTA still fine, archive blocked with toast).
- No `user_contexts` reads remain in `models/context.py` (grep clean).
