# Design

Recorded from the built system, not from intention. If this file and the code
disagree, the code is right and this file is stale.

Source of truth: `static/tokens.css`. Both stylesheets import it and neither
may introduce a raw hex value.

## Direction

**The category standard, executed at full commitment.** Offered a choice
between a derived concept world and the conventional one, the product owner
chose the convention deliberately. Case Closed is meant to look like the
software its buyer already trusts.

That is a commitment, not a fallback. There is no governing metaphor, no
decorative conceit, and no smuggled quirk. Conventional arrangement — centred
hero, feature sections, product demonstration, workflow, FAQ, CTA on the
marketing surface; sidebar plus content on the authenticated surface — is the
correct answer here and should stay.

**Craft bar: Harvey, CoCounsel, Spellbook.** Their finish is the standard.
Concretely that means a legal-professional register rather than a startup one,
source and citation display treated as a designed feature, conservative claim
language, and restraint wherever expression and clarity conflict.

Seed key `432d4b9c`.

## Palette

Retained from the existing product. Nine brand colours, unchanged in value,
now addressed through semantic roles.

| Role | Value | Use |
|---|---|---|
| `--surface-page` | `#fdfcfa` | page ground |
| `--surface` | `#ffffff` | cards, panels, inputs |
| `--surface-muted` | `#f5ede3` | sidebar, section bands |
| `--surface-muted-strong` | `#ede7dd` | secondary surfaces, tracks |
| `--surface-inverse` | `#4a3228` | dark bands, toasts, tooltips |
| `--text-strong` | `#3a2a1a` | headings — 13.4:1 |
| `--text` | `#3e2f24` | body — 12.5:1 |
| `--text-secondary` | `#6b5744` | supporting — 6.7:1 |
| `--text-muted` | `#72665b` | metadata — 4.53:1 worst case |
| `--accent` | `#b8805f` | clay. Marks and state only. |
| `--accent-text` | `#8a5a3a` | readable clay for text and links |
| `--action` | `#4a3228` | primary buttons — 11.81:1 |

**Two rules carry most of the system:**

1. **Clay is never a text background.** `#b8805f` is 3.34:1 against white,
   which fails AA for any text at any weight. It clears the 3:1 non-text
   threshold, so it is valid for icons, active rules, selected borders and the
   focus ring — and invalid as a fill behind a label. Primary actions use
   espresso instead. This corrected a live failure on the product's single most
   important control.
2. **Status is never colour alone.** Treatment signals, relevance grades and
   the strength meter all pair their colour with an icon and a text label. A
   lawyer uses these to decide whether an authority is safe to cite.

Status colours are darkened from the originals so they pass as text:
`--positive #3c6b4a` (was `#4a7c59`), `--caution #8a5510` (was `#e69138`, which
was **2.48:1**), `--negative #a8261d` (was `#cc0000`/`#dc4a3b`).

`scripts/check-contrast.mjs` verifies 53 pairings and exits non-zero on
failure. Run it after touching `tokens.css`.

## Type

**Inter**, 400/500/600/700, one ramp across both surfaces.

The mechanical detector flags Inter as overused. That finding is **accepted, not
outstanding**: the direction is canon, and both reference products use a neutral
workhorse sans. A face with a point of view would contradict the commitment.

| Token | Size | Use |
|---|---|---|
| `--text-2xs` | 11px | uppercase micro-labels with `--tracking-caps`. Never prose. |
| `--text-xs` | 12px | timestamps, counts, table metadata |
| `--text-sm` | 13px | dense secondary UI |
| `--text-base` | 15px | application body |
| `--text-md` | 16px | marketing body |
| `--display` | clamp(36→56px) | hero |

Nothing below 11px exists. The previous stylesheet shipped 8px and 9px text.
Numerals in tables, timers, scores and dates use `font-variant-numeric:
tabular-nums` so they stop jittering.

`Georgia` serif is reserved for generated legal documents — it makes a draft
read as a document rather than as app output.

## Surface language

- **Flat.** Elevation is a border. A shadow means "this floats above the page"
  and nothing else — modals, dropdowns, toasts. Not cards, not hover.
- **No gradients anywhere.** The previous app had five.
- **Radii 2–8px.** Five values replacing twenty-seven across the two files,
  which included `999px` and `99px` coexisting for the same pill.
- **Spacing on a 4px ramp.** No more 7/9/11/13/19/21px.
- **Motion is short and purposeful** — 80/140/200/320ms. Animate `transform`
  and `opacity`; never `width`, `height`, `padding` or `max-height`.
  `prefers-reduced-motion` is honoured globally in `tokens.css`.

## Workspace information architecture

The right panel holds four sections, each with a single job:

| Panel | Answers |
|---|---|
| **Record** | what the matter says — facts, parties, jurisdictions, issues, causes, documents |
| **Chronology** | when it happened |
| **Authority** | what law applies — case law and statutes together, with treatment signals |
| **Draft** | what we produced from it |

**Matter strength lives in the header, not in a tab.** It is a verdict on the
whole matter, not the content of one section.

This replaced three tabs holding nine information types, which was the shape
feature accretion left behind rather than a decision. Case law and statutes
share the Authority panel because they answer the same question and were split
only because they were built in different weeks.

## Account centre

