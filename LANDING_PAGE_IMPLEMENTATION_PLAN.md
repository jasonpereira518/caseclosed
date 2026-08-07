# Case Closed Landing Page Implementation Plan

## 1. Document Purpose

This document defines the product strategy, visual direction, content, technical architecture, implementation sequence, and acceptance criteria for the Case Closed public landing page.

The landing page will introduce Case Closed to solo and small-firm litigators, establish enough confidence for them to enter the product or request a demonstration, and communicate the broader platform opportunity to investors without turning the page into a fundraising pitch.

This is an implementation specification, not just a creative brief. It should be usable as the source of truth for design, development, review, testing, and release.

---

## 2. Product Context

Case Closed is an AI-assisted litigation workspace that currently supports:

- Matter intake through chat and structured forms
- PDF, DOCX, DOC, and TXT uploads
- Extraction of facts, parties, issues, timelines, statutes, and matter strength
- CourtListener case-law search
- AI-assisted case relevance scoring and reranking
- Case descriptions, follow-up questions, treatment checks, notes, and bookmarks
- Matter-aware legal memo and brief drafting
- DOCX draft export
- Matter history, global search, and time tracking

The landing page must represent the product that exists today while leaving room for its larger long-term vision. Claims must remain grounded in current capabilities.

---

## 3. Audience

### Primary audience

Solo and small-firm litigators who:

- Handle active matters without a large research or litigation-support team
- Work across pleadings, correspondence, evidence, notes, research databases, and word processors
- Need to understand a matter quickly and preserve context as it develops
- Spend significant time building chronologies and identifying legal issues
- Want faster legal research without surrendering source review or professional judgment
- Need a strong first draft rather than an unreviewed final answer
- Are interested in AI but cautious about accuracy, confidentiality, and control

### Secondary audience

Investors, advisors, and potential strategic partners who need to understand:

- The clear initial customer and workflow
- Why the product is more than a single-purpose AI prompt interface
- How matter context connects intake, analysis, research, and drafting
- Why Case Closed can become an operating layer for litigation work
- How the product may compound in usefulness as more matter information is organized

### Audience priority rule

When lawyer conversion and investor storytelling compete, optimize for the lawyer. Investors should understand the opportunity by seeing a credible, focused product with an identifiable buyer.

---

## 4. Goals and Non-Goals

### Primary goals

1. Explain what Case Closed does within the first viewport.
2. Make the target user feel that the product understands litigation workflow.
3. Demonstrate a continuous path from raw matter information to review-ready work.
4. Establish confidence through product visibility, restrained language, and source-conscious positioning.
5. Drive qualified visitors to start a matter, sign in, or request a demonstration.
6. Give investors a clear view of the platform potential without interrupting the customer story.
7. Create a public, indexable entry point separate from the authenticated product.

### Non-goals for the first release

- A pricing system or self-service billing flow
- A customer portal or investor relations page
- A long-form legal AI education center
- A public user-generated demo with live LLM or CourtListener calls
- Unsupported performance, accuracy, security, or time-savings claims
- A redesign of the authenticated application
- A replacement for the existing Google OAuth implementation
- A full content-management system
- Extensive blog or resource-center functionality

---

## 5. Positioning

### Positioning statement

Case Closed is a matter-aware litigation workspace for solo and small-firm lawyers. It helps litigators organize the record, identify legal issues, research relevant authority, and prepare review-ready legal work without losing the context of the matter.

### Core promise

**From case file to first draft, faster.**

### Supporting statement

Organize the record, uncover relevant authority, and prepare review-ready legal work in one focused workspace.

### Product principles to communicate

- **Matter-aware:** analysis, research, and drafting use the context of the matter.
- **Source-conscious:** lawyers can inspect the cases and authority behind the work.
- **Reviewable:** facts, timelines, analysis, and drafts remain subject to lawyer review.
- **Continuous:** matter information carries forward instead of being reassembled for every task.
- **Practical:** the product supports work lawyers already perform.

### Language guardrails

Use:

- "AI-assisted"
- "Review-ready"
- "First draft"
- "Relevant authority"
- "Organize"
- "Research"
- "Prepare"
- "Lawyer review"
- "Matter context"

Avoid:

