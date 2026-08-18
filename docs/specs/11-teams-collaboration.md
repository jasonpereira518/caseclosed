# Cycle 11 — Teams & Collaboration (Functional Spec)

Date: 2026-08-18. Status: approved and implemented.

## Cycle-close notes (2026-08-18)

- Implemented as specified; 238 tests green, `node --check` clean.
- The account page requires a real Clerk session, so the UI additions (pending-invitation rows, rename control, activity section) are covered by route/service tests rather than a demo walkthrough. **Worth one manual look next time Jason signs into the real app** — especially the invitation list appearing after sending an invite.
- The invite-form flow now re-renders the team card after a successful invite so the new pending invitation appears immediately.

## Behavior contract (after this cycle)

### 1. Pending invitations are visible and revocable

- `GET /api/workspaces/<id>/invitations` (admin+): pending invitations only — email, role, created, expiry, invitation id. Token hashes never leave the server.
- The team card lists them with a Revoke button per row (existing DELETE endpoint). The invite loop finally has a middle.

### 2. Teams are renameable

- `PATCH /api/workspaces/<id>` `{name}` (admin+): same 120-char validation as create; personal workspaces refuse (`ValidationError`); audited as `workspace.renamed`.
- Inline rename control on the team card.

### 3. The audit trail is readable

- `GET /api/workspaces/<id>/activity` (admin+): the latest 50 audit events (event, actor uid + display name where resolvable, matter id, metadata, timestamp), newest first.
- A collapsible Activity section on the team card, fetched on first open. Read-only — the write side has existed all along.

## Out of scope

- Member-profile privacy scoping in `list_members` (flagged for awareness, standard behavior kept).
- Invitation resend (revoke + re-invite covers it).
- Per-event audit detail views, filtering, or export.

## Implementation notes

- `services/tenancy.py`: `list_invitations`, `rename_workspace`, `list_activity` (all behind `require_workspace(admin=True)`).
- `routes/account.py`: three routes (PATCH shares the `/workspaces/<id>` rule with DELETE).
- `static/account.js`: pending-invitation rows + revoke, rename control, activity section. Account page only — no workspace.html/demo impact.
- Firestore note: `list_activity` orders `audit_events` by `created_at` — single-collection order-by needs no composite index.
- Tests: `tests/test_teams_cycle11.py` — service rules (pending-only filter, no token_hash leak, team-only rename, admin gates) with mocked Firestore + route matrix with patched tenancy functions.

## Verification

`python -m pytest` green; `node --check static/account.js`. UI is account-page-only and needs a real signed-in session to exercise — verified by tests + a note for Jason's next real-app session.
