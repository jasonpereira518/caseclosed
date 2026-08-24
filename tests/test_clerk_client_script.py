"""Behavioural tests for static/clerk.js and static/logout.js.

Sign-out has no server-side session invalidation backstop (routes/auth.py's
/logout only clears the Flask session, which is inert for auth -- see
services/clerk_auth.py); it depends entirely on window.Clerk.signOut()
settling. A stalled signOut() call used to leave the click looking completely
dead: no redirect, no feedback, because there was no timeout and no loading
indicator. These tests run the real scripts in Node against a stub DOM/Clerk
client, covering resolve, reject, and hang.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLERK_JS = REPO_ROOT / "static" / "clerk.js"
LOGOUT_JS = REPO_ROOT / "static" / "logout.js"

# The fake setTimeout ignores the real delay so the timeout-race path resolves
# instantly instead of waiting out the script's real SIGN_OUT_TIMEOUT_MS.
CLERK_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const scenario = process.argv[2];

function element(extra) {
  return Object.assign({
    classList: {names: new Set(),
      add(name) { this.names.add(name); },
      toggle(name, on) { on ? this.names.add(name) : this.names.delete(name); }},
    href: '/auth/logout',
    addEventListener(type, handler) { (this.handlers ||= {})[type] = handler; },
  }, extra || {});
}

const link = element();
const assigned = [];
let signOutCalls = 0;

const clerk = {
  load: () => Promise.resolve(),
  signOut: () => {
    signOutCalls += 1;
    if (scenario === 'resolve') return Promise.resolve();
    if (scenario === 'reject') return Promise.reject(new Error('network error'));
    return new Promise(() => {});
  },
};

const sandbox = {
  console,
  document: {querySelectorAll: sel => (sel === '[data-clerk-sign-out]' ? [link] : [])},
  window: {Clerk: clerk, location: {assign: url => assigned.push(url)}},
  setTimeout: fn => setTimeout(fn, 0),
  clearTimeout,
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);

(async () => {
  await sandbox.window.caseClosedClerkReady;
  link.handlers.click({preventDefault() {}});
  await new Promise(resolve => setTimeout(resolve, 10));
  process.stdout.write(JSON.stringify({
    assigned,
    signOutCalls,
    isLoading: link.classList.names.has('is-loading'),
  }));
})();
"""

LOGOUT_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const scenario = process.argv[2];
const assigned = [];
let signOutCalls = 0;

const clerk = {
  signOut: () => {
    signOutCalls += 1;
    if (scenario === 'resolve') return Promise.resolve();
    if (scenario === 'reject') return Promise.reject(new Error('network error'));
    return new Promise(() => {});
  },
};

const sandbox = {
  console,
  window: {caseClosedClerkReady: Promise.resolve(clerk), location: {assign: url => assigned.push(url)}},
  setTimeout: fn => setTimeout(fn, 0),
  clearTimeout,
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);

(async () => {
  await new Promise(resolve => setTimeout(resolve, 10));
  process.stdout.write(JSON.stringify({assigned, signOutCalls}));
})();
"""


def _run(harness, script, scenario):
    return json.loads(subprocess.run(
        ["node", "-e", harness, str(script), scenario],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout)


def _run_clerk(scenario):
    return _run(CLERK_HARNESS, CLERK_JS, scenario)


def _run_logout(scenario):
    return _run(LOGOUT_HARNESS, LOGOUT_JS, scenario)


@unittest.skipUnless(shutil.which("node"), "node is required to execute static/clerk.js")
class ClerkSignOutClickTests(unittest.TestCase):
    def test_successful_sign_out_does_not_fall_back(self):
        result = _run_clerk("resolve")
        self.assertEqual(result["assigned"], [])

    def test_rejected_sign_out_falls_back_to_logout_route(self):
        result = _run_clerk("reject")
        self.assertEqual(result["assigned"], ["/auth/logout"])

    def test_hung_sign_out_falls_back_once_the_timeout_fires(self):
        """The bug: signOut() stalling (never resolving or rejecting) used to leave
        the click with no visible effect at all -- the old code had no timeout, so
        the catch-based fallback never ran."""
        result = _run_clerk("hang")
        self.assertEqual(result["assigned"], ["/auth/logout"])
        self.assertEqual(result["signOutCalls"], 1)

    def test_loading_state_is_applied_synchronously_on_click(self):
        result = _run_clerk("hang")
        self.assertTrue(result["isLoading"])


@unittest.skipUnless(shutil.which("node"), "node is required to execute static/logout.js")
class LogoutInterstitialTests(unittest.TestCase):
    def test_successful_sign_out_does_not_redirect_home(self):
        result = _run_logout("resolve")
        self.assertEqual(result["assigned"], [])

    def test_rejected_sign_out_redirects_home(self):
        result = _run_logout("reject")
        self.assertEqual(result["assigned"], ["/"])

    def test_hung_sign_out_redirects_home_once_the_timeout_fires(self):
        """Without a timeout this page could hang on "Signing out..." forever if
        Clerk stalls, same root cause as the sign-out button itself."""
        result = _run_logout("hang")
        self.assertEqual(result["assigned"], ["/"])
        self.assertEqual(result["signOutCalls"], 1)


if __name__ == "__main__":
    unittest.main()