- "Replace lawyers"
- "Win more cases"
- "Guaranteed accurate"
- "Automatic legal advice"
- "Instantly solve"
- "Eliminate research"
- "Court-ready" unless a lawyer review qualifier is present
- Numerical savings or accuracy claims until supported by validated evidence

---

## 6. Brand and Visual Direction

### Creative concept

**A modern litigation command center.**

The page should combine the authority of a contemporary legal institution with the precision of a sophisticated work product. The product interface, matter artifacts, and legal workflow provide the visual interest.

Target balance:

- 65% sharp litigation technology company
- 35% prestigious modern legal practice

### Desired emotional response

A lawyer should think:

- "This understands how I work."
- "This looks serious enough for an active matter."
- "I can inspect the work rather than trust a black box."
- "This could give my practice more leverage."

An investor should think:

- "The initial customer and pain are clear."
- "This is a workflow product, not a thin chatbot."
- "The matter workspace can expand into a meaningful platform."

### Color system

The landing page uses the authenticated Case Closed application's established
brown-and-cream palette:

| Token | Value | Use |
|---|---:|---|
| Paper | `#FDFCFA` | Primary page background |
| White | `#FFFFFF` | Product surfaces and high-contrast cards |
| Ink | `#3A2A1A` | Headlines and primary copy |
| Body | `#3E2F24` | Body text |
| Espresso | `#4A3228` | Dark sections and header states |
| Clay | `#B8805F` | Primary actions and active product states |
| Clay dark | `#A06E4F` | Hover and pressed states |
| Sand | `#F5EDE3` | Soft section background |
| Sand deep | `#EDE7DD` | Secondary product surfaces |
| Rule | `#E0D5C8` | Dividers and interface borders |
| Muted | `#9E8E7E` | Secondary copy and metadata |
| Positive | `#4A7C59` | Source and completed states |

The marketing site must feel like the public front door of the current product,
not a separate cobalt or green brand.

### Typography

Use Inter for headings, navigation, body copy, controls, and product UI. Weight,
scale, spacing, and color provide hierarchy without introducing a second brand
typeface.

Requirements:

- No font-size scaling based directly on viewport width
- No negative letter spacing
- Comfortable line lengths of approximately 55-72 characters
- Hero type must remain subordinate to product visibility on smaller screens
- Font loading must not block access to meaningful content

### Imagery

The product is the primary visual asset.

Preferred assets:

- A sanitized, realistic Case Closed workspace
- Product UI scenes built from the actual design language
- Realistic fictional matter documents and metadata
- Subtle paper/document textures only where they improve hierarchy

Do not use:

- Gavels
- Scales of justice
- Courthouse columns
- Handshake photography
- Generic boardroom scenes
- Abstract "AI brain" imagery
- Glowing circuits, robots, or holograms
- Decorative gradient blobs or floating orbs

### Iconography

Use one consistent icon set for actions and workflow labels. Lucide icons are preferred if an icon dependency is introduced. Do not manually draw common interface symbols.

---

## 7. Information Architecture

The landing page is a concise continuous narrative:

1. Announcement and header
2. Hero and primary product view
3. Fragmented workflow problem
4. Interactive product walkthrough
5. Three-stage workflow
6. Lawyer control
7. Fictional matter outcome
8. Design-partner invitation
9. FAQ
10. Final call to action
11. Footer and legal disclaimer

The page should feel like one developing argument rather than a collection of unrelated feature cards.

---

## 8. Detailed Page Specification

### 8.1 Header

#### Purpose

Provide brand recognition, lightweight navigation, and a persistent path into the product.

#### Desktop layout

- Left: Case Closed logo mark and wordmark
- Center/right: Product, Workflow, Trust
- Far right: Sign in and primary `Start a matter` button

#### Mobile layout

- Left: wordmark
- Right: primary CTA and menu icon
- Menu opens a compact accessible navigation panel
- The page must remain usable if JavaScript fails; core links should still be available

#### Behavior

- Transparent or paper-colored at the top
- Gains a restrained border/background after scrolling
- Anchor links move to page sections
- Respect `prefers-reduced-motion` by disabling smooth scrolling where appropriate

#### Link targets

- Product → `#product`
- Workflow → `#workflow`
- Trust → `#trust`
- Sign in → `/auth/login`
- Start a matter → authenticated users go to `/app`; signed-out users begin `/auth/login`

