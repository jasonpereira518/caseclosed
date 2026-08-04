# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: solo and small-firm litigators.** They handle active matters without a research or
litigation-support team. Their day moves across pleadings, correspondence, evidence, handwritten
notes, research databases, and a word processor — six surfaces that do not share context. They
spend significant time building chronologies and identifying legal issues by hand. They want faster
research without surrendering source review or professional judgment, and they want a strong first
draft rather than an unreviewed final answer. They are interested in AI and specifically cautious
about accuracy, confidentiality, and control.

**Secondary: investors, advisors, and potential strategic partners.** They need to see a clear
initial customer, a workflow product rather than a thin chat wrapper, and a path from matter
workspace to operating layer.

**Audience priority rule:** when lawyer conversion and investor storytelling compete, optimize for
the lawyer. Investors should understand the opportunity by seeing a credible, focused product with
an identifiable buyer.

## Product Purpose

Case Closed is an AI-assisted litigation workspace. It helps a litigator organize the record,
identify legal issues, research relevant authority, and prepare review-ready legal work without
losing the context of the matter.

Core promise: **From case file to first draft, faster.**

Success is a litigator who moves from raw matter information to a reviewable draft in one place,
with every step inspectable.

## Positioning

**The mechanism a neighboring product cannot truthfully copy: matter context is continuous.** One
matter holds its documents, extracted facts, parties, jurisdictions, legal issues, causes of action,
chronology, statutes, graded authority, notes, and drafts in a single record. Every later task is
answered *from that matter* rather than re-prompted from scratch. A general chat assistant restarts
at every turn; a point research tool never sees the draft; a drafting tool never sees the record.

## Operating Context

- The user is at a desk, usually on a laptop or with a second monitor, often outside business hours,
  under deadlines counted in days. **Desktop-first is a fact about the work, not a convenience.**
- The materials are real litigation artifacts: complaints, incident reports, client statements,
  dispatch logs, opposing counsel correspondence. Formats are PDF, DOCX, DOC, and TXT.
- The profession's own information systems are part of the context: the docket sheet, the pleading
  caption, the Bluebook citation, the citator signal that says how far an authority can be trusted,
  the trial chronology, the exhibit number that ties an assertion to a page.
- Work arrives two ways: unstructured (describe the matter, upload the file) and structured (an
  intake form covering case title, legal category, jurisdiction, court level, the lawyer's role,
  facts, key dates, prior actions, opposing party).
- Output leaves as a `.docx` the lawyer edits in Word.

## Capabilities and Constraints

**Shipping today:**
- Matter intake through chat, a structured intake form, and PDF/DOCX/DOC/TXT upload
- An LLM clarification loop (up to 5 questions, max 2 rounds) before searching
- Extraction of facts, parties, jurisdictions, legal issues, causes of action, penal codes,
  chronology, statutes, and a matter-strength rating
- CourtListener case-law search with LLM-generated queries, relevance grading on five weighted
  dimensions, filtering, and reranking
- Per-case AI descriptions, follow-up Q&A, negative-treatment checks, notes, and bookmarks
- Matter-aware memo and brief drafting, exportable as `.docx`
- Matter history, cross-matter global search, keyboard shortcuts, and per-matter time tracking

**Constraints:**
- Server-rendered Flask + Jinja, vanilla JS, **no build step and no frontend framework**. Any design
  system must be plain CSS and plain JS.
- Authentication is Google OAuth only. Sign-up and sign-in are the same act.
- Persistence is two Firestore collections (`users`, `user_contexts`). No relational database.
- A `/chat` turn makes roughly twenty sequential Gemini calls; gunicorn runs a 300-second timeout.
  Perceived latency is a real design problem, and loading states are load-bearing.
- Deployment is Cloud Run shaped (Docker, `python:3.11-slim`, gunicorn).

**Explicitly undecided / does not exist:** there is no billing, no pricing, no subscription tier, no
trial, no quota, no usage limit, no feature flag system, and no user role model. Every authenticated
user gets every feature. None of this may be implied by any surface.

## Brand Commitments

- **Name:** Case Closed. Fixed. Its typographic treatment is not.
- **Language guardrails — binding.** Use: "AI-assisted", "review-ready", "first draft", "relevant
  authority", "organize", "research", "prepare", "lawyer review", "matter context". Never use:
  "replace lawyers", "win more cases", "guaranteed accurate", "automatic legal advice", "instantly
  solve", "eliminate research", or "court-ready" without a lawyer-review qualifier.
