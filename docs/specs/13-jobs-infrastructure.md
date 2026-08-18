# Cycle 13 — Jobs Infrastructure (Functional Spec)

Date: 2026-08-18. Status: approved and implemented.

## Cycle-close notes (2026-08-18)

- Implemented as specified; 247 tests green. Demo regression verified live: seeded chat settles normally through the backoff-enabled poller with citations intact.
- Reminder for later: enabling the Firestore TTL policy on `expires_at` (jobs collections) is a console toggle whenever Jason wants automatic cleanup to begin.
- **This closes the 13-cycle functional refresh.** Every part of the application has been walked, specced against Jason's vision, and implemented.

## Behavior contract (after this cycle)

### 1. Slow successes stop masquerading as failures

- `pollJob` backs off: the interval grows 1.25× per poll from `intervalMs` (900 ms) to a 2.5 s cap — long jobs cost ~⅓ the status reads.
- A deadline expiry throws an error carrying `stillRunning: true` (message unchanged for existing handlers).
- Chat's poll deadline rises to **180 s**, and hitting it renders a **"Keep waiting"** button that resumes polling on the same `status_url` (mirroring the Retry-button pattern) instead of the dead-end "refresh the matter" text.

### 2. Terminal jobs are TTL-ready

`_update` (the single write path for matter *and* account jobs) stamps `expires_at = now + 30 days` whenever a job reaches `succeeded`/`failed`/`cancelled` — the same pattern as the Clerk webhook dedupe records. Zero behavior change today; enabling Firestore's TTL policy on `expires_at` later is a console toggle. `expires_at` is not in `_PUBLIC_FIELDS`, so API payloads are unchanged.

## Out of scope

- Everything else in the spine — creation/idempotency, claim, dispatch, retry semantics, cooperative cancellation, transports, health probes — reviewed across all 12 prior cycles' consumers and left as-is. This cycle is deliberately small: the spine earned it.

## Implementation notes

- `services/jobs.py` (`_update` stamp + `JOB_TTL_DAYS = 30` constant), `static/job-poller.js` (backoff + `stillRunning`), `static/script.js` (`pollChatJob` deadline, keep-waiting flow in `settleChatJob`).
- Tests: `tests/test_jobs_cycle13.py` — terminal stamps (matter + account paths), non-terminal doesn't stamp, public payload free of `expires_at`. JS covered by `node --check` + demo regression (fast demo jobs are unaffected by backoff).

## Verification

`python -m pytest` green; `node --check`; demo chat still settles normally.
