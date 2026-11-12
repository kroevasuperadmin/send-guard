import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path

from send_guard.ledger import Ledger


def _try_claim(args):
    directory, campaign, recipient = args
    return Ledger(directory).claim(campaign, recipient) is not None


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "ledger"

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_claim_wins_second_fails(self):
        ledger = Ledger(self.dir)
        first = ledger.claim("launch", "Ada@Example.com")
        self.assertIsNotNone(first)
        self.assertTrue(first.path.is_dir())
        self.assertIsNone(ledger.claim("launch", "ada@example.com"))

    def test_claim_records_metadata(self):
        claim = Ledger(self.dir).claim("launch", "ada@example.com")
        meta = json.loads((claim.path / "claim.json").read_text())
        self.assertEqual(meta["campaign"], "launch")
        self.assertEqual(meta["recipient"], "ada@example.com")
        self.assertIn("claimed_at", meta)

    def test_different_campaign_is_a_different_claim(self):
        ledger = Ledger(self.dir)
        self.assertIsNotNone(ledger.claim("a", "ada@example.com"))
        self.assertIsNotNone(ledger.claim("b", "ada@example.com"))

    def test_only_one_process_wins_a_race(self):
        args = [(str(self.dir), "race", "ada@example.com")] * 16
        with multiprocessing.Pool(8) as pool:
            results = pool.map(_try_claim, args)
        self.assertEqual(sum(results), 1)


if __name__ == "__main__":
    unittest.main()