### 8.2 Hero

#### Purpose

Answer three questions immediately:

1. What is this?
2. Who is it for?
3. What can I do next?

#### Proposed copy

Eyebrow:

> Litigation workspace for solo and small-firm lawyers

Headline:

> From case file to first draft, faster.

Supporting copy:

> Organize the record, uncover relevant authority, and prepare review-ready legal work in one focused workspace.

Primary CTA:

> Start a matter

Secondary CTA:

> Watch the product tour

Supporting trust line:

> Matter-aware analysis · Inspectable authority · Lawyer-controlled drafting

#### Visual composition

- The hero is a full-width editorial composition, not a text card beside an image card.
- The product workspace occupies the dominant visual area.
- The headline overlays or sits immediately above the product scene without obscuring inspectable details.
- A visible portion of the next section remains below the fold on common desktop and mobile viewport heights.
- The product scene shows an active fictional matter, not an empty dashboard.

#### Hero product scene

Suggested fictional matter:

> Rivera v. Northline Logistics

Visible matter details:

- Uploaded complaint, incident report, witness statement, and correspondence
- Extracted negligence and vicarious-liability issues
- Chronology entries with dates
- Ranked case result with jurisdiction and relevance explanation
- Draft memorandum state

All names and content must be fictional and clearly sanitized.

### 8.3 Fragmented Workflow Section

#### Purpose

Reflect the lawyer's current pain before presenting the solution.

#### Proposed headline

> Your case should not be scattered across five different tools.

#### Supporting copy

> Pleadings, evidence, notes, research, and drafts all depend on the same matter context. Case Closed keeps that context connected as the work moves forward.

#### Visual

Show a restrained sequence of matter artifacts:

- Pleading PDF
- Email or correspondence
- Research note
- Chronology fragment
- Draft document

As the user scrolls, these artifacts align into one workspace. On reduced-motion devices, show the completed organized state without animation.

### 8.4 Workflow Section

#### Purpose

Explain the product through a familiar four-step litigation workflow.

#### Section headline

> One matter. One continuous workflow.

#### Stages

1. **Build the record**
   Upload pleadings, evidence, correspondence, notes, and supporting documents.

2. **Understand the matter**
   Surface parties, claims, disputed facts, legal issues, dates, statutes, and unanswered questions.

3. **Research authority**
   Search relevant case law and review ranked results with matter-specific explanations.

4. **Prepare the work product**
   Turn the organized record and research into a review-ready memo or brief.

#### Interaction

- Desktop: horizontal segmented progression with one active stage at a time
- Mobile: vertical sequence
- Users can select a stage directly
- Auto-progression is optional and must pause after user interaction
- No carousel controls that hide essential content

### 8.5 Product Walkthrough

#### Purpose

Demonstrate depth and prove that Case Closed is more than a chatbot.

#### Section headline

> The matter stays with the work.

#### Desktop behavior

- A sticky product workspace remains visible.
- Explanatory steps scroll alongside it.
- The highlighted product area changes between stages.
- The sticky region must release before the next section to avoid trapping the page.

#### Mobile behavior

- Use a sequence of cropped, readable product views.
- Avoid sticky behavior if it reduces usable viewport space.
- Each image or UI scene includes its relevant explanation immediately nearby.

#### Walkthrough stages

1. **Documents**
   Show uploaded files and inclusion controls.

2. **Structured analysis**
   Show facts, parties, claims, disputed issues, and legal questions.

3. **Chronology**
   Show dated events with source context.

4. **Case law**
   Show jurisdiction, citation, relevance score, explanation, notes, and treatment status.

5. **Draft**
   Show a legal memorandum with issue, rule, application, and conclusion structure.

#### Implementation preference

Build a lightweight, sanitized product representation in HTML and CSS so:

- Text remains sharp at responsive sizes
- Important regions can animate independently
- Accessibility labels can describe each state
- The scene can match the current product while presenting it more clearly

Use a static screenshot as a fallback if the HTML representation would be too expensive to maintain. Do not place a live authenticated application inside an iframe.

### 8.6 Litigator Advantages

#### Purpose

Translate product features into benefits relevant to small practices.

