# Branch review

Snapshot of every branch/worktree with unreviewed work, generated from `git log`,
`git diff`, and the status of each worktree under `.claude/worktrees/`. `main` here
means `origin/main` (latest merged state) unless noted.

## 1. `claude-refresh-branch` (current branch)

18 commits ahead of `origin/main`, not yet merged. This is the 13-cycle
spec-driven functional refresh (plan tracked at `docs/specs/00-progress.md`),
plus pre-existing deploy prep commits also sitting on top of `main`.

**Committed, by cycle:**
- **Cycle 1** — gated early access (admin approval workflow), honest landing
  page data, deeper `/demo` sandbox, legal pages (privacy/terms).
- **Cycle 2** — Clerk-only identity (Firebase rollback path retired),
  invite-approves-access, admin signup signal.
- **Cycle 3** — matter archiving, legacy migration retired, lighter matter
  routes.
- **Cycle 4** — editable intake, authoritative jurisdiction, party-role wired
  end-to-end.
- **Cycle 5** — retrieval-only include, auto-include on ready, live status +
  retry.
- **Cycle 6** — model-classified chat intent, no-op acknowledgments, chat
  memory.
- **Cycle 7** — annotation-preserving research, wider net, retryable
  treatment.
- **Cycle 8** — manual timeline events survive rebuilds, event delete, XSS
  fix.
- **Cycle 9** — editable drafts, faithful export, guarded regeneration.
- **Cycle 10** — light search loads, filename search, archived-aware reports.
- **Cycle 11** — visible invitations, team rename, readable audit trail.
- **Cycle 12** — time-inclusive exports, latest-only retention, avatar
  removal.
- **Cycle 13** — poll backoff with resumable waits, TTL-ready terminal jobs.
- Integration pass fixing 15 cross-cycle seams found by a full-app review.
- Demo: honour `DELETE` on job status URLs so Cancel actually cancels.
- Plus the two deploy-prep commits also on `main` locally (custom domain,
  deploy docs) and a dead-code removal commit.

**Uncommitted on top (working tree right now):**
- **Account center rewrite** — `templates/account.html` (+339) and
  `static/account.js` (+951) rebuild the account page into a tabbed
  profile/workspaces/data/danger-zone UI (avatar upload, bar number,
  jurisdictions, practice areas, workspace list, export, danger zone). New
  `static/ui.js`. Backing tests: `tests/test_account_center_page.py`,
  `tests/test_account_client_script.py`.
- **Clerk auth hardening** (`services/clerk_auth.py`) — scopes which
  `__session*` cookie is presented to Clerk by matching the token's `iss`
  claim against `CLERK_FRONTEND_API_URL`, fixing a bug where a foreign Clerk
  cookie (e.g. from the `clerk-nextjs/` scaffold on the same host) could
  shadow the real session and strand signed-in users on the login page.
  Backing tests: `tests/test_clerk_auth.py`, `tests/test_auth_client_script.py`.
- **Config hardening** (`config.py`) — blank `GOOGLE_APPLICATION_CREDENTIALS`
  in `.env` is now treated as unset instead of crashing Firestore/ADC calls.
  Backing test: `tests/test_config_env.py`.
- Supporting edits to `app.py`, `static/app.css`, `static/script.js`,
  `static/auth.js`, `templates/base.html`, `DESIGN.md`, and a small fix to
  `scripts/migrate_firebase_user_to_clerk.py`.

**Needs your review because:** it's the largest unmerged body of work, mixes
13 cycles of feature/bugfix commits with unreviewed uncommitted changes, and
nothing here has been pushed or opened as a PR yet.

## 2. `claude/focused-jones-f26526` (worktree)

No unique commits — its one commit (`5c97086`) is already an ancestor of both
`claude-refresh-branch` and `origin/main`. **All the real work here is
uncommitted** in the worktree at `.claude/worktrees/focused-jones-f26526`.

**Feature: public marketing site, split from the authenticated app**
- New `routes/marketing.py` — unauthenticated blueprint registered at `/`,
  renders `templates/marketing/landing.html` (extends new
  `templates/marketing/base.html`).
- `routes/main.py` — the authenticated chat workspace moves from `/` to
  `/app` (`main.index` renamed to `main.app_home`).
- `routes/auth.py` — OAuth callback redirect updated to point at
  `main.app_home` instead of the old `main.index`.
- `routes/__init__.py` — registers the new `marketing_bp`.
- `templates/login.html` — adds a "Back to home" link to the new marketing
  landing page.
- `static/style.css` — supporting styles for the above.
- New, not yet wired into anything else: `static/marketing.css`.

**Needs your review because:** it's a routing change (root `/` changes
ownership from the app to a new public site) that will conflict with
whatever `claude-refresh-branch` does with the landing page/demo sandbox —
worth deciding which branch's version of `/` wins before either merges.

## 3. `claude/init-8586f8` (worktree)

No unique commits of its own (`d0d896c`, same tip as local `main`; not yet
pushed to `origin/main`). **The only content is an uncommitted rewrite of
`CLAUDE.md`** in the worktree at `.claude/worktrees/init-8586f8` — this is
documentation, not a code feature:
- Documents `node scripts/check-contrast.mjs` as the repo's only lint (WCAG
  2.2 contrast check over `static/tokens.css`).
- Documents `scripts/provision_gcp.sh` / `scripts/verify_gcp.sh`.
- Adds a "Testing conventions" section (no `conftest.py`, no fixture DB,
  `unittest.TestCase` + `app.test_client()`, auth faked via session, structural
  tests as invariant guardrails).
- Adds a "Frontend" section documenting `static/tokens.css` as the single
  source of truth for design tokens, light-theme-only by design, and
  `static/job-poller.js` as the shared `202`/`status_url` polling client.
- Documents the `/demo` sandbox's structural isolation (`tests/test_demo_route.py`
  AST-checks its imports).
- Clarifies `VECTOR_SEARCH_ENABLED` (runtime) vs. `ENABLE_VECTOR_SEARCH` /
  `ENABLE_LEGAL_CORPUS_SYNC` (provisioning-only) as separate, non-interchangeable
  flag families.

**Needs your review because:** it's a documentation-accuracy pass describing
patterns that already exist elsewhere in the codebase — low risk, but worth a
skim before it's committed since it'll become the project's onboarding doc.

## Not included

- `main` (local) is 2 commits ahead of `origin/main` (`838cb5d`, `d0d896c` —
  custom-domain deploy prep) but not a separate line of work; those same 2
  commits are already folded into both `claude-refresh-branch` and
  `claude/init-8586f8`'s history.
