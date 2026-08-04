#!/usr/bin/env node
/**
 * WCAG 2.2 contrast verification for static/tokens.css.
 *
 *   node scripts/check-contrast.mjs
 *
 * Reads the token values straight out of the stylesheet, so it cannot drift
 * from what actually ships. Exits non-zero if any declared pairing fails.
 *
 * Thresholds: 4.5:1 for normal text, 3:1 for large text (>=24px, or >=18.66px
 * bold) and for the boundary of a control (WCAG 1.4.11 non-text contrast).
 * Purely decorative dividers are exempt and are asserted as such below.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CSS = readFileSync(join(ROOT, 'static/tokens.css'), 'utf8');

/* ------------------------------------------------------------- token parse */

const RAW = {};
for (const [, name, value] of CSS.matchAll(/^\s*(--[\w-]+):\s*([^;]+);/gm)) {
  RAW[name] = value.trim();
}

/** Resolve `var(--x)` chains down to a literal hex value. */
function resolve(name, seen = new Set()) {
  let v = RAW[name];
  if (v === undefined) throw new Error(`token ${name} is not defined in tokens.css`);
  let guard = 0;
  while (v.startsWith('var(')) {
    const ref = v.slice(4, v.indexOf(')')).trim();
    if (seen.has(ref) || guard++ > 20) throw new Error(`circular var chain at ${name}`);
    seen.add(ref);
    v = RAW[ref];
    if (v === undefined) throw new Error(`${name} points at undefined ${ref}`);
    v = v.trim();
  }
  if (!/^#[0-9a-f]{3,8}$/i.test(v)) throw new Error(`${name} is not a hex colour: ${v}`);
  return v;
}

/* ------------------------------------------------------------------- maths */

const bytes = h => {
  h = h.replace('#', '');
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
};
const luminance = h =>
  bytes(h)
    .map(v => (v /= 255) <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4))
    .reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

/* -------------------------------------------------------------- the checks */

const SURFACES = [
  '--surface-page', '--surface', '--surface-sunken',
  '--surface-muted', '--surface-muted-strong', '--surface-hover',
];

/** Text roles that must clear 4.5:1 on EVERY surface above. */
const BODY_TEXT = ['--text-strong', '--text', '--text-secondary', '--text-muted', '--accent-text'];

/** [label, foreground, background, kind] — kind is 'text' | 'ui'. */
const PAIRS = [
  ['primary button label',        '--action-text',      '--action',            'text'],
  ['primary button, hover',       '--action-text',      '--action-hover',      'text'],
  ['primary button, active',      '--action-text',      '--action-active',     'text'],
  ['inverse surface text',        '--text-inverse',     '--surface-inverse',   'text'],
  ['inverse surface text, hover', '--text-inverse',     '--surface-inverse-hover', 'text'],
  ['link on page',                '--text-link',        '--surface-page',      'text'],
  ['positive on its surface',     '--positive',         '--positive-surface',  'text'],
  ['caution on its surface',      '--caution',          '--caution-surface',   'text'],
  ['negative on its surface',     '--negative',         '--negative-surface',  'text'],
  ['positive on white',           '--positive',         '--surface',           'text'],
  ['caution on white',            '--caution',          '--surface',           'text'],
  ['negative on white',           '--negative',         '--surface',           'text'],
  ['secondary button label',      '--action-secondary-text', '--surface',      'text'],

  ['form control edge',           '--border-control',   '--surface',           'ui'],
  ['form control edge on sand',   '--border-control',   '--surface-muted',     'ui'],
  ['secondary button edge',       '--action-secondary-border', '--surface',    'ui'],
  ['focus ring',                  '--focus-ring-color', '--surface',           'ui'],
  ['focus ring on page',          '--focus-ring-color', '--surface-page',      'ui'],
  ['focus ring on sand',          '--focus-ring-color', '--surface-muted',     'ui'],
  ['meaningful accent mark',      '--accent',           '--surface',           'ui'],
  ['positive indicator',          '--positive',         '--surface',           'ui'],
  ['caution indicator',           '--caution',          '--surface',           'ui'],
  ['negative indicator',          '--negative',         '--surface',           'ui'],
];

/**
 * Tokens deliberately BELOW 3:1. Listed so the exemption is a recorded
 * decision rather than an oversight. These may never identify a control.
 */
const EXEMPT_DECORATIVE = [
  ['--border-subtle',   'hairline divider'],
  ['--border',          'container edge'],
  ['--border-strong',   'emphasis divider'],
  ['--accent-border',   'decorative accent edge'],
  ['--accent-muted',    'tinted fill'],
  ['--icon-decorative', 'non-meaningful glyph'],
];

/* ------------------------------------------------------------------ report */

const need = kind => (kind === 'ui' ? 3.0 : 4.5);
let failures = 0;
const bar = '─'.repeat(72);

console.log(`\n${bar}\n Case Closed — token contrast audit (WCAG 2.2)\n${bar}`);

console.log('\n TEXT ROLES × SURFACES              (each cell must be >= 4.50:1)\n');
const head = SURFACES.map(s => s.replace('--surface-', '').replace('--surface', 'white').padStart(7));
console.log('   ' + ' '.repeat(20) + head.join(' '));
for (const t of BODY_TEXT) {
  const fg = resolve(t);
  const cells = SURFACES.map(s => {
    const r = contrast(fg, resolve(s));
    if (r < 4.5) failures++;
    return (r.toFixed(2) + (r < 4.5 ? '!' : ' ')).padStart(7);
  });
  console.log(`   ${t.padEnd(20)}${cells.join(' ')}`);
}

console.log('\n DECLARED PAIRS\n');
for (const [label, fgT, bgT, kind] of PAIRS) {
  const r = contrast(resolve(fgT), resolve(bgT));
  const ok = r >= need(kind);
  if (!ok) failures++;
  console.log(
    `   ${label.padEnd(30)} ${r.toFixed(2).padStart(6)}:1  ` +
    `(needs ${need(kind).toFixed(1)})  ${ok ? 'pass' : 'FAIL  <<<<'}`
  );
}

console.log('\n DELIBERATELY DECORATIVE — exempt from 1.4.11, must not bound a control\n');
for (const [t, why] of EXEMPT_DECORATIVE) {
  const r = contrast(resolve(t), resolve('--surface'));
  console.log(`   ${t.padEnd(20)} ${r.toFixed(2).padStart(6)}:1   ${why}`);
}

console.log(`\n${bar}`);
if (failures) {
  console.log(` ${failures} FAILURE(S). Fix tokens.css before shipping.\n${bar}\n`);
  process.exit(1);
}
console.log(` All ${BODY_TEXT.length * SURFACES.length + PAIRS.length} checks pass.\n${bar}\n`);
