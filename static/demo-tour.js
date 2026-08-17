/* ===========================================================================
   Case Closed — demo guided tour

   Loaded ONLY on /demo, after script.js. A small, dependency-free walkthrough
   that steps a visitor through the workspace: conversation, record,
   chronology, authority, draft, and finally the sign-up CTA.

   Deliberately inert inside the landing-page iframe unless started from the
   "Take the tour" button — it never auto-starts anywhere.
   ========================================================================= */

(function () {
  'use strict';

  const root = document.querySelector('.app');
  if (!root || root.dataset.demo !== '1') return;

  const startButton = document.getElementById('demo-tour-start');
  if (!startButton) return;

  const STEPS = [
    {
      selector: '#chat-form',
      title: 'Ask about the matter',
      text: 'The conversation is grounded in this matter’s record. Try one of the suggested questions above the composer — answers cite the sources they rely on.',
    },
    {
      selector: '#tabbtn-record',
      click: true,
      title: 'The record',
      text: 'Documents, facts, parties, and legal issues live here — one working record instead of six scattered tools.',
    },
    {
      selector: '#tabbtn-chronology',
      click: true,
      title: 'The chronology',
      text: 'Dated facts become a reviewable timeline. You can add events by hand alongside the extracted ones.',
    },
    {
      selector: '#tabbtn-authority',
      click: true,
      title: 'The authority',
      text: 'Case law ranked by fit for this matter, each with a relevance explanation, notes, and an automated flag when a case may have been negatively treated.',
    },
    {
      selector: '#tabbtn-draft',
      click: true,
      title: 'The draft',
      text: 'A first-draft memorandum built from the accumulated record — editable, exportable, and always marked for attorney review.',
    },
    {
      selector: '.demo-start-cta',
      title: 'Your turn',
      text: 'Everything here is synthetic. Bring the matter you are actually working on — sign in with Google to request access.',
    },
  ];

  const STYLE = [
    '.demo-tour-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.35); z-index: 999; }',
    '.demo-tour-highlight { position: relative; z-index: 1001; outline: 3px solid #b45f3c; outline-offset: 3px; }',
    '.demo-tour-tip { position: fixed; z-index: 1002; max-width: 320px; background: #fff; color: #2b1d16;',
    '  border: 1px solid #c9b9ae; border-radius: 6px; padding: 14px 16px; font-size: 14px; line-height: 1.45; }',
    '.demo-tour-tip h2 { margin: 0 0 6px; font-size: 15px; }',
    '.demo-tour-tip p { margin: 0 0 12px; }',
    '.demo-tour-tip .demo-tour-controls { display: flex; gap: 8px; align-items: center; }',
    '.demo-tour-tip button { font: inherit; padding: 4px 12px; border-radius: 4px; border: 1px solid #4a3228; cursor: pointer; background: #fff; }',
    '.demo-tour-tip button.demo-tour-next { background: #4a3228; color: #fff; }',
    '.demo-tour-tip .demo-tour-count { margin-left: auto; font-size: 12px; color: #6f5d52; }',
  ].join('\n');

  let index = -1;
  let backdrop = null;
  let tip = null;
  let highlighted = null;

  function ensureChrome() {
    if (backdrop) return;
    const style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);
    backdrop = document.createElement('div');
    backdrop.className = 'demo-tour-backdrop';
    backdrop.addEventListener('click', endTour);
    tip = document.createElement('div');
    tip.className = 'demo-tour-tip';
    tip.setAttribute('role', 'dialog');
    tip.setAttribute('aria-live', 'polite');
    document.body.append(backdrop, tip);
    document.addEventListener('keydown', onKeydown);
  }

  function onKeydown(event) {
    if (event.key === 'Escape') endTour();
    if (event.key === 'ArrowRight') showStep(index + 1);
    if (event.key === 'ArrowLeft') showStep(index - 1);
  }

  function clearHighlight() {
    if (highlighted) highlighted.classList.remove('demo-tour-highlight');
    highlighted = null;
  }

  function endTour() {
    clearHighlight();
    if (backdrop) backdrop.remove();
    if (tip) tip.remove();
    backdrop = null;
    tip = null;
    index = -1;
    document.removeEventListener('keydown', onKeydown);
    startButton.focus();
  }

  function positionTip(target) {
    const rect = target.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();
    let top = rect.bottom + 12;
    if (top + tipRect.height > window.innerHeight - 12) {
      top = Math.max(12, rect.top - tipRect.height - 12);
    }
    let left = Math.min(rect.left, window.innerWidth - tipRect.width - 12);
    tip.style.top = Math.max(12, top) + 'px';
    tip.style.left = Math.max(12, left) + 'px';
  }

  function showStep(nextIndex) {
    if (nextIndex < 0) return;
    if (nextIndex >= STEPS.length) { endTour(); return; }
    const step = STEPS[nextIndex];
    const target = document.querySelector(step.selector);
    if (!target) { showStep(nextIndex + (nextIndex >= index ? 1 : -1)); return; }

    ensureChrome();
    index = nextIndex;
    if (step.click) target.click();
    clearHighlight();
    highlighted = target;
    target.classList.add('demo-tour-highlight');
    target.scrollIntoView({ block: 'nearest' });

    tip.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = step.title;
    const body = document.createElement('p');
    body.textContent = step.text;
    const controls = document.createElement('div');
    controls.className = 'demo-tour-controls';

    if (index > 0) {
      const back = document.createElement('button');
      back.type = 'button';
      back.textContent = 'Back';
      back.addEventListener('click', () => showStep(index - 1));
      controls.appendChild(back);
    }
    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'demo-tour-next';
    next.textContent = index === STEPS.length - 1 ? 'Finish' : 'Next';
    next.addEventListener('click', () => showStep(index + 1));
    controls.appendChild(next);

    const skip = document.createElement('button');
    skip.type = 'button';
    skip.textContent = 'Skip';
    skip.addEventListener('click', endTour);
    controls.appendChild(skip);

    const count = document.createElement('span');
    count.className = 'demo-tour-count';
    count.textContent = (index + 1) + ' / ' + STEPS.length;
    controls.appendChild(count);

    tip.append(heading, body, controls);
    positionTip(target);
    next.focus();
  }

  startButton.addEventListener('click', () => showStep(0));
})();
