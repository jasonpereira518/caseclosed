"""static/job-poller.js: a transient blip must not abort waiting on a job
that is still running server-side; a real 4xx still fails fast."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

POLLER_JS = Path(__file__).resolve().parents[1] / "static" / "job-poller.js"

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const responses = JSON.parse(process.argv[2]);
let calls = 0;
const sandbox = {
  setTimeout: fn => setTimeout(fn, 0),
  fetch: async () => {
    const r = responses[Math.min(calls++, responses.length - 1)];
    if (r === 'network') throw new TypeError('Failed to fetch');
    if (r.html) return {ok: false, status: r.status, json: async () => { throw new SyntaxError("Unexpected token '<'"); }};
    return {ok: r.status < 400, status: r.status, json: async () => r.body};
  },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
vm.runInContext('pollJob("/s")', sandbox)
  .then(job => process.stdout.write(JSON.stringify({status: job.status, calls})))
  .catch(err => process.stdout.write(JSON.stringify({error: err.message, calls})));
"""


def _poll(responses):
    return json.loads(subprocess.run(
        ["node", "-e", HARNESS, str(POLLER_JS), json.dumps(responses)],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout)


@unittest.skipUnless(shutil.which("node"), "node is required to execute static/job-poller.js")
class PollJobTests(unittest.TestCase):
    def test_rides_out_network_drops_and_proxy_error_pages(self):
        result = _poll(["network", {"status": 502, "html": True},
                        {"status": 200, "body": {"status": "running"}},
                        {"status": 200, "body": {"status": "succeeded"}}])
        self.assertEqual(result, {"status": "succeeded", "calls": 4})

    def test_client_errors_still_fail_fast(self):
        result = _poll([{"status": 404, "body": {"error": "job not found"}}])
        self.assertEqual(result, {"error": "job not found", "calls": 1})


if __name__ == "__main__":
    unittest.main()
