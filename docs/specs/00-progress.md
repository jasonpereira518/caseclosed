# Functional Refresh — Cycle Tracker

Process defined in the approved refresh plan: per cycle — present current behavior → elicit vision → spec → implement → verify. Functionality only; visuals deferred to a later pass.

| # | Cycle | Status | Spec |
|---|-------|--------|------|
| 1 | Landing page & demo sandbox | **Done** (2026-08-16) | [01-landing-demo.md](01-landing-demo.md) |
| 2 | Auth & identity | Not started | — |
| 3 | Workspaces & matters | Not started | — |
| 4 | Client intake | Not started | — |
| 5 | Documents | Not started | — |
| 6 | Chat core | Not started | — |
| 7 | Legal research & authorities | Not started | — |
| 8 | Matter analysis & chronology | Not started | — |
| 9 | Drafting | Not started | — |
| 10 | Workspace utilities | Not started | — |
| 11 | Teams & collaboration | Not started | — |
| 12 | Account center | Not started | — |
| 13 | Jobs infrastructure | Not started | — |

## Deferred / parked items

- **Cycle 2 (Auth):** The access-gate introduced in Cycle 1 touches the auth flow (pending users after sign-in). Cycle 2 should revisit the gate's interaction with invite redemption (`/auth/complete`) — a team-invited user should probably bypass the waitlist since a member explicitly invited them.
- **Visual pass:** demo tour styling, waitlist/admin page styling, legal-page typography all kept deliberately plain.
