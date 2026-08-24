"""Behavioural tests for static/auth.js.

The sign-in button is the only path into the product, so its failure handling is
exercised for real rather than asserted against source text: the script is
executed in Node against a stub DOM and a stub Clerk client.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_JS = REPO_ROOT / "static" / "auth.js"

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const rejection = JSON.parse(process.argv[2]);

function element(extra) {
  return Object.assign({
    textContent: '',
    disabled: false,
    hidden: false,
    classList: {names: new Set(),
      toggle(name, on) { on ? this.names.add(name) : this.names.delete(name); },
      add(name) { this.names.add(name); }},
    setAttribute() {},
    removeAttribute() {},
    addEventListener(type, handler) { (this.handlers ||= {})[type] = handler; },
  }, extra || {});
}

const nodes = {
  'auth-root': element({dataset: {complete: '/auth/complete?next=%2Fapp',
                                  ssoCallback: '/auth/sso-callback?next=%2Fapp'}}),
  'auth-google': element(),
  'auth-google-label': element(),
  'auth-google-spinner': element(),
  'auth-status': element(),
};

const assigned = [];
const error = new Error(rejection.message);
error.errors = rejection.errors;

const sandbox = {
  console,
  document: {getElementById: id => nodes[id] || null},
  window: {
    caseClosedClerkReady: Promise.resolve({
      client: {signIn: {authenticateWithRedirect: () => Promise.reject(error)}},
    }),
    location: {assign: url => assigned.push(url)},
  },
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);

(async () => {
  await sandbox.window.caseClosedClerkReady;
  await new Promise(resolve => setImmediate(resolve));
  await nodes['auth-google'].handlers.click();
  await new Promise(resolve => setImmediate(resolve));
  process.stdout.write(JSON.stringify({
    assigned,
    status: nodes['auth-status'].textContent,
    statusIsError: nodes['auth-status'].classList.names.has('auth-status--error'),
    buttonLabel: nodes['auth-google-label'].textContent,
    buttonDisabled: nodes['auth-google'].disabled,
  }));
})();
"""


def _run(rejection):
    return json.loads(subprocess.run(
        ["node", "-e", HARNESS, str(AUTH_JS), json.dumps(rejection)],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout)


@unittest.skipUnless(shutil.which("node"), "node is required to execute static/auth.js")
class GoogleSignInFailureHandlingTests(unittest.TestCase):
    def test_existing_clerk_session_continues_instead_of_reporting_failure(self):
        """Clerk rejects a fresh OAuth redirect when the browser already holds an
        active session. That is a signed-in user whose server-side view went
        stale, not a Google outage -- send them on to /auth/complete."""
        result = _run({
            "message": "You're already signed in.",
            "errors": [{"code": "session_exists", "message": "Session already exists"}],
        })

        self.assertEqual(result["assigned"], ["/auth/complete?next=%2Fapp"])
        self.assertFalse(result["statusIsError"])

    def test_genuine_redirect_failure_still_reports_an_error(self):
        result = _run({"message": "Network request failed", "errors": None})

        self.assertEqual(result["assigned"], [])
        self.assertIn("could not connect to Google", result["status"])
        self.assertTrue(result["statusIsError"])
        self.assertEqual(result["buttonLabel"], "Continue with Google")
        self.assertFalse(result["buttonDisabled"])


if __name__ == "__main__":
    unittest.main()
