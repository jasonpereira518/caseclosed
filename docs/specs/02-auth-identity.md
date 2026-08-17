# Cycle 2 — Auth & Identity (Functional Spec)

Date: 2026-08-16. Status: approved and implemented.

## Cycle-close notes (2026-08-16)

- Implemented as specified; 138 tests green. Live-verified: login page renders the single Clerk variant with zero Firebase references, `/auth/session` 404s, logout interstitial renders.
- `firebase-admin` stays in requirements (Firestore/Storage data plane). `scripts/migrate_firebase_user_to_clerk.py` retained as historical record; `scripts/configure_firebase_auth.py` deleted.
- Production note: the deploy profiles no longer set `AUTH_PROVIDER` — deploying an old revision that still reads it falls back to its `clerk` default, so mixed rollbacks are safe.

## Behavior contract (after this cycle)

### 1. Clerk is the only identity provider

The Firebase Authentication rollback path is retired. Rollback story from here: `git revert` + redeploy.

**Deleted:**
- `POST /auth/session` (Firebase ID-token → session-cookie exchange) and its origin/email-verified logic.
- `static/firebase_auth.js`; the Firebase variant and `firebase-config` JSON block in `templates/login.html`.
- The `AUTH_PROVIDER` branch in `app.py`'s `request_loader` (Clerk verification only), in `routes/auth.py` logout (Clerk interstitial only) and `sso_callback` (guard removed), and in `routes/account.py` identity deletion (Clerk only).
- Config: `AUTH_PROVIDER`, `FIREBASE_WEB_CONFIG`, `AUTH_SESSION_COOKIE`, `AUTH_SESSION_DAYS` (nothing reads them afterward). `AUTH_COOKIE_SECURE` stays — it secures the Flask session cookie.
- `services/runtime_config.py`: Clerk vars are unconditionally required in production; Firebase-auth validation removed.
- `scripts/configure_firebase_auth.py` (configures the retired provider). `scripts/migrate_firebase_user_to_clerk.py` **stays** — it documents how existing UIDs got their Clerk `external_id`.
- Firebase-path tests in `tests/test_landing_routes.py`; provider patches elsewhere updated.

**Kept:** `firebase_admin` SDK, `FIREBASE_CREDENTIALS`, `FIREBASE_STORAGE_BUCKET` — the Firestore/Storage data plane is unrelated to identity. The `__session` cookie name disappears from code; stale cookies in browsers simply go unread.

**Docs:** README and CLAUDE.md lose the "temporary rollback" language; deploy profiles and `.env.example` drop the removed vars.

### 2. Accepting a team invitation approves access

`services/tenancy.accept_invitation`, on successful redemption, sets `access_status: "approved"` (with `access_updated_at`) when the account is currently `pending`. Rationale: an explicit member invitation is a stronger admission signal than admin review. Applies to both redemption paths (`/auth/complete` and `POST /api/invitations/accept`). A `revoked` account is **not** resurrected by an invitation — revocation is an admin action only an admin undoes.

### 3. Admins are emailed when someone requests access

When `ensure_user` creates a **new** account (the moment it stamps `pending`), a best-effort notification goes to every address in `ADMIN_EMAILS`: requester's email + a link to `{APP_BASE_URL}/admin/access`. Sent from a daemon thread so SMTP latency can never slow first sign-in; failures are logged and swallowed — sign-up is never blocked by mail.

### 4. Invite failures are actually shown

`/auth/complete` with a bad/expired invite token currently redirects to the login page, which immediately bounces the (authenticated) user onward — the error is never seen. New behavior: render an `invite_error.html` page stating what happened ("This invitation is invalid or has expired — ask the person who invited you to send a new one"), with links to continue to the workspace. The user still signs in; they just don't silently miss that the team join failed.

### 5. Soft-deleted identities cannot load

`models/user.load_user` returns `None` when the user document carries `auth_status: "deleted"` (set by the Clerk `user.deleted` webhook). Local defense-in-depth on top of Clerk refusing to mint tokens for deleted users.

## Out of scope

- Any change to the Clerk sign-in UX, session lifetimes (managed in the Clerk dashboard), or the sso-callback flow — all working as designed.
- Waitlist/admin page styling (visual pass).
- Removing `firebase-admin` from requirements (data plane).

## Implementation notes

- **Access-gate exemption check:** `/auth/*` remains gate-exempt; invite approval happens inside `accept_invitation`, so ordering with the gate is moot.
- **`clerk_enabled` template flag** simplifies to key-presence only (no provider comparison).
- New mailer function `send_access_request_notification(recipient, requester_email)`, reusing `_deliver`.
- Notification hook: small `services/tenancy._notify_admins_of_access_request(email)` spawning a daemon thread; patched directly in tests.
- Files: `app.py`, `config.py`, `routes/auth.py`, `routes/account.py`, `routes/main.py` (context var if referenced), `services/runtime_config.py`, `services/tenancy.py`, `services/mailer.py`, `models/user.py`, `templates/login.html`, `templates/invite_error.html` (new), deletions above; tests `tests/test_auth_cycle2.py` (new) + updates to `test_landing_routes.py`, `test_access_gate.py`, and any provider-patching test.

## Verification

- `python -m pytest` green; no remaining `AUTH_PROVIDER` reference outside migration script/docs history.
- Local run: sign-in flow unchanged in the browser; `/auth/session` 404s; login page renders single Clerk variant.
- Unit-verified: invite redemption approves pending accounts; revoked stays revoked; new-account creation calls the admin notification; deleted identity loads as None; invite failure renders the error page.