`/account` reuses the application shell rather than presenting itself as a
document: `.app` for the grid, `.sidebar-brand` for the 52px rail head,
`.matter-bar` for the caption, `.panel-tab-content` for pane switching. The sand
rail and the 52px band therefore do not move when you cross from `/app`, which
is the point — settings are part of the workspace, not a page that fell out of
it.

The sub-nav is a **vertical tablist** — Profile, Workspaces, Your data, Delete
account — not scroll-spy anchors. Four destinations with no reading order, an
unbounded team manager whose height changes on click, and a destructive action
that should be a destination rather than a scroll depth. Active state is keyed
off `[aria-selected="true"]` rather than a parallel `.active` class so the
accessible and visible states cannot drift. Sections deep-link by hash, written
with `replaceState` so Back leaves the page instead of walking the panes. At
≤1024 the rail becomes a horizontally scrolling strip; there is no off-canvas
drawer, because the four sections are the whole page.

Six local classes carry it — `.account-nav`, `.account-nav__list`,
`.account-nav__item`, `.account-content`, `.account-identity`,
`.account-form-row` — plus `.account-card`, a neutral card on the documented
recipe. `.case-item` is deliberately not reused: it is redefined further down
`app.css` as a grid keyed to `.case-star` and `.treatment-placeholder`, so
borrowing it would mean undoing those rules.

This surface was the last one on the old stylesheet. Its block was the only
place in `app.css` with raw pixel values (`padding: 40px 0 80px`) and a hex
literal (`#6f5d52`), and it opted out of `script.js` entirely — so it had no
toasts and no dialogs, and put the product's most destructive actions behind
`window.confirm` and a `window.prompt` typing gate.

## Components

One modal pattern for all dialogs: `.modal` > `.modal__panel`, toggled by
`[hidden]`, with a focus trap, Esc, scroll lock and focus restore handled
centrally in `static/ui.js`. Dialogs previously toggled inline `style.display`
with no focus management at all.

`ui.js` holds the primitives every surface needs — `showToast`, the modal
controller, `escapeHtml` — and `base.html` loads it on every page ahead of
`page_scripts`. They lived in `script.js` until the account centre needed them,
which was not possible: `script.js`'s `DOMContentLoaded` handler boots the
workspace through `matters.js` functions, so any page loading it alone throws
`ReferenceError` before init finishes. Esc-to-dismiss moved with them; it had
been sitting in the workspace keydown handler beside the sidebar toggle, so it
only ever worked on `/app`.

`[hidden]` is enforced globally with `display: none !important`. The UA rule
alone loses to any component that sets its own `display`, so `el.hidden = true`
silently stopped working for `.btn`, `.modal` and `.drop-zone` — which is how
three separate one-off `[hidden]` overrides accumulated, and why four draft
buttons in `workspace.html` were marked hidden and rendered anyway.

Icons are an inline SVG sprite in `templates/_icons.html` — 24×24, 1.5 stroke,
round cap and join, sized by class so they align to their label. This replaced
a render-blocking Font Awesome CDN request that shipped the entire icon set for
about twenty glyphs, alongside loose unicode glyphs (`☰ ✕ ▾ ★`) used on the same
screens.

## Responsive

Desktop-first, because litigators work at a desk.

- **≥1280 and 1024** — designed
- **768** — correct and usable; panes stack, each scrolling independently
- **<600** — usable, not designed

One breakpoint set across both stylesheets. They previously disagreed
(1040/820/600 versus 1024/768/600), and roughly 42% of the application
stylesheet sat below its own media queries with no responsive rules at all,
while `base.html` shipped no viewport meta.

## The demonstration surface

`/demo` renders the real workspace on a fixture matter, unauthenticated. The
landing hero frames it in an iframe at desktop width, scaled to fit.

This exists so the marketing page shows the product rather than a drawing of
it. The previous hero contained a hand-maintained replica — 137 lines of markup
and about 835 lines of CSS — that already looked better than the real
application and would have drifted on the next feature.

**Isolation is structural.** `routes/demo.py` imports no service module, so it
has no path to Gemini, CourtListener or Firestore; `tests/test_demo_route.py`
parses its AST to enforce that. `static/demo.js` replaces `window.fetch` and
refuses unrecognised paths outright.

**Everything in the fixture is synthetic and labelled.** Case names carry a
`Fict.` marker so none can be mistaken for real authority, and the workspace
shows a persistent demonstration banner.

## Accepted deviations

Findings the detector reports that are deliberate:

- **Inter** (3 occurrences) — see Type above.
- **`border-right: 2px solid var(--clay)`, `landing.css`** — part of a drawn
  connector graphic in the citation demo, not a card accent tab.

## Known gaps

- **Tablet and mobile layouts are written but unverified.** The automated
  browser would not resize below 1440px, so only desktop was visually
  confirmed. Check 768 and 390 by hand before shipping.
  The account centre's ≤1024 strip was checked by retargeting its media query
  at desktop width, which proves the rules but not the trigger point — it still
  wants a real narrow viewport. That test did catch one bug worth knowing
  about: `width: 100%`, correct for the vertical rail, gave the first tab the
  entire strip and scrolled the other three out of view.
- No dark theme. `tokens.css` reserves a `[data-theme]` hook so one is a swap
  rather than a rewrite, but it needs a real design pass — do not synthesise it
  by inverting values.
- `renderStrengthMeter` and its `.strength-section` styles survive from the
  in-panel strength display and are now unused; the header chip replaced them.
