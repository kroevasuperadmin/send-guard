import sys
import tempfile
import unittest
from pathlib import Path

from send_guard.guard import CheckResult, Guard, Status, command_check
from send_guard.ledger import Ledger


class GuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "ledger"
        self.ledger = Ledger(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_recipient_is_claimed(self):
        d = Guard(self.ledger).acquire("launch", "ada@example.com")
        self.assertTrue(d.ok)
        self.assertTrue(d.claim.path.is_dir())

    def test_second_attempt_same_campaign_is_blocked(self):
        g = Guard(self.ledger)
        g.acquire("launch", "ada@example.com")
        d = g.acquire("launch", "ada@example.com")
        self.assertEqual(d.status, Status.LEDGER_HIT)

    def test_other_campaign_within_window_is_blocked(self):
        g = Guard(self.ledger)
        g.acquire("launch", "ada@example.com")
        d = g.acquire("followup", "ada@example.com")
        self.assertEqual(d.status, Status.LEDGER_HIT)
        self.assertEqual(d.blockers, ["launch__ada@example.com"])
        self.assertFalse((self.dir / "followup__ada@example.com").exists())

    def test_hook_clear_keeps_claim(self):
        g = Guard(self.ledger, check=lambda c, r, d: CheckResult(False, "0 matches"))
        d = g.acquire("launch", "ada@example.com")
        self.assertTrue(d.ok)
        self.assertEqual((d.claim.path / "check.txt").read_text().strip(), "0 matches")

    def test_hook_found_keeps_claim_and_writes_marker(self):
        g = Guard(self.ledger, check=lambda c, r, d: CheckResult(True, "sent 2 days ago"))
        d = g.acquire("launch", "ada@example.com")
        self.assertEqual(d.status, Status.FOUND_BY_CHECK)
        self.assertTrue((d.claim.path / "BLOCKED_found_by_check.txt").exists())
        self.assertEqual(Guard(self.ledger).acquire("launch", "ada@example.com").status, Status.LEDGER_HIT)

    def test_hook_error_fails_closed_and_releases_claim(self):
        def broken(c, r, d):
            raise ConnectionError("imap unreachable")

        d = Guard(self.ledger, check=broken).acquire("launch", "ada@example.com")
        self.assertEqual(d.status, Status.CHECK_FAILED)
        self.assertFalse((self.dir / "launch__ada@example.com").exists())
        # nothing was sent, so a later attempt may claim again
        self.assertTrue(Guard(self.ledger).acquire("launch", "ada@example.com").ok)


class CommandCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.script = Path(self._tmp.name) / "check.py"

    def tearDown(self):
        self._tmp.cleanup()

    def _make(self, body):
        self.script.write_text(body)
        return command_check(f"{sys.executable} {self.script}", timeout=20)

    def test_exit_zero_is_clear_and_gets_env(self):
        check = self._make(
            "import os,sys\n"
            "print(os.environ['SEND_GUARD_CAMPAIGN'], os.environ['SEND_GUARD_RECIPIENT'], os.environ['SEND_GUARD_DAYS'])\n"
        )
        r = check("launch", "ada@example.com", 7)
        self.assertFalse(r.found)
        self.assertEqual(r.detail, "launch ada@example.com 7")

    def test_exit_ten_is_found(self):
        r = self._make("print('in Sent'); raise SystemExit(10)")("c", "a@b.co", 7)
        self.assertTrue(r.found)
        self.assertEqual(r.detail, "in Sent")

    def test_other_exit_codes_raise(self):
        with self.assertRaises(RuntimeError):
            self._make("raise SystemExit(1)")("c", "a@b.co", 7)

    def test_timeout_raises(self):
        check = command_check(f"{sys.executable} -c 'import time; time.sleep(5)'", timeout=0.3)
        with self.assertRaises(Exception):
            check("c", "a@b.co", 7)


if __name__ == "__main__":
    unittest.main()