#### Section headline

> Built for the way litigators think.

#### Three capabilities

**Matter-aware**

> Research and drafting use the facts, documents, and issues already organized in the matter.

**Source-conscious**

> Review the cases and reasoning behind the output before relying on it.

**Reviewable**

> Edit the facts, chronology, analysis, notes, and drafts as your understanding develops.

#### Layout

Use an unframed three-column section on desktop and a vertical sequence on mobile. Avoid decorative nested cards.

### 8.7 Fictional Matter Outcome

#### Purpose

Make the workflow concrete without inventing customer metrics.

#### Section headline

> Turn a working file into a working case picture.

#### Before state

- 14 matter documents
- Scattered factual notes
- Incomplete chronology
- Open legal questions
- Blank memorandum

#### After state

- Structured case assessment
- Reviewable event timeline
- Relevant authorities organized by fit
- Matter-specific research notes
- First-draft legal memorandum

#### Important qualification

The section describes workflow transformation, not a guaranteed result. Do not imply that the system independently verifies every fact or produces final legal work without review.

### 8.8 Trust and Lawyer Control

#### Purpose

Address the central adoption concerns without making unverified security claims.

#### Section headline

> Your judgment stays in the loop.

#### Initial trust points

- Source-linked case research
- Editable analysis and drafts
- Matter-specific workspaces
- Secure Google sign-in
- Clear distinction between assistance and legal advice

#### Security claim process

Before launch, verify every claim against the deployed implementation. Do not claim encryption standards, data isolation guarantees, retention policies, privilege protection, compliance certifications, or training-data exclusions unless they are technically and contractually true.

#### Required disclaimer

> Case Closed provides tools for legal research, organization, and drafting. It does not provide legal advice, and its output should be reviewed by a qualified attorney before use.

### 8.9 Platform Vision

#### Purpose

Show long-term scope in language that still serves the lawyer.

#### Proposed copy

Headline:

> Every matter becomes an intelligent workspace.

Body:

> Case Closed connects the record, legal analysis, research, and drafting so the knowledge developed during a case remains available throughout its life.

#### Visual

A restrained matter map linking:

- Record
- Issues
- Timeline
- Authority
- Work product

This should read as product architecture, not an investor slide.

### 8.10 Final CTA

#### Proposed copy

Headline:

> Start with the matter in front of you.

Body:

> Bring the record, organize the issues, and move your research forward.

Primary CTA:

> Start a matter

Secondary CTA:

> Request a demonstration

#### Demo request behavior

For the first release, the secondary CTA may:

- Open a pre-addressed email using a configured business contact, or
- Link to an existing scheduling page, or
- Link to the existing product demonstration video, or
- Open a small accessible request form if a secure submission endpoint is added

Do not ship a form that silently drops submissions. The final implementation choice requires a real recipient or scheduling destination.

### 8.11 Footer

Include:

- Case Closed wordmark
- Product
- Workflow
- Trust
- Sign in
- Contact
- Privacy policy, when available
- Terms, when available
- Copyright year generated server-side
- Legal-assistance disclaimer

Do not publish placeholder links. Omit unavailable destinations until the corresponding pages exist.

---

## 9. Responsive Design

### Breakpoint strategy

Use content-driven breakpoints rather than targeting specific devices. Suggested ranges:

- Compact: below 640px
- Medium: 640px to 959px
- Large: 960px and above
- Wide: 1280px and above

### Mobile priorities

- Preserve the message and primary CTA in the first viewport
- Keep the active product state readable without horizontal scrolling
- Convert multi-column editorial sections into one clear vertical sequence
- Avoid sticky product behavior where it consumes most of the screen
- Keep buttons at least 44px high
- Prevent headline, navigation, labels, and UI mockup text from clipping
- Maintain a visible path to sign in and start a matter

### Large-screen priorities

- Constrain copy to readable measures
- Allow the product scene to use substantial width
- Avoid excessive empty margins on ultrawide displays
- Use stable grid tracks so product content does not shift between states
- Keep section heights driven by content rather than arbitrary full-screen blocks

---

## 10. Motion and Interaction

### Motion principles

Motion must explain continuity or state change.

Approved uses:

