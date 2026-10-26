"""Pure bearer verifier fixtures; no live configuration or credentials."""
from email.message import Message
import unittest
from unittest.mock import patch
from ethan import local_auth

SYNTHETIC = "SYNTHETIC_TEST_ONLY_" * 3


class ExplicitBearer(unittest.TestCase):
    def test_absent_disabled_present_invalid_fail_closed_without_echo(self):
        self.assertFalse(local_auth.load({}).enabled)
        self.assertTrue(local_auth.load({}).authorized([]))
        for value in ("", "short", "X"*31, "X"*4097, "X"*40+"\r\n", "é"*40, "X"*40+" ", None):
            with self.subTest(length=len(value) if isinstance(value, str) else None):
                with self.assertRaises(local_auth.ConfigurationError) as caught:
                    local_auth.load({local_auth.ENV_NAME: value})
                if value:
                    self.assertNotIn(str(value), str(caught.exception))

    def test_exact_bearer_constant_time_and_no_implicit_alternatives(self):
        auth = local_auth.load({local_auth.ENV_NAME: SYNTHETIC})
        with patch.object(local_auth.hmac, "compare_digest", wraps=local_auth.hmac.compare_digest) as compare:
            self.assertTrue(auth.authorized(["bEaReR " + SYNTHETIC]))
            self.assertFalse(auth.authorized(["Bearer " + "OTHER_SYNTHETIC_VALUE_"*3]))
            self.assertEqual(compare.call_count, 2)
        for values in ([], ["Basic " + SYNTHETIC], ["Bearer  " + SYNTHETIC],
                       ["Bearer " + SYNTHETIC, "Bearer " + SYNTHETIC], ["Bearer\t" + SYNTHETIC],
                       ["Bearer " + SYNTHETIC + "\n"], ["Bearer " + "é"*40]):
            self.assertFalse(auth.authorized(values))
        self.assertFalse(auth.authorized({"Cookie": SYNTHETIC, "token": SYNTHETIC}))
        self.assertNotIn(SYNTHETIC, repr(auth))

    def test_http_message_duplicates_and_case_sensitive_token(self):
        auth = local_auth.Auth.from_environment({local_auth.ENV_NAME: SYNTHETIC})
        headers = Message()
        headers.add_header("authorization", "Bearer " + SYNTHETIC)
        self.assertTrue(auth.authorized(headers))
        headers.add_header("Authorization", "Bearer " + SYNTHETIC)
        self.assertFalse(auth.authorized(headers))
        self.assertFalse(auth.authorized(["Bearer " + SYNTHETIC.lower()]))

    def test_snapshot_does_not_follow_configuration_mutation(self):
        env = {local_auth.ENV_NAME: SYNTHETIC}
        auth = local_auth.Auth.from_environment(env)
        env[local_auth.ENV_NAME] = "DIFFERENT_SYNTHETIC_"*3
        self.assertTrue(auth.authorized(["Bearer " + SYNTHETIC]))
        self.assertEqual(auth.request_headers(), {"Authorization": "Bearer " + SYNTHETIC})
        self.assertEqual(local_auth.load({}).request_headers(), {})
