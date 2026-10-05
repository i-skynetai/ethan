"""EH-050: `pip install .` gives an `ethan` command, and an installed Ethan finds its
config and state outside the checkout."""
import json, os, subprocess, sys, tempfile, tomllib, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import util  # noqa: E402

PY = sys.executable
#: Nothing listens on port 1, so these tests prove the CLI needs no running service.
NO_SERVICE = {**os.environ, "PYTHONUTF8": "1", "ETHAN_CONSOLE_PORT": "1"}


class Packaging(unittest.TestCase):
    def test_pyproject_names_the_commands(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            meta = tomllib.load(f)
        scripts = meta["project"]["scripts"]
        self.assertEqual(scripts["ethan"], "ethan.cli:main")
        self.assertEqual(scripts["ethan-service"], "ethan.main:main")
        self.assertEqual(meta["project"]["dependencies"], [])          # standard library only

    def test_the_cli_module_prints_usage(self):
        out = subprocess.run([PY, "-m", "ethan.cli", "--help"], cwd=ROOT, capture_output=True, text=True,
                             env=NO_SERVICE, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ethan --status", out.stdout)

    def test_bin_ethan_is_the_same_command(self):
        out = subprocess.run([PY, os.path.join(ROOT, "bin", "ethan"), "--help"], cwd=ROOT, capture_output=True,
                             text=True, env=NO_SERVICE, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ethan --status", out.stdout)

    def test_shipped_defaults_match_the_checkout_config(self):
        for name in ("policy.json", "ethan.json", "kb-map.example.json"):
            with open(os.path.join(ROOT, "config", name), encoding="utf-8") as a, \
                    open(os.path.join(ROOT, "ethan", "defaults", name), encoding="utf-8") as b:
                self.assertEqual(json.load(a), json.load(b), name)


class WhereThingsLive(unittest.TestCase):
    def test_a_checkout_uses_its_own_config_and_state(self):
        with mock.patch.dict(os.environ, {"ETHAN_CONFIG_DIR": "", "ETHAN_STATE_DIR": ""}):
            self.assertEqual(util.config_dir(), os.path.join(ROOT, "config"))
            self.assertEqual(util.state_dir(), os.path.join(ROOT, "state"))

    def test_env_wins(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"ETHAN_CONFIG_DIR": tmp, "ETHAN_STATE_DIR": tmp}):
            self.assertEqual(util.config_dir(), tmp)
            self.assertEqual(util.state_dir(), tmp)
            self.assertEqual(util.cfg("policy.json")["doors"]["console"]["classes"], ["personal", "work", "client"])
            self.assertTrue(os.path.isfile(os.path.join(tmp, "policy.json")))  # seeded from the defaults

    def test_an_installed_copy_uses_the_user_folders_and_seeds_them(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"ETHAN_CONFIG_DIR": "", "ETHAN_STATE_DIR": "",
                                             "APPDATA": tmp, "LOCALAPPDATA": tmp, "XDG_CONFIG_HOME": tmp,
                                             "XDG_DATA_HOME": tmp}), \
                mock.patch.object(util, "ROOT", os.path.join(tmp, "site-packages")):
            cfg_dir, st_dir = util.config_dir(), util.state_dir()
            self.assertTrue(cfg_dir.startswith(tmp), cfg_dir)
            self.assertTrue(st_dir.startswith(tmp), st_dir)
            self.assertNotEqual(cfg_dir, st_dir)
            self.assertEqual(util.cfg("ethan.json")["relay_poll_sec"], 30)
            self.assertEqual(sorted(os.listdir(cfg_dir)), ["ethan.json", "kb-map.example.json", "policy.json"])

    def test_seeding_never_overwrites_a_users_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"ETHAN_CONFIG_DIR": tmp}):
            with open(os.path.join(tmp, "policy.json"), "w", encoding="utf-8") as f:
                json.dump({"doors": {"console": {"classes": ["personal"]}}}, f)
            self.assertEqual(util.cfg("policy.json"), {"doors": {"console": {"classes": ["personal"]}}})


if __name__ == "__main__":
    unittest.main()
