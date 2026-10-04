#!/usr/bin/env python3
"""Regression tests for three defects found by review on 2026-09-13.

Run: python3 tests/test_regressions.py   (stdlib only, like the rest of Ethan)

The first test is the important one. It does not check a single fixed line; it
checks the whole *class* of mistake, because that bug was introduced by a
find-and-replace that collapsed a module name and a variable name into one
word. A rename can do that again, and Python will not complain until the line
actually runs — which for `ingest_document` meant the CLI's ingest path was
dead while everything still imported and compiled cleanly.
"""
from __future__ import annotations

import ast
import glob
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


# ── 1. No module name may also be a local or parameter ──────────────────────
# `from . import kb` then `kb = something` inside a function makes `kb` local
# for the WHOLE function, so an earlier `kb.kb_map()` raises UnboundLocalError.

def test_no_shadowed_modules() -> None:
    print("\n1. module names are not shadowed by locals or parameters")
    sites = []
    for path in sorted(glob.glob(os.path.join(ROOT, "ethan", "*.py"))
                       + glob.glob(os.path.join(ROOT, "tools", "*.py"))):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules |= {a.asname or a.name for a in node.names}
            elif isinstance(node, ast.Import):
                modules |= {(a.asname or a.name).split(".")[0] for a in node.names}
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            bound = {n.id for n in ast.walk(fn)
                     if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            bound |= {a.arg for a in fn.args.args}
            for node in ast.walk(fn):
                if (isinstance(node, ast.Attribute)
                        and isinstance(node.value, ast.Name)
                        and node.value.id in modules
                        and node.value.id in bound):
                    rel = os.path.relpath(path, ROOT)
                    sites.append(f"{rel}:{node.lineno} {fn.name}() uses "
                                 f"{node.value.id}.* while '{node.value.id}' is also local")
    for s in sites:
        print(f"        {s}")
    check("no module is shadowed by a local", not sites, f"{len(sites)} site(s)")


# ── 2. Direct ingest reaches its policy checks ──────────────────────────────

def test_ingest_document_runs() -> None:
    print("\n2. ingest_document() reaches its policy checks")
    from ethan import harvest
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        fh.write("A document long enough to pass the minimum-length gate, "
                 "written only so the ingest path can be exercised.\n")
        tmp = fh.name
    try:
        status, info = harvest.ingest_document(tmp, "learning", "console", "test")
    except Exception as exc:                                   # noqa: BLE001
        check("ingest_document does not raise", False, f"{type(exc).__name__}: {exc}")
        return
    finally:
        os.unlink(tmp)
    # A temp file belongs to no KB, so "refused" is the correct outcome. What
    # matters is that it got far enough to decide that.
    check("ingest_document does not raise", True)
    check("it reached KB resolution", status == "refused" and "no kb owns" in str(info),
          f"got {status}: {info}")


# ── 3. Concurrent hands get distinct log files ─────────────────────────────

def test_log_paths_unique() -> None:
    print("\n3. two hands starting in the same second get different log files")
    from ethan import hands
    paths = {hands._log_path("claude") for _ in range(50)}
    check("50 consecutive paths are all distinct", len(paths) == 50,
          f"{len(paths)} unique of 50")


# ── 4. A disabled Telegram door does not end the process ───────────────────

def test_telegram_optional() -> None:
    print("\n4. main() does not exit when the Telegram door is disabled")
    with open(os.path.join(ROOT, "ethan", "main.py"), encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    fn = next(f for f in ast.walk(tree)
              if isinstance(f, ast.FunctionDef) and f.name == "main")
    body = ast.unparse(fn)
    idx = body.find("door_telegram.run()")
    check("door_telegram.run() is called", idx != -1)
    if idx == -1:
        return
    after = body[idx + len("door_telegram.run()"):]
    # Something must hold the process open after the door returns, or the
    # daemon console thread dies with main().
    check("something holds the process open afterwards",
          "while True" in after, "nothing follows the call")

    # Returning is only half of it: an optional door must not be able to raise
    # out of its own start-up either. Checking that a `try` exists somewhere is
    # not the same as checking the dangerous call is inside it, so this drives
    # the real function with a failing API and asserts on the behaviour.
    from ethan import door_telegram
    real_api, real_log = door_telegram._api, door_telegram.log
    logged: list[str] = []
    door_telegram._api = lambda *a, **k: (_ for _ in ()).throw(
        OSError("simulated: token set but the call fails"))
    door_telegram.log = logged.append
    saved = os.environ.get("TELEGRAM_BOT_TOKEN")
    os.environ["TELEGRAM_BOT_TOKEN"] = "test-token-that-does-not-work"
    try:
        door_telegram.run()
        returned = True
    except Exception:                                          # noqa: BLE001
        returned = False
    finally:
        door_telegram._api, door_telegram.log = real_api, real_log
        # Put back exactly what was there — this process may be a real one.
        if saved is None:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        else:
            os.environ["TELEGRAM_BOT_TOKEN"] = saved
    check("a failing start-up returns instead of raising", returned,
          "run() propagated the exception, which would end main()")
    check("and it says why", any("cannot start" in m for m in logged),
          f"logged: {logged}")


def run_all() -> int:
    """Entry point shared by __main__ and unittest discovery."""
    test_no_shadowed_modules()
    test_ingest_document_runs()
    test_log_paths_unique()
    test_telegram_optional()
    return len(failures)


class Regressions(unittest.TestCase):
    """So `python3 -m unittest discover tests` runs these too.

    The checks print their own detail, which is more useful than an assertion
    message when several fail at once, so this wraps rather than replaces them.
    """

    def test_all_regressions(self) -> None:
        failures.clear()
        self.assertEqual(run_all(), 0, f"failing checks: {failures}")


class SkillsGoUnderTheSkillOntology(unittest.TestCase):
    """A skill is a procedure and is extracted under `sky_skill`.

    "skill" sat in AGENT_CONTEXT_TYPES, so skill documents went under the
    ontology that records *use* of a skill rather than the skill itself. The
    harness's ingest skill made the same mistake; both were fixed together
    (2026-09-14). The routing is a pure function now so this can be pinned.
    """

    def test_a_skill_is_routed_to_sky_skill(self):
        from ethan import harvest
        self.assertEqual(harvest.ontology_for("skill", None, "sky_sdlc"), "sky_skill")

    def test_session_context_still_goes_to_agent_context(self):
        from ethan import harvest
        self.assertEqual(harvest.ontology_for("session-context", None, "sky_sdlc"),
                         "agent_context")

    def test_a_personal_kb_keeps_its_own_ontology_for_everything(self):
        from ethan import harvest
        for doc_type in ("skill", "session-context", "adr"):
            with self.subTest(doc_type=doc_type):
                self.assertEqual(harvest.ontology_for(doc_type, "personal", "mine"), "mine")

    def test_skill_is_no_longer_an_agent_context_type(self):
        from ethan import harvest
        self.assertNotIn("skill", harvest.AGENT_CONTEXT_TYPES)


class HandsGoThroughCore(unittest.TestCase):
    """Ethan calls `sky build`; it no longer starts a hand itself.

    Two findings from the 2026-09-14 review, pinned: the command is core's, not
    a bare `claude`; and the environment is an explicit list carrying exactly
    one secret, never everything Ethan holds.
    """

    def test_the_command_is_sky_build_not_a_bare_hand(self):
        from ethan import hands
        conf = {"sky": {"bin": None}}
        cmd = hands.build_command(conf, role="reviewer", hand="codex",
                                  brief="review the diff", kb="team_kb")
        self.assertNotEqual(os.path.basename(cmd[0]), "codex")
        self.assertIn("build", cmd)
        i = cmd.index("build")
        # core's global options come before the subcommand
        self.assertIn("--kb-map", cmd[:i])
        self.assertEqual(cmd[cmd.index("--kb") + 1], "team_kb")
        self.assertLess(cmd.index("--kb"), i)
        self.assertEqual(cmd[cmd.index("--role") + 1], "reviewer")
        self.assertEqual(cmd[cmd.index("--hand") + 1], "codex")
        self.assertIn("--json", cmd)
        self.assertEqual(cmd[-1], "review the diff")

    def test_the_environment_carries_exactly_one_secret(self):
        """Everything else Ethan holds stays behind."""
        from ethan import hands
        saved = dict(os.environ)
        try:
            os.environ.update({
                "TELEGRAM_BOT_TOKEN": "tg-secret", "OPENAI_API_KEY": "oa-secret",
                "KB_TEST_PAT": "the-one-we-want", "KB_OTHER_PAT": "not-this-kb",
                "PATH": os.environ.get("PATH", "/usr/bin"), "HOME": "/tmp/h"})
            env = hands.build_env({"sky": {}}, {"pat_env": "KB_TEST_PAT"})
        finally:
            os.environ.clear(); os.environ.update(saved)
        self.assertEqual(env.get("KB_TEST_PAT"), "the-one-we-want")
        for leaked in ("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "KB_OTHER_PAT"):
            self.assertNotIn(leaked, env, f"{leaked} reached sky build")
        self.assertIn("PATH", env)
        self.assertIn("SKY_STATE_DIR", env)

    def test_no_kb_means_no_secret_at_all(self):
        from ethan import hands
        env = hands.build_env({"sky": {}}, None)
        self.assertFalse([k for k in env if k.endswith("_PAT") or "TOKEN" in k or "KEY" in k])

    def test_kinds_map_to_the_four_roles_and_default_to_read_only(self):
        from ethan import hands
        self.assertEqual(hands.role_for("build"), "developer")
        self.assertEqual(hands.role_for("review"), "reviewer")
        self.assertEqual(hands.role_for("design"), "architect")
        self.assertEqual(hands.role_for("security"), "security")
        self.assertEqual(hands.role_for("something-new"), "reviewer")
        self.assertEqual(hands.role_for("build", review=True), "reviewer")

    def test_a_missing_sky_is_reported_not_raised(self):
        from ethan import hands
        empty = tempfile.mkdtemp()
        saved = dict(os.environ)
        try:
            os.environ["PATH"] = empty
            os.environ.pop("SKY_BIN", None)
            res = hands.run("claude", "brief", None)
        finally:
            os.environ.clear(); os.environ.update(saved)
        self.assertFalse(res["ok"])
        self.assertIn("sky is not installed", res["out"])
        self.assertNotIn("run_id", res, "no run row should exist for a launch that never began")

    @unittest.skipIf(sys.platform == "win32", "runs a #!/bin/sh fake sky directly; Windows has no /bin/sh")
    def test_cores_json_line_is_what_ethan_reads(self):
        """A fake `sky` on PATH: prose, then the one structured line."""
        from ethan import hands
        fake = tempfile.mkdtemp()
        script = os.path.join(fake, "sky")
        summary = {"sky": "build", "run_id": "run-20260914-000001-001",
                   "directory": "/tmp/sky-run", "outcome": "finished", "ok": True,
                   "usage": {"available": True, "cost_usd": 0.0123, "tokens": 1500},
                   "result_text": "the hand did the thing"}
        with open(script, "w") as fh:
            fh.write("#!/bin/sh\necho 'run run-20260914-000001-001   me   KB x'\n"
                     "echo 'git block proven: ok'\n"
                     f"echo '{json.dumps(summary)}'\n")
        os.chmod(script, 0o755)
        saved = dict(os.environ)
        try:
            os.environ["PATH"] = fake + os.pathsep + os.environ.get("PATH", "")
            os.environ.pop("SKY_BIN", None)
            res = hands.run("claude", "do the thing", None, kind="build")
        finally:
            os.environ.clear(); os.environ.update(saved)
        self.assertTrue(res["ok"], res["out"])
        self.assertEqual(res["sky_run_id"], "run-20260914-000001-001")
        self.assertEqual(res["sky_dir"], "/tmp/sky-run")
        self.assertEqual(res["out"], "the hand did the thing")
        self.assertEqual(res["usage"]["cost_usd"], 0.0123)
        self.assertEqual(res["outcome"], "finished")

    @unittest.skipIf(sys.platform == "win32", "runs a #!/bin/sh fake sky directly; Windows has no /bin/sh")
    def test_a_structured_refusal_is_a_result_not_a_crash(self):
        from ethan import hands
        fake = tempfile.mkdtemp()
        script = os.path.join(fake, "sky")
        summary = {"sky": "build", "outcome": "refused", "ok": False, "stage": "readiness",
                   "reason": "this brain is not ready for build: safety missing"}
        with open(script, "w") as fh:
            fh.write(f"#!/bin/sh\necho 'sky build refused' >&2\necho '{json.dumps(summary)}'\nexit 1\n")
        os.chmod(script, 0o755)
        saved = dict(os.environ)
        try:
            os.environ["PATH"] = fake + os.pathsep + os.environ.get("PATH", "")
            os.environ.pop("SKY_BIN", None)
            res = hands.run("claude", "build it", None, kind="build")
        finally:
            os.environ.clear(); os.environ.update(saved)
        self.assertFalse(res["ok"])
        self.assertEqual(res["outcome"], "refused")
        self.assertIn("not ready", res["out"])

    def test_the_source_no_longer_spawns_a_hand_directly(self):
        """The class of mistake, not one instance: no bare hand binary in argv[0]."""
        with open(os.path.join(ROOT, "ethan", "hands.py"), encoding="utf-8") as fh:
            src = fh.read()
        for bare in ('["claude"', "['claude'", '["codex"', '["kimi"', 'h["cmd"]', "review_cmd"):
            self.assertNotIn(bare, src, f"hands.py still builds a bare hand command: {bare}")
        self.assertIn("env=env", src, "Popen must be given an explicit environment")


class OneAnswerForWhereTheKbMapIs(unittest.TestCase):
    """The router and the hand must be looking at the same file.

    They were not. `kb.kb_map()` fell back to `config/kb-map.example.json` when the real
    map was absent — which is every clean checkout — while `hands.build_command` passed
    `sky --kb-map config/kb-map.json` unconditionally. Nothing complained, because the
    router had already loaded a perfectly good map by then. The disagreement only showed
    up when something was actually built, and then as a path error about a file the
    person had never been told to create.
    """

    def test_the_hand_is_given_the_map_the_router_read(self):
        from ethan import hands
        from ethan.kb import kb_map_path
        cmd = hands.build_command({}, role="developer", hand="claude", brief="x")
        self.assertIn("--kb-map", cmd)
        self.assertEqual(cmd[cmd.index("--kb-map") + 1], kb_map_path())

    def test_the_resolved_map_is_a_file_that_exists(self):
        """A clean checkout must resolve to something real, not a hoped-for path."""
        from ethan.kb import kb_map_path
        self.assertTrue(os.path.isfile(kb_map_path()), f"{kb_map_path()} does not exist")

    def test_the_real_map_wins_when_it_is_there(self):
        from ethan import kb
        from ethan.util import config_dir
        real = os.path.join(config_dir(), "kb-map.json")
        if os.path.isfile(real):
            self.assertEqual(kb.kb_map_path(), real)
        else:
            self.assertTrue(kb.kb_map_path().endswith("kb-map.example.json"))


# This block used to sit in the middle of the file, so running it directly stopped here
# and the classes below were never even defined — the documented command quietly covered
# less than `unittest discover` did. It runs the whole file now: the printed checks
# first, then every TestCase, so the two ways of running agree.
if __name__ == "__main__":
    print("Ethan regression tests")
    failed = run_all()
    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
    print("\nand the rest of the suite:")
    result = unittest.main(exit=False, verbosity=2, argv=[sys.argv[0]]).result
    sys.exit(1 if failed or not result.wasSuccessful() else 0)
