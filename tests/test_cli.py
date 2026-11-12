import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from send_guard.cli import main


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:  # argparse errors
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.led = str(Path(self._tmp.name) / "led")

    def tearDown(self):
        self._tmp.cleanup()

    def test_claim_then_blocked(self):
        code, out, _ = run("--ledger", self.led, "claim", "launch", "ada@example.com")
        self.assertEqual((code, out.startswith("OK")), (0, True))
        code, out, _ = run("--ledger", self.led, "claim", "launch", "ada@example.com")
        self.assertEqual(code, 3)
        self.assertIn("BLOCKED", out)

    def test_cross_campaign_block_and_status(self):
        run("--ledger", self.led, "claim", "a", "ada@example.com")
        self.assertEqual(run("--ledger", self.led, "claim", "b", "ada@example.com")[0], 3)
        code, out, _ = run("--ledger", self.led, "status", "ada@example.com")
        self.assertEqual((code, out.strip()), (3, "a__ada@example.com"))
        self.assertEqual(run("--ledger", self.led, "status", "bob@example.com")[:2], (0, "clear\n"))

    def test_invalid_input_is_usage_error(self):
        code, _, err = run("--ledger", self.led, "claim", "a/b", "ada@example.com")
        self.assertEqual(code, 2)
        self.assertIn("campaign", err)

    def test_json_output(self):
        _, out, _ = run("--ledger", self.led, "--json", "claim", "launch", "ada@example.com")
        data = json.loads(out)
        self.assertEqual((data["ok"], data["status"]), (True, "CLAIMED"))

    def test_release_allows_reclaim(self):
        run("--ledger", self.led, "claim", "launch", "ada@example.com")
        self.assertEqual(run("--ledger", self.led, "release", "launch", "ada@example.com")[0], 0)
        self.assertEqual(run("--ledger", self.led, "release", "launch", "ada@example.com")[0], 1)
        self.assertEqual(run("--ledger", self.led, "claim", "launch", "ada@example.com")[0], 0)

    def test_check_cmd_found_and_failed(self):
        found = f"{sys.executable} -c 'raise SystemExit(10)'"
        bad = f"{sys.executable} -c 'raise SystemExit(1)'"
        self.assertEqual(run("--ledger", self.led, "claim", "c1", "a@example.com", "--check-cmd", found)[0], 4)
        self.assertEqual(run("--ledger", self.led, "claim", "c2", "b@example.com", "--check-cmd", bad)[0], 5)
        self.assertFalse((Path(self.led) / "c2__b@example.com").exists())

    def test_run_executes_only_after_a_successful_claim(self):
        marker = Path(self._tmp.name) / "ran"
        cmd = [sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x')"]
        self.assertEqual(run("--ledger", self.led, "run", "c", "ada@example.com", "--", *cmd)[0], 0)
        self.assertEqual(run("--ledger", self.led, "run", "c", "ada@example.com", "--", *cmd)[0], 3)
        self.assertEqual(marker.read_text(), "x")

    def test_run_passes_through_command_exit_code_and_keeps_claim(self):
        cmd = [sys.executable, "-c", "raise SystemExit(7)"]
        self.assertEqual(run("--ledger", self.led, "run", "c", "ada@example.com", "--", *cmd)[0], 7)
        self.assertTrue((Path(self.led) / "c__ada@example.com").is_dir())


if __name__ == "__main__":
    unittest.main()
