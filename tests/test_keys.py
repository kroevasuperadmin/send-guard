import unittest

from send_guard.keys import InvalidKey, entry_name, normalise_recipient, validate_campaign


class KeyTests(unittest.TestCase):
    def test_recipient_is_lowercased_and_trimmed(self):
        self.assertEqual(normalise_recipient("  Ada@Example.COM "), "ada@example.com")

    def test_recipient_rejects_path_tricks_and_junk(self):
        for bad in ["", "no-at-sign", "a/b@example.com", "a@b", "a@@b.com", "../x@y.com", "a..b@c.com", "a__b@c.com"]:
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidKey):
                    normalise_recipient(bad)

    def test_campaign_rules(self):
        self.assertEqual(validate_campaign("spring-2026.v2"), "spring-2026.v2")
        for bad in ["", "a/b", "a__b", "-lead", "..", "a b", ".hidden"]:
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidKey):
                    validate_campaign(bad)

    def test_entry_name(self):
        self.assertEqual(entry_name("launch", "Ada@Example.com"), "launch__ada@example.com")


if __name__ == "__main__":
    unittest.main()