- Documents organizing into a matter workspace
- Workflow stage transitions
- Product panel focus changes during the walkthrough
- Case results appearing and sorting by relevance
- Timeline entries resolving from matter documents
- Subtle header, button, and navigation transitions

Avoid:

- Continuous ambient motion
- Exaggerated parallax
- Cursor-following effects
- Decorative particles
- Auto-playing video with sound
- Long entrance animations that delay reading

### Reduced motion

When `prefers-reduced-motion: reduce` is active:

- Disable smooth scrolling
- Remove scroll-linked transforms
- Show final, stable UI states
- Keep only immediate opacity or state changes where necessary

### JavaScript resilience

The page must remain readable and navigable without JavaScript. JavaScript enhances:

- Sticky walkthrough state
- Mobile navigation disclosure
- Scroll-aware header
- Optional analytics
- Progressive visual transitions

Core copy, links, and CTA destinations must remain server-rendered.

---

## 11. Technical Architecture

### Current behavior

The current root route in `routes/main.py`:

- Renders `chat.html` for authenticated users
- Renders `login.html` for signed-out users

The OAuth callback currently redirects to `main.index`, and logout currently sends users directly back into the OAuth flow.

### Target route behavior

| Route | Authentication | Behavior |
|---|---|---|
| `/` | Public | Render the landing page for all visitors |
| `/app` | Required | Render the existing Case Closed workspace |
| `/auth/login` | Public | Begin Google OAuth |
| `/auth/callback` | Public | Complete OAuth and redirect to `/app` |
| `/auth/logout` | Authenticated session | Log out and redirect to `/` |

### CTA behavior

The server should resolve the primary CTA destination:

- Authenticated visitor → `/app`
- Signed-out visitor → `/auth/login`

This can be passed into the template as a URL rather than requiring client-side authentication detection.

### Proposed files

Create:

- `templates/landing_base.html`
- `templates/landing.html`
- `static/landing.css`
- `static/landing.js`
- `static/landing/` for optimized product and social assets, if needed
- `tests/test_landing_routes.py`

Modify:

- `routes/main.py`
- `routes/auth.py`
- `app.py` only if protected-route behavior or security headers require adjustment
- `README.md` to document `/` and `/app`

Retain:

- `templates/base.html` for the authenticated application and current login-related styling where still needed
- `static/style.css` for the existing application
- `static/script.js` for the existing application

### Template isolation

The landing page should not extend the current `base.html` because that template:

- Always renders the authenticated application's header
- Always loads the large application stylesheet
- Loads Font Awesome
- Loads the application script by default

`landing_base.html` should provide:

- Metadata blocks
- Landing-specific font loading
- Landing stylesheet
- Favicon and social metadata
- A skip link
- Page content block
- Deferred landing script

This isolation reduces CSS collisions and avoids downloading the full product JavaScript on the marketing page.

### Route pseudocode

```python
@main_bp.route("/")
def landing():
    cta_url = (
        url_for("main.app_workspace")
        if current_user.is_authenticated
        else url_for("auth.login")
    )
    return render_template(
        "landing.html",
        primary_cta_url=cta_url,
        current_year=datetime.now(timezone.utc).year,
    )


@main_bp.route("/app")
@login_required
def app_workspace():
    return render_template(
        "chat.html",
        user_name=current_user.name,
        user_email=current_user.email,
        user_profile_pic=current_user.profile_pic,
    )
```

The final implementation should use project naming conventions and avoid naming the view function `app`.

### OAuth return target

The initial release can always return successful authentication to `/app`.

A later enhancement may support a validated `next` parameter. If added:

- Permit only relative paths on the same origin
- Reject protocol-relative and absolute URLs
- Default to `/app`
- Add tests for open-redirect attempts

### Static asset strategy

- Use SVG only for the logo or simple interface-native marks
- Use WebP or AVIF plus fallback for raster assets
- Provide explicit width and height attributes
- Lazy-load below-the-fold images
- Eager-load only the hero's critical visual asset
- Keep the hero product representation lightweight
- Avoid embedding sensitive or real client information in screenshots

---

## 12. Product Demo Content

The landing page requires one internally consistent fictional matter so the product scenes tell a coherent story.

### Fictional matter outline

**Matter:** Rivera v. Northline Logistics

**Type:** Commercial vehicle negligence dispute