- **No numerical savings or accuracy claims** until supported by validated evidence. None exists yet.
- Voice: restrained, source-conscious, practical. It addresses a professional who will be held
  responsible for the output.
- Accessibility target WCAG 2.2 AA is a stated commitment, not an aspiration.

**Standing visual preference — recorded 2026-08-03, binding until the user changes it.**

Offered a choice between a derived concept world and the category standard, the user chose the
category standard, deliberately. Case Closed is to look like the software its buyer already trusts,
not like a design exercise. This is a commitment, not a fallback:

- **The conventional arrangement is correct.** Centered hero, feature sections, product
  demonstration, workflow, FAQ, CTA on the marketing surface; a conventional sidebar + content app
  shell on the authenticated surface. Do not smuggle in a concept world, a governing metaphor, or a
  decorative conceit. Execute the convention at full fidelity, without irony.
- **The existing palette is retained** — paper `#FDFCFA`, ink `#3A2A1A`, body `#3E2F24`, espresso
  `#4A3228`, clay `#B8805F`, clay-dark `#A06E4F`, sand `#F5EDE3`, sand-deep `#EDE7DD`, rule
  `#E0D5C8`. These get semantic names, real state ramps, and AA contrast verification; they do not
  get replaced.
- **Craft bar: Harvey, CoCounsel, and Spellbook.** Their finish level is the standard this work is
  measured against. Concretely, that means a legal-professional register rather than a startup
  register; source and citation display treated as a designed feature rather than metadata;
  conservative claim language; enterprise-legible typography; and restraint over expression
  everywhere the two conflict.
- Light theme. The product's output is a document the lawyer prints and edits in Word; the interface
  should not fight it.

## Evidence on Hand

**Real:**
- Demo video: https://youtu.be/-iNLur6breI
- Architecture diagram: `assets/case_closed_architecture.png`
- Backing: 1789 Student Venture Fund. Originally built as an AI hackathon project.
- Contributors: Sai Yadavalli (AI engineering), Jason Pereira (frontend, UI/UX)
- The working product itself — the strongest available proof, and the reason the landing page shows
  the real workspace rather than describing it.

**Synthetic, and must always be labeled as a demonstration:**
- The fixture matter **Rivera v. Northline Logistics** (commercial vehicle negligence), specified in
  `LANDING_PAGE_IMPLEMENTATION_PLAN.md` §12: documents Complaint.pdf, Incident_Report.pdf,
  Rivera_Statement.docx, Dispatch_Log.txt, Northline_Correspondence.pdf; issues negligence,
  vicarious liability, notice, comparative fault, evidentiary foundation.
- **Case names in demo content must be fictional** unless a real citation and summary have been
  manually verified. Never fabricate a citation that could be mistaken for actual authority.

**Absent — must not be fabricated:** customers, customer count, testimonials, case studies, logos,
press, benchmarks, accuracy rates, time-savings figures, security certifications, pricing, and
uptime claims.

## Product Principles

1. **Matter-aware.** Analysis, research, and drafting all use the context of the matter. Anything
   that makes the user restate what the matter already knows is a defect.
2. **Source-conscious.** The lawyer can always inspect the authority behind the work. Provenance is
   a first-class element, never a footnote.
3. **Reviewable.** Facts, chronology, analysis, and drafts remain subject to lawyer review. The
   product produces a first draft, never a final answer, and never hides that distinction.
4. **Continuous.** Matter information carries forward instead of being reassembled for every task.
5. **Practical.** The product supports work lawyers already perform, in the vocabulary they already
   use.

## Accessibility & Inclusion

WCAG 2.2 AA. Semantic landmarks, one page-level `h1`, logical heading order, a skip link,
keyboard-operable navigation and interactions, visible focus styles, 44px minimum primary touch
targets, sufficient contrast in normal/hover/focus/disabled states, descriptive alt text on
meaningful imagery and empty alt on decorative imagery, and state changes announced only when
user-triggered.

`prefers-reduced-motion` must be honored on every surface. The landing page currently honors it; the
authenticated application currently does not, and that is a known defect.

## Note on a superseded non-goal

`LANDING_PAGE_IMPLEMENTATION_PLAN.md` §4 lists "a redesign of the authenticated application" as a
non-goal. That was scoped to the landing page's first release. It has been explicitly superseded:
the authenticated workspace is being redesigned alongside the landing page. Every other non-goal in
that section still stands, including the absence of pricing and self-service billing.
