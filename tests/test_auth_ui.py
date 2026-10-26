"""Auth response generation tests run without browser, credentials or network."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node unavailable')
class AuthUI(unittest.TestCase):
    def test_stale_header_and_body_responses_are_discarded(self):
        root = Path(__file__).resolve().parents[1]
        p = subprocess.run([shutil.which('node'), str(root/'tests/test_auth_epoch.cjs'),
                            str(root/'ethan/web/hud.js')], capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        self.assertIn('auth epoch tests passed', p.stdout)
