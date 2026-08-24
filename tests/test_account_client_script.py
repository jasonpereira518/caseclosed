"""Behavioural tests for static/account.js.

Follows tests/test_auth_client_script.py: the script is executed for real in Node
against a stub DOM, rather than asserted against its source text.

account.js is a classic script wrapped in one IIFE whose free identifiers
(showToast, openModal, escapeHtml, pollJob) resolve to page globals. That is what
makes it runnable under vm.runInContext here — do not convert it to a module.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_JS = REPO_ROOT / "static" / "account.js"

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const scenario = JSON.parse(process.argv[2]);
const calls = [];
const toasts = [];

function element(id) {
  const el = {
    id: id || '',
    tagName: 'DIV',
    textContent: '',
    innerHTML: '',
    value: '',
    checked: false,
    disabled: false,
    hidden: false,
    tabIndex: 0,
    attributes: {},
    dataset: {},
    files: [],
    children: [],
    style: {},
    classList: {
      names: new Set(),
      toggle(n, on) { on ? this.names.add(n) : this.names.delete(n); },
      add(n) { this.names.add(n); },
      remove(n) { this.names.delete(n); },
      contains(n) { return this.names.has(n); },
    },
    handlers: {},
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; },
    removeAttribute(k) { delete this.attributes[k]; },
    addEventListener(type, handler) { (this.handlers[type] ||= []).push(handler); },
    removeEventListener(type, handler) {
      this.handlers[type] = (this.handlers[type] || []).filter(h => h !== handler);
    },
    dispatch(type, event) {
      for (const h of (this.handlers[type] || [])) h(Object.assign({
        preventDefault() {}, stopPropagation() {}, currentTarget: this, target: this,
      }, event || {}));
    },
    querySelector() { return element(); },
    querySelectorAll() { return []; },
    closest() { return null; },
    focus() { context.document.activeElement = this; },
    click() { this.dispatch('click'); },
    appendChild(c) { this.children.push(c); return c; },
    insertBefore(c) { this.children.push(c); return c; },
    remove() {},
    getBoundingClientRect() { return {width: 10, height: 10}; },
  };
  return el;
}

// The ids account.js reaches for by name.
const ids = [
  'profile-form', 'identity-name', 'identity-email',
  'avatar-image', 'avatar-fallback', 'avatar-remove', 'avatar-upload', 'avatar-input',
  'workspace-list', 'create-team-btn', 'team-form',
  'export-account', 'export-progress',
  'delete-account', 'delete-confirmation', 'delete-account-confirm', 'delete-blockers',
  'confirm-modal', 'confirm-modal-title', 'confirm-modal-body', 'confirm-accept',
  'create-team-modal', 'delete-account-modal', 'toast-region',
];
const nodes = {};
for (const id of ids) nodes[id] = element(id);
for (const s of ['profile', 'workspaces', 'data', 'danger']) {
  nodes['tab-' + s] = element('tab-' + s);
  nodes['pane-' + s] = element('pane-' + s);
}

// The profile form's fields, as a live-ish HTMLFormElement stand-in.
const FIELD_NAMES = ['display_name', 'job_title', 'organization', 'phone', 'timezone',
  'bar_number', 'jurisdictions', 'practice_areas', 'office_address', 'bio'];
const fields = {};
for (const name of FIELD_NAMES) { const el = element(); el.name = name; el.type = 'text'; fields[name] = el; }
const notify = element(); notify.name = 'notification_email'; notify.type = 'checkbox';
fields.notification_email = notify;

const formElements = Object.values(fields);
formElements.notification_email = notify;
for (const name of FIELD_NAMES) formElements[name] = fields[name];
nodes['profile-form'].elements = formElements;
nodes['profile-form'].querySelector = () => element();

const navList = element();
navList.classList.add('account-nav__list');

const context = {
  console,
  JSON, Math, Object, Array, String, Number, Boolean, Promise, Error, Set, Map,
  RegExp, Date, isNaN, parseInt, parseFloat, setTimeout, clearTimeout,
  MutationObserver: class { observe() {} disconnect() {} },
  FormData: class {
    constructor(form) {
      this.map = new Map();
      if (form && form.elements) {
        for (const el of Object.values(form.elements)) {
          if (el && el.name && el.type !== 'checkbox') this.map.set(el.name, el.value);
        }
      }
    }
    append(k, v) { this.map.set(k, v); }
    get(k) { return this.map.get(k); }
    entries() { return this.map.entries(); }
    [Symbol.iterator]() { return this.map.entries(); }
  },
  document: {
    activeElement: null,
    getElementById: (id) => nodes[id] || null,
    querySelector: (sel) => (sel.includes('account-nav__list') ? navList : null),
    querySelectorAll: () => [],
    createElement: () => element(),
    addEventListener() {},
    body: element(),
  },
  window: {
    location: { hash: scenario.hash || '', assign(u) { calls.push({assign: u}); } },
    addEventListener() {},
  },
  history: {
    replaceState() { calls.push({replaceState: true}); },
    pushState() { calls.push({pushState: true}); },
  },
  showToast: (msg, type) => { toasts.push({msg, type}); },
  openModal: () => {},
  closeModal: () => {},
  escapeHtml: (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'),
  pollJob: async () => ({status: 'succeeded', download_url: '/download.zip'}),
  fetch: async (url, options) => {
    calls.push({url: String(url), method: (options && options.method) || 'GET',
                body: options && options.body});
    const key = ((options && options.method) || 'GET') + ' ' + String(url);
    if (scenario.responses && scenario.responses[key]) {
      const r = scenario.responses[key];
      return {ok: r.status < 400, status: r.status, json: async () => r.body};
    }
    return {ok: true, status: 200, json: async () => scenario.account};
  },
};
context.window.location = context.location = context.window.location;
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);

(async () => {
  await new Promise(r => setTimeout(r, 30));

  const result = {calls, toasts};

  if (scenario.action === 'nav') {
    result.selected = ['profile', 'workspaces', 'data', 'danger']
      .filter(s => nodes['tab-' + s].getAttribute('aria-selected') === 'true');
    result.visiblePanes = ['profile', 'workspaces', 'data', 'danger']
      .filter(s => nodes['pane-' + s].hidden === false);
    result.tabIndexes = ['profile', 'workspaces', 'data', 'danger']
      .map(s => nodes['tab-' + s].tabIndex);
  }

  if (scenario.action === 'profile-submit') {
    fields.jurisdictions.value = 'New York, , Federal';
    fields.practice_areas.value = 'Civil litigation';
    fields.display_name.value = 'Jordan Parker';
    notify.checked = true;
    nodes['profile-form'].dispatch('submit', {submitter: null});
    await new Promise(r => setTimeout(r, 30));
    const patch = calls.find(c => c.method === 'PATCH');
    result.patchBody = patch ? JSON.parse(patch.body) : null;
  }

  if (scenario.action === 'export-double-click') {
    nodes['export-account'].dispatch('click');
    nodes['export-account'].dispatch('click');
    await new Promise(r => setTimeout(r, 60));
    result.exportPosts = calls.filter(c => c.url && c.url.includes('/api/account/export')).length;
  }

  if (scenario.action === 'delete-409') {
    nodes['delete-account-confirm'].dispatch('click');
    await new Promise(r => setTimeout(r, 40));
    result.assigned = calls.filter(c => c.assign).map(c => c.assign);
    result.blockersHidden = nodes['delete-blockers'].hidden;
    result.blockersHtml = nodes['delete-blockers'].innerHTML;
  }

  process.stdout.write(JSON.stringify(result));
})();
"""


