import unittest

from feishu_mes_bot.security import verify_event_token


class SecurityTests(unittest.TestCase):
    def test_verify_event_token_accepts_matching_token(self):
        self.assertTrue(verify_event_token({"header": {"token": "abc"}}, "abc"))

    def test_verify_event_token_rejects_mismatch(self):
        self.assertFalse(verify_event_token({"header": {"token": "wrong"}}, "abc"))

    def test_verify_event_token_allows_missing_config(self):
        self.assertTrue(verify_event_token({"header": {"token": "wrong"}}, ""))


if __name__ == "__main__":
    unittest.main()
