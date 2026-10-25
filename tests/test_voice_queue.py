"""Run the meaningful browser voice-ordering regression when Node is installed."""
from pathlib import Path
import shutil
import subprocess
import unittest


class VoiceQueue(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is not installed; voice queue JavaScript regression not run")
    def test_delayed_start_release_cancel_and_failure_recovery(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([shutil.which("node"), str(root / "tests/test_voice_queue.cjs")],
                                cwd=root, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Voice queue:", result.stdout)


if __name__ == "__main__":
    unittest.main()