**Jurisdiction:** Use a fictionalized or carefully selected jurisdiction appropriate to the sample authorities.

**Documents:**

- Complaint.pdf
- Incident_Report.pdf
- Rivera_Statement.docx
- Dispatch_Log.txt
- Northline_Correspondence.pdf

**Potential issues shown:**

- Negligence
- Vicarious liability
- Notice
- Comparative fault
- Evidentiary foundation

**Timeline examples:**

- Incident date
- Internal report created
- Notice sent
- Complaint filed

**Research display:**

- Use fictional case names unless real citations and summaries are manually verified
- Never fabricate a real-looking citation that could be mistaken for actual authority
- Clearly label sample product content as a demonstration where needed

**Draft display:**

- Short memorandum title
- Question presented
- Brief analysis paragraph
- Visible source references
- "Draft for attorney review" status

---

## 13. Accessibility Requirements

Target WCAG 2.2 AA for the landing page.

Required:

- Semantic landmark structure: header, nav, main, sections, footer
- One clear page-level `h1`
- Logical heading hierarchy
- Skip link to main content
- Keyboard-operable navigation and interactions
- Visible focus styles
- Minimum 44px target size for primary touch controls
- Sufficient color contrast in normal, hover, focus, and disabled states
- Descriptive alternative text for meaningful imagery
- Empty alt text for decorative imagery
- Product walkthrough state changes announced only when user-triggered
- No critical information conveyed by color alone
- Mobile menu focus management and Escape-to-close behavior
- No unexpected focus movement during scroll interactions
- Reduced-motion support
- Zoom support to at least 200% without loss of content

The HTML/CSS product mockup should be hidden from assistive technology if it duplicates adjacent explanatory content. If it contains unique information, provide an equivalent concise description.

---

## 14. SEO and Social Metadata

### Suggested title

> Case Closed | AI-Assisted Litigation Workspace

### Suggested description

> Case Closed helps solo and small-firm litigators organize matter records, research relevant authority, build timelines, and prepare review-ready legal drafts.

### Required metadata

- Canonical URL in production
- Open Graph title, description, image, and URL
- Twitter/X large-image card metadata
- Favicon and Apple touch icon
- Descriptive social share image
- `robots` behavior appropriate to the environment

### Structured data

Consider `SoftwareApplication` structured data only when:

- Product name and description are final
- Public URL is stable
- Pricing or offer data is accurate if included

Do not add review ratings, customer counts, or organization claims that cannot be substantiated.

### Indexing environments

- Production: indexable unless business requirements say otherwise
- Staging and preview: `noindex, nofollow`
- Authenticated `/app`: not intended for indexing

---

## 15. Analytics and Conversion Measurement

Analytics should be privacy-conscious and should never include matter content, user-entered legal information, uploaded filenames, document text, research queries, or draft content.

### Recommended events

| Event | Trigger | Allowed properties |
|---|---|---|
| `landing_view` | Page viewed | Referrer category, campaign parameters |
| `landing_primary_cta` | Start a matter selected | Placement, auth state |
| `landing_sign_in` | Sign in selected | Placement |
| `landing_workflow_view` | Workflow section reached | Section id |
| `landing_product_step` | Walkthrough step selected | Step name |
| `landing_demo_request` | Demo action selected/submitted | Placement |
| `oauth_started` | OAuth begins from landing | Source placement |
| `workspace_entered` | Authenticated user reaches `/app` | Landing/referral source if safely persisted |

### Initial conversion definitions

- Primary conversion: visitor reaches `/app` after selecting a landing CTA
- Secondary conversion: qualified demo request
- Engagement indicator: visitor reaches product walkthrough or interacts with a workflow step

### Consent

If third-party analytics, advertising pixels, or non-essential cookies are added, determine consent and disclosure requirements before deployment. A first-party, cookieless analytics option is preferable for the first release.

---

## 16. Performance Budget

Targets should be measured on a production-like mobile connection:

- Largest Contentful Paint: under 2.5 seconds
- Interaction to Next Paint: under 200 milliseconds
- Cumulative Layout Shift: under 0.1
- Initial landing JavaScript: aim for under 50 KB compressed
- No loading of the existing multi-thousand-line `static/script.js`
- No loading of the authenticated application's complete stylesheet
- Hero media sized to its rendered dimensions
- Below-the-fold media lazy-loaded