def run(scenario):
    proc = subprocess.run(
        ["node", "-e", HARNESS, str(ACCOUNT_JS), json.dumps(scenario)],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise AssertionError(f"harness failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


ACCOUNT = {
    "profile": {"uid": "u1", "email": "lawyer@example.com", "display_name": "Jordan Parker",
                "notification_preferences": {"email": True}, "avatar_url": ""},
    "workspaces": [{"workspace_id": "w1", "name": "Parker & Associates",
                    "type": "team", "role": "owner"}],
}


@unittest.skipUnless(shutil.which("node"), "node is required for these tests")
class AccountClientScriptTests(unittest.TestCase):

    def test_boot_opens_the_first_section_and_does_not_push_history(self):
        result = run({"action": "nav", "hash": "", "account": ACCOUNT})

        self.assertEqual(result["selected"], ["profile"])
        self.assertEqual(result["visiblePanes"], ["profile"])
        # Roving tabindex: only the selected tab is reachable by Tab.
        self.assertEqual(result["tabIndexes"], [0, -1, -1, -1])
        self.assertTrue(any("replaceState" in c for c in result["calls"]))
        self.assertFalse(any("pushState" in c for c in result["calls"]))

    def test_hash_deep_links_to_a_section(self):
        result = run({"action": "nav", "hash": "#danger", "account": ACCOUNT})

        self.assertEqual(result["selected"], ["danger"])
        self.assertEqual(result["visiblePanes"], ["danger"])

    def test_unknown_hash_falls_back_to_the_first_section(self):
        result = run({"action": "nav", "hash": "#nonsense", "account": ACCOUNT})

        self.assertEqual(result["selected"], ["profile"])

    def test_profile_submit_shapes_the_payload(self):
        """Comma lists become arrays, blanks are dropped, and the flat checkbox
        is folded into notification_preferences."""
        result = run({"action": "profile-submit", "account": ACCOUNT})

        self.assertIsNotNone(result["patchBody"])
        self.assertEqual(result["patchBody"]["jurisdictions"], ["New York", "Federal"])
        self.assertEqual(result["patchBody"]["practice_areas"], ["Civil litigation"])
        self.assertEqual(result["patchBody"]["notification_preferences"], {"email": True})
        self.assertNotIn("notification_email", result["patchBody"])

    def test_double_clicking_export_starts_one_job(self):
        """The old page had no in-flight guard, so a second click queued a
        second archive."""
        result = run({"action": "export-double-click", "account": ACCOUNT})

        self.assertEqual(result["exportPosts"], 1)

    def test_delete_account_409_lists_blockers_without_navigating(self):
        result = run({
            "action": "delete-409",
            "account": ACCOUNT,
            "responses": {"DELETE /api/account": {"status": 409, "body": {
                "error": "Transfer or delete owned teams first.",
                "workspace_ids": ["w1"]}}},
        })

        self.assertEqual(result["assigned"], [])
        self.assertFalse(result["blockersHidden"])
        self.assertIn("Parker &amp; Associates", result["blockersHtml"])
        self.assertIn("#workspaces", result["blockersHtml"])


if __name__ == "__main__":
    unittest.main()
