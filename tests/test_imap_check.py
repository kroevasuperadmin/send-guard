import unittest
from datetime import datetime, timezone

from send_guard.imap_check import count_sent, imap_date


class FakeImap:
    instances = []

    def __init__(self, host, port, hits=b"3 8", select="OK"):
        self.calls = []
        self.hits, self.select_status = hits, select
        FakeImap.instances.append(self)

    def login(self, user, password):
        self.calls.append(("login", user))

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return self.select_status, [b"1"]

    def search(self, charset, *criteria):
        self.calls.append(("search",) + criteria)
        return "OK", [self.hits]

    def logout(self):
        self.calls.append(("logout",))


class ImapCheckTests(unittest.TestCase):
    def test_date_is_locale_independent(self):
        self.assertEqual(imap_date(datetime(2026, 3, 5)), "05-Mar-2026")

    def test_counts_matches_and_searches_the_window(self):
        now = datetime(2026, 11, 12, tzinfo=timezone.utc)
        n = count_sent("ada@example.com", 7, "h", "u", "p", connect=lambda h, p: FakeImap(h, p), now=now)
        self.assertEqual(n, 2)
        calls = FakeImap.instances[-1].calls
        self.assertIn(("select", '"Sent"', True), calls)
        self.assertIn(("search", "SINCE", "05-Nov-2026", "TO", '"ada@example.com"'), calls)
        self.assertEqual(calls[-1], ("logout",))

    def test_no_hits_is_zero(self):
        n = count_sent("a@b.co", 7, "h", "u", "p", connect=lambda h, p: FakeImap(h, p, hits=b""))
        self.assertEqual(n, 0)

    def test_missing_folder_raises(self):
        with self.assertRaises(RuntimeError):
            count_sent("a@b.co", 7, "h", "u", "p", connect=lambda h, p: FakeImap(h, p, select="NO"))


if __name__ == "__main__":
    unittest.main()