The page should not require a frontend framework. The current Flask, Jinja, HTML, CSS, and small vanilla JavaScript architecture is sufficient.

---

## 17. Security and Privacy

### Requirements

- Do not expose Flask configuration or environment values in the page
- Do not include real matter data in source-controlled assets
- Do not pass authentication tokens into JavaScript
- Keep CTA authentication decisions server-side
- Maintain OAuth state validation
- Avoid unvalidated redirect targets
- Add a restrictive Content Security Policy when compatible with current dependencies
- Prefer self-hosted assets where practical
- Ensure external font and analytics choices are covered by privacy disclosures
- Do not place sensitive data in analytics events or URLs

### Existing production concern

`app.py` currently sets `OAUTHLIB_INSECURE_TRANSPORT=1` unconditionally. This is marked for development only and should be removed or restricted to local development before production launch.

### Trust-content dependency

Marketing security language must be reviewed alongside:

- Firestore access patterns and project configuration
- Retention and deletion behavior
- Third-party model data handling
- CourtListener request behavior
- Uploaded-file temporary storage and cleanup
- Logging and error reporting
- Production session-cookie settings

This review can block specific claims, but it should not block building the landing page itself.

---

## 18. Testing Strategy

### Route tests

Add Flask tests covering:

- Signed-out `GET /` returns the landing page
- Signed-in `GET /` still returns the landing page
- Signed-out `GET /app` redirects to `/auth/login`
- Signed-in `GET /app` renders the workspace
- OAuth callback success redirects to `/app`
- Logout clears the session and redirects to `/`
- Primary CTA is `/auth/login` when signed out
- Primary CTA is `/app` when signed in
- Existing JSON unauthorized behavior remains unchanged

### Template tests

Verify:

- One `h1`
- Main navigation destinations exist
- Primary CTA exists above the fold
- Required disclaimer is present
- No real matter or user data appears
- Metadata title and description are populated
- Landing page does not load `static/script.js`

### Browser tests

Test at minimum:

- Desktop: 1440 × 900
- Laptop: 1280 × 800
- Tablet: 768 × 1024
- Mobile: 390 × 844
- Small mobile: 320 × 568

Validate:

- No horizontal overflow
- No overlapping text or controls
- Mobile menu keyboard behavior
- Anchor navigation
- Product walkthrough state changes
- Sticky section entry and exit
- CTA routes
- Reduced-motion presentation
- 200% zoom
- Hero and product visuals render nonblank

### Accessibility checks

- Automated axe scan
- Keyboard-only pass
- Screen-reader landmark and heading check
- Contrast verification
- Focus order review
- Reduced-motion verification

### Regression checks

Confirm the route split does not break:

- Existing chat requests
- Matter switching
- Uploads
- Intake
- Search
- Case notes and bookmarks
- Draft generation and export
- Login-required JSON behavior
- Sign-out behavior

### Visual review

Capture desktop and mobile screenshots and review:

- First viewport clarity
- Product readability
- Section rhythm
- Color balance
- Text wrapping
- Button sizing
- Sticky behavior
- Footer completeness

---

## 19. Implementation Phases

### Phase 0: Decisions and content lock

Deliverables:

- Confirm logo treatment
- Confirm primary CTA wording
- Choose demo-request destination
- Approve fictional matter
- Approve trust claims
- Approve final section copy

Exit criteria:

- No unresolved decision changes route behavior or page architecture

### Phase 1: Route and template foundation

Work:

- Add public `/`
- Move authenticated workspace to `/app`
- Protect `/app` with Flask-Login
- Update OAuth success redirect
- Update logout redirect
- Add `landing_base.html`
- Add the semantic structure of `landing.html`
- Add route tests

Exit criteria:

- Public and authenticated routes behave correctly
- Existing product remains functional at `/app`

### Phase 2: Visual system and responsive layout

Work:

- Implement landing design tokens
- Build header and mobile navigation
- Build hero composition
- Build all section layouts
- Add responsive behavior
- Add focus, hover, and reduced-motion states

Exit criteria:

- Complete static page at all target viewport sizes
- No critical text or layout defects

