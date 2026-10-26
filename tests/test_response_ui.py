"""Deterministic request replay/cancel/access lifecycle checks against actual HUD JS."""
from pathlib import Path
import shutil
import subprocess
import unittest


class ResponseUI(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is unavailable')
    def test_request_lifecycle(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([shutil.which('node'), str(root / 'tests/test_response_ui.cjs'),
                                 str(root / 'ethan/web/hud.js')], capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('response UI lifecycle tests passed', result.stdout)
