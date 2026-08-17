# Cycle 1 — Landing Page & Demo Sandbox (Functional Spec)

Date: 2026-08-16. Status: approved and implemented (see cycle-close notes at bottom).

## Behavior contract (after this cycle)

### 1. Gated sign-up ("sign in is the request")

Access to the product is gated by an allowlist; the landing page keeps its early-access framing, and that framing becomes true.

- **Requesting access:** CTAs continue to lead to Google sign-in. Signing in creates the user account as today, but new accounts start with `access_status: "pending"` on `users/{uid}`.
- **The gate:** an app-level `before_request` check in `app.py`. An authenticated user whose `access_status` is `pending` (or `revoked`):
  - is redirected to `GET /waitlist` for HTML page requests;
  - receives `403 {"error": "access_pending"}` for JSON/API paths (same path-classification helper as the existing 401 logic).
  - Exempt paths: `/`, `/demo`, `/demo/fixture`, `/privacy`, `/terms`, `/waitlist`, `/auth/*`, `/webhooks/*`, `/internal/*`, health probes, and static assets. Admin paths are exempt for admins only.
- **Grandfathering:** a user document with **no** `access_status` field is treated as `approved`. Every pre-existing account (including Jason's) keeps working with zero migration. Only the user-creation path sets `pending` explicitly.
- **`GET /waitlist`** (login required): a simple page — "You're on the list" — showing the signed-in email and a sign-out link. If the visiting user is actually approved, it redirects to `/app`.
- **Admin approval — in-app page:**
  - `config.ADMIN_EMAILS` (comma-separated env var) defines admins. Empty ⇒ no admins ⇒ admin surface 404s for everyone.
  - `GET /admin/access` (admin only, others 404): lists pending users (email, name, requested date) and approved/revoked users, with Approve / Revoke actions.
  - `POST /api/admin/access/<uid>` with `{"action": "approve" | "revoke"}` (admin only): sets `access_status`, stamps `access_updated_at`.
  - Approval is **synchronous** (a single field write + one email — no job needed, consistent with the "trivially fast" exception).
- **Approval email:** on approve, send "You're in" mail via the existing `services/mailer.py` with a sign-in link to `APP_BASE_URL`. Mail failure does **not** roll back the approval (unlike team invites) — access is the source of truth, the email is a courtesy; the admin page shows a warning if the send failed.
- **Cycle-2 note (parked):** users arriving via a team invitation should likely bypass the waitlist; handled when Cycle 2 reworks `/auth/complete`.

### 2. Landing content aligned to the demo fixture (single source of truth: Rivera v. Northline)

- Product-tab previews in `static/landing.js` (`featureContent`) are rewritten to the **Rivera v. Northline** matter — same parties, chronology, issues, and the fixture's **fictional** authorities (Alvarado, Petrakis, Okonkwo, Straub, Denholm). The current employment-retaliation content and **real case names (Kwan, Gorman-Bakos, Summa) are removed**.
- Stats row corrected to fixture truth: **5 documents → 7 key events → 5 legal issues → 5 authorities → 1 memo**.
- Fixture self-consistency fix: the assistant message claiming "nine authorities" becomes "five authorities"; document-count phrasing checked against the five `uploaded_documents`.

### 3. Demo: seeded Q&A

- The fixture gains a `seeded_chat` list: **4 curated questions**, each with a distinct grounded-style answer (with citations where apt), staying inside the Rivera matter (e.g. comparative fault — existing answer; scope of employment / telemetry; what's the weakest point of the case; what should I do next).
- `demo.js` renders **suggested-question chips** above the composer (demo mode only). Clicking a chip submits that question through the normal chat flow.
- Free-typed questions are matched to seeds by simple keyword overlap; anything off-script gets a graceful canned reply explaining that the live product would research it against the matter record, plus a nudge toward the chips.

### 4. Demo: conversion CTA

- The demo header's badge area gains a **"Start your own matter"** button → `/auth/login`, with `target="_top"` so it breaks out of the landing-page iframe correctly.
- The account-name link (which today accidentally bounces to login via `/account`) becomes inert in demo mode.

### 5. Demo: guided tour

- A demo-only, dependency-free tour: sequential tooltips highlighting composer → Record tab → Chronology → Authority (one case card, noting treatment flags) → Draft tab, ending on the conversion CTA.
- Started from a **"Take the tour"** button in the demo notice. Never auto-starts inside the landing iframe (`window.self !== window.top` guard); may auto-offer (not auto-start) when the demo is opened standalone.
- Implemented in a new `static/demo-tour.js`, loaded only in demo mode. Skippable at every step; Escape exits.

### 6. Legal pages

- `GET /privacy` and `GET /terms` (public, in `routes/main.py`): straightforward drafted content — data handling (Firestore/Cloud Storage, Clerk sign-in, no training on user data, deletion rights via account deletion), AI-output disclaimer, no-legal-advice clause. **Jason reviews the wording before the cycle closes.**
- Footer of the landing page links both pages.

## Out of scope (parked for later cycles / visual pass)

- Any styling beyond plain, pattern-matching markup (waitlist, admin, legal pages, tour tooltips, chips).
- Waitlist email-capture form for unauthenticated visitors (not chosen).
- Invite-bypass of the gate (Cycle 2).
- Landing copy/design refresh beyond the data-honesty fixes.

## Implementation notes

- **`PROTECTED_JSON_PATHS`:** new JSON path `/api/admin/access/<uid>` is dynamic; the startup assertion only covers literal paths — `_is_protected_json_path` already 401s everything under `/api/`. No new literal entries required; `/waitlist` and `/admin/access` are HTML.
- **Demo parity rule:** `/chat` stub in `demo.js` changes (seeded answers); no real-route contract changes, so no server-side demo impact. Demo isolation (no service imports) untouched — all new demo behavior is client-side.
- **New files:** `templates/waitlist.html`, `templates/admin_access.html`, `templates/legal_page.html` (shared by privacy/terms), `static/demo-tour.js`, `routes/admin.py` (blueprint), tests `tests/test_access_gate.py`, `tests/test_legal_pages.py`, updates to `tests/test_demo_route.py` expectations if needed.
- **Modified:** `app.py` (gate), `config.py` (`ADMIN_EMAILS`), `services/tenancy.py` or user-creation path (`access_status: pending` on create), `services/mailer.py` (approval mail helper), `routes/main.py` (legal pages), `routes/__init__.py` (admin blueprint), `templates/landing.html` (stats row, footer links), `static/landing.js` (featureContent), `static/demo.js` (seeded chat, chips, CTA), `templates/workspace.html` (demo CTA/badge area, tour script tag), `static/demo-fixture.json` (seeded_chat, message-count fixes).
- **Tests:** gate behavior (pending redirect/403, approved passes, grandfathered passes, exempt paths), admin authorization (non-admin 404, admin list/approve/revoke, approval sets field + sends mail, mail failure keeps approval), legal pages 200 + linked from landing, demo page still renders with the new fixture keys, existing suites stay green.

## Cycle-close notes (2026-08-16)

- Implemented as specified; 128 tests green. Live-verified in the browser: seeded chips answer with citations, off-script questions get the graceful fallback, the 6-step tour activates each tab and ends on the highlighted CTA, landing stats/previews/footer all correct.
- **Jason to review before this content is considered final:** the drafted wording of `templates/privacy.html` and `templates/terms.html` (both currently list jasonpereira518@gmail.com as the contact address), and the approval-email copy in `services/mailer.py`.
- Production note: `ADMIN_EMAILS` was added to both deploy profiles; the gate takes effect for **new** sign-ups on the next deploy. Existing accounts are unaffected.

## Verification

- `python -m pytest` green.
- Local run: sign in with a fresh (non-grandfathered) test path → waitlist page; approve via admin page → access works; approval email attempted (mock/SMTP log).
- `/demo` standalone: chips answer seeded questions, tour completes, CTA targets top frame. Landing iframe unaffected, no console errors.
- `/privacy`, `/terms` reachable from footer.
