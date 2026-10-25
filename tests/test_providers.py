import unittest
from unittest.mock import patch
from ethan import providers


class ExplicitSessionSelection(unittest.TestCase):
    def resolve(self, ref, rows, available=True):
        with patch.object(providers.bridge_registry, "sessions", return_value={
                "available": available, "sessions": rows}):
            return providers.resolve(ref)

    def test_only_explicit_native_ref_and_minimal_target(self):
        row = {"agent": "claude", "native_id": "session-1", "name": "reviewer",
               "status": "busy", "private_metadata": "not returned"}
        self.assertEqual(self.resolve("claude:session-1", [row]), {
            "agent": "claude", "native_id": "session-1", "name": "reviewer"})

    def test_no_auto_pick_alias_url_or_new_provider(self):
        for ref in (None, "", "auto", "claude:reviewer name", "https://provider", "app:session-1", True):
            with self.subTest(ref=ref), self.assertRaises(providers.SelectionError):
                self.resolve(ref, [])

    def test_unavailable_missing_duplicate_or_bad_metadata_refuses(self):
        row = {"agent": "codex", "native_id": "id-1", "name": "reviewer"}
        cases = [([], True), ([row], False), ([row, row], True),
                 ([dict(row, name="bad\nname")], True)]
        for rows, available in cases:
            with self.subTest(rows=rows, available=available), self.assertRaises(providers.SelectionError):
                self.resolve("codex:id-1", rows, available)

    def test_name_match_never_substitutes_for_native_id(self):
        with self.assertRaises(providers.SelectionError):
            self.resolve("codex:wanted", [{"agent": "codex", "native_id": "other", "name": "wanted"}])
