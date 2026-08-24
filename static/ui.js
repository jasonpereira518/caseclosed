/* ===========================================================================
   Shared UI primitives.

   Loaded from base.html on EVERY page, before {% block page_scripts %}, so
   any surface can raise a toast or open a dialog without pulling in the
   workspace.

   These lived in script.js until the account centre needed them. Moving them
   was not a preference: script.js's DOMContentLoaded handler calls
   loadContext(), loadSessionHistory() and setupSidebar(), all of which are
   defined in matters.js — so a page that loads script.js alone throws
   ReferenceError and aborts init. The primitives had to come out.

   Do NOT re-declare showToast, FOCUSABLE, _modalStack, openModal, closeModal,
   topModal or escapeHtml in any other classic script. Two top-level `const`
   declarations of the same name on one page is a SyntaxError that kills the
   whole file.

   The 401 fetch interceptor deliberately stayed in script.js: it monkey-patches
   window.fetch globally, and on /auth/login a 401 from Clerk's cross-origin
   API would redirect the login page to itself.
   ========================================================================= */

function showToast(message, type = 'success') {
    const region = document.getElementById('toast-region') || document.body;
    const existing = document.getElementById('app-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'app-toast';
    toast.className = `app-toast app-toast-${type}`;
    toast.textContent = message;
    region.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('visible'));

    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/* ===========================================================================
   Modal controller

   Every dialog previously toggled its own inline style.display and had no
   focus management at all: no trap, no Esc, no scroll lock, no focus
   restore. One controller now owns all six.
   ========================================================================= */

const FOCUSABLE = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled])',
    'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])'
].join(',');

let _modalStack = [];

function _resolveModal(ref) {
    return typeof ref === 'string' ? document.getElementById(ref) : ref;
}

function openModal(ref) {
    const el = _resolveModal(ref);
    if (!el || _modalStack.includes(el)) return;

    el._returnFocus = document.activeElement;
    el.hidden = false;
    _modalStack.push(el);
    document.body.style.overflow = 'hidden';

    const first = el.querySelector('[data-autofocus]') || el.querySelector(FOCUSABLE);
    if (first) requestAnimationFrame(() => first.focus());
}

function closeModal(ref) {
    const el = _resolveModal(ref);
    if (!el || el.hidden) return;

    el.hidden = true;
    _modalStack = _modalStack.filter(m => m !== el);
    if (!_modalStack.length) document.body.style.overflow = '';

    const back = el._returnFocus;
    if (back && document.contains(back)) back.focus();
    el._returnFocus = null;
}

function topModal() {
    return _modalStack[_modalStack.length - 1] || null;
}

// Focus trap + click-outside-to-dismiss, bound once.
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const modal = topModal();
    if (!modal) return;

    const items = [...modal.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];

    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
    }
}, true);

/* Esc dismisses the top dialog. This used to live in script.js's workspace
   keydown handler, next to the sidebar toggle and quick switcher — which meant
   Esc only closed dialogs on /app. It belongs with the controller that owns
   the stack. script.js's Esc branch now defers to topModal() before it
   collapses the sidebar, so the two do not fight. */
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const modal = topModal();
    if (!modal) return;
    e.preventDefault();
    // An Esc that dismissed a dialog is spent. Without this, script.js's
    // keydown handler runs next, finds an empty stack, and collapses the
    // workspace sidebar behind the dialog the user just closed.
    e.stopImmediatePropagation();
    closeModal(modal);
});

document.addEventListener('mousedown', (e) => {
    const modal = topModal();
    // A click on the scrim itself, never on the panel inside it.
    if (modal && e.target === modal) closeModal(modal);
});

/* Any element carrying data-close-modal="<modal-id>" dismisses that dialog.
   Saves wiring a listener per Cancel button and per × in every page script. */
document.addEventListener('click', (e) => {
    const trigger = e.target.closest('[data-close-modal]');
    if (trigger) closeModal(trigger.dataset.closeModal);
});

function escapeHtml(unsafe) {
    return (unsafe || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