### Phase 3: Product storytelling

Work:

- Build sanitized product UI representation
- Populate the fictional matter
- Implement workflow selector
- Implement sticky product walkthrough
- Add reduced-motion fallback
- Optimize all visual assets

Exit criteria:

- The product story is understandable without animation
- Interactive states are accessible and stable

### Phase 4: Trust, SEO, and measurement

Work:

- Finalize verified trust language
- Add disclaimer
- Add metadata and social image
- Add analytics events
- Add production/staging indexing behavior
- Update README

Exit criteria:

- No unsupported claims
- Metadata and analytics pass review
- No matter content is captured

### Phase 5: Verification and launch

Work:

- Run backend and route tests
- Run browser and accessibility checks
- Capture visual QA screenshots
- Check production-like performance
- Verify OAuth end-to-end
- Confirm demo-request delivery
- Deploy through the project's existing release path
- Monitor errors and conversions after release

Exit criteria:

- Acceptance criteria are satisfied
- Rollback path is known
- Production CTA and OAuth flow work

---

## 20. Acceptance Criteria

The landing page is ready when:

1. `/` is public and always renders the landing page.
2. `/app` renders the existing workspace for authenticated users.
3. Signed-out users attempting `/app` enter the existing Google OAuth flow.
4. Successful OAuth returns users to `/app`.
5. Logout returns users to `/`.
6. The first viewport clearly communicates audience, value, product, and next action.
7. The product interface is a dominant first-viewport signal.
8. All major current capabilities are represented accurately.
9. No unsupported legal, security, accuracy, or performance claims appear.
10. The page is usable without JavaScript.
11. The page supports keyboard navigation and reduced motion.
12. The page has no horizontal overflow or incoherent overlap at target sizes.
13. The landing page does not load the authenticated product's main JavaScript bundle.
14. Core Web Vitals meet or approach the stated budget in production-like testing.
15. Analytics contain no legal matter content or personal data beyond approved attribution.
16. The demo request reaches a real monitored destination.
17. Desktop and mobile visual QA is approved.
18. Existing application workflows continue to operate at `/app`.

---

## 21. Open Decisions

These decisions should be resolved before or during Phase 0:

1. **Brand mark:** retain the current briefcase, refine it, or create a new wordmark/mark system.
2. **Primary CTA:** `Start a matter` is recommended; confirm whether access is open, invite-only, or demo-led.
3. **Demo destination:** email, scheduling link, or first-party form.
4. **Trust language:** determine exactly what can be said about storage, retention, encryption, model handling, and confidentiality.
5. **Product representation:** HTML/CSS interface scene is recommended; confirm acceptable maintenance cost.
6. **Real authority:** decide whether sample cases will be verified real authorities or explicitly fictional demonstration entries.
7. **Contact identity:** define the business email and legal entity displayed in the footer.
8. **Privacy and terms:** determine whether existing documents are available or must be written before launch.
9. **Analytics provider:** select a privacy-conscious first-party or cookieless solution.
10. **Launch mode:** public self-service, private beta, or request-access.

---

## 22. Recommended First-Release Decisions

To keep the first release focused:

- Use `Start a matter` as the primary CTA.
- Send signed-out users through Google OAuth.
- Use the existing product demonstration video as the secondary CTA until a real monitored email or scheduling destination is confirmed.
- Build one sanitized HTML/CSS product scene from a fictional matter.
- Use restrained scroll-triggered state changes with a complete reduced-motion fallback.
- Keep pricing off the page until packaging is defined.
- Keep customer logos and testimonials off the page until explicit permission and attributable evidence exist.
- Use factual product capabilities instead of quantitative claims.
- Launch the landing page as part of the existing Flask application.

---

## 23. Future Enhancements

Potential follow-on work after the first release:

- Interactive guided product demo
- Practice-area-specific landing variants
- Private-beta waitlist and qualification flow
- Case study pages
- Customer testimonials and validated outcome metrics
- Pricing and plan comparison
- Security and data-handling center
- Resource library for small-firm litigation workflows
- Investor or company page separate from the customer landing page
- Validated post-login return URLs
- A/B testing for headline and CTA language
- Product-led onboarding from landing campaign context

These additions should follow real customer evidence and should not delay the first credible public page.
