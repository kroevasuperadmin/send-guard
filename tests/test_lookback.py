import os
import tempfile
import time
import unittest
from pathlib import Path

from send_guard.ledger import Ledger


class LookbackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ledger = Ledger(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _age(self, path, days):
        old = time.time() - days * 86400
        os.utime(path, (old, old))

    def test_finds_entry_from_other_campaign(self):
        self.ledger.claim("first", "ada@example.com")
        hits = self.ledger.recent_entries("ada@example.com", 7)
        self.assertEqual([h.name for h in hits], ["first__ada@example.com"])

    def test_ignores_old_entries(self):
        claim = self.ledger.claim("first", "ada@example.com")
        self._age(claim.path, 10)
        self.assertEqual(self.ledger.recent_entries("ada@example.com", 7), [])

    def test_ignores_other_recipients_and_lookalike_suffixes(self):
        self.ledger.claim("c", "bob@example.com")
        self.ledger.claim("c", "xada@example.com")
        self.assertEqual(self.ledger.recent_entries("ada@example.com", 7), [])

    def test_plain_files_from_older_tooling_still_block(self):
        (self.dir / "legacy__ada@example.com").write_text("x")
        self.assertEqual(len(self.ledger.recent_entries("ada@example.com", 7)), 1)

    def test_empty_or_missing_ledger(self):
        self.assertEqual(Ledger(self.dir / "nope").recent_entries("ada@example.com", 7), [])


if __name__ == "__main__":
    unittest.main()
