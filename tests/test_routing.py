"""Routing, the unknown-KB rule, what the router model is shown, the console's
POST checks, the local folder KB and the demo.

Each class is one roadmap row (EH-001, 002, 003, 005) or one shipped feature. The
model is a stub that records every call, so "no model call" is something a test can
count rather than something the code promises.
"""
import contextlib, http.client, json, os, socket, subprocess, sys, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import door_console, hands, harvest, kb, llm, router, store  # noqa: E402

MAP = {
    "billing_kb": {"purpose": "the billing platform: invoices and refunds", "privacy": "work",
                   "write": True, "hints": ["PROJ-", "invoice"], "folder": "unused"},
    "notes_kb":   {"purpose": "personal notes", "privacy": "personal",
                   "write": True, "hints": ["notes"], "folder": "unused"},
    "ops_kb":     {"purpose": "operations runbooks", "privacy": "work",
                   "write": True, "hints": ["runbook", "invoice"], "folder": "unused"},
}


class Stub:
    """Stands in for the router model and the hand; records what each was given."""

    def __init__(self, route=None):
        self.route, self.calls, self.runs = route, [], []

    def ask(self, messages, json_schema=None):
        self.calls.append(messages)
        if json_schema:
            return dict(self.route)
        return "an answer"

    def run(self, hand, brief, repo=None, review=False, task_id=None, kb=None, kind=None):
        self.runs.append({"hand": hand, "kb": kb, "kind": kind, "brief": brief})
        return {"ok": True, "out": "done"}


@contextlib.contextmanager
def stubbed(route=None):
    stub = Stub(route)
    saved = (kb._MAP, llm.ask, hands.run, kb.search, harvest.run)
    kb._MAP = MAP
    llm.ask, hands.run = stub.ask, stub.run
    kb.search = lambda name, q, k=5: []
    harvest.run = lambda *a, **k: ("nothing", "stub")
    try:
        yield stub
    finally:
        kb._MAP, llm.ask, hands.run, kb.search, harvest.run = saved


def handle(text, chat="t"):
    replies = []
    router.handle(f"{chat}-{id(replies)}", text, replies.append, door="console")
    return replies


def route(kind="question", kb_name="billing_kb", hand="none"):
    return {"kind": kind, "kb": kb_name, "hand": hand, "steps": [],
            "search_query": "q", "reason": "stub"}


class HintsDecideWithoutAModelCall(unittest.TestCase):
    """EH-001."""

    def test_a_hinted_review_makes_no_model_call(self):
        with stubbed() as stub:
            handle("review PROJ-412")
        self.assertEqual(stub.calls, [], "a hinted ask must not reach the model")
        self.assertEqual(len(stub.runs), 1)
        self.assertEqual((stub.runs[0]["kb"], stub.runs[0]["kind"]), ("billing_kb", "review"))

    def test_a_hint_matches_whatever_the_case(self):
        for ask in ("review proj-412", "review PROJ-412", "Review Proj-412"):
            with stubbed() as stub:
                handle(ask)
            self.assertEqual(stub.calls, [], ask)
            self.assertEqual(stub.runs[0]["kb"], "billing_kb", ask)

    def test_two_matching_kbs_go_to_the_model_with_only_those_two(self):
        with stubbed(route("question", "ops_kb")) as stub:
            handle("what does the invoice say")
        system = stub.calls[0][0]["content"]
        self.assertIn("billing_kb", system)
        self.assertIn("ops_kb", system)
        self.assertNotIn("notes_kb", system)

    def test_an_unclear_kind_calls_the_model_and_the_hinted_kb_wins(self):
        with stubbed(route("build", "notes_kb", "auto")) as stub:
            handle("could you look at PROJ-9 for me")
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(stub.runs[0]["kb"], "billing_kb")

    def test_an_ask_that_sounds_like_a_chain_is_left_to_the_model(self):
        self.assertIsNone(router._hint_kind("fix PROJ-1 with claude then review with codex"))


class NoSilentFallbackToTheFirstKb(unittest.TestCase):
    """EH-002."""

    def test_an_unknown_kb_is_said_and_nothing_is_filed_under_another(self):
        with stubbed(route("build", "no_such_kb", "auto")) as stub:
            replies = handle("please tidy the docs")
        self.assertTrue(any("No knowledge base matched" in r for r in replies), replies)
        self.assertIsNone(stub.runs[0]["kb"], "the hand must not be given a KB nobody chose")
        self.assertTrue(any("no knowledge base was chosen" in r for r in replies), replies)
        self.assertIsNone(store.recent_tasks(1)[0]["kb"], "the ledger must record no KB")

    def test_a_kb_outside_the_hinted_pair_is_refused(self):
        with stubbed(route("question", "notes_kb")):
            replies = handle("what does the invoice say")
        self.assertTrue(any("No knowledge base matched" in r for r in replies), replies)


class TheRouterModelSeesOnlyPurposesAndTheAsk(unittest.TestCase):
    """EH-003."""

    def test_the_routing_call_is_one_system_and_one_user_message(self):
        with stubbed(route("chat", "billing_kb")) as stub:
            chat = "eh003"
            store.remember(chat, "assistant", "SECRET EARLIER HAND OUTPUT")
            router.handle(chat, "hello there", lambda m: None, door="console")
        routing = stub.calls[0]
        self.assertEqual([m["role"] for m in routing], ["system", "user"])
        self.assertEqual(routing[1]["content"], "hello there")
        self.assertNotIn("SECRET EARLIER HAND OUTPUT", json.dumps(routing))

    def test_each_ask_is_stored_once_through_the_console(self):
        with stubbed(route("chat", "billing_kb")):
            door_console._ask("only once please", chat="eh003-console")
        texts = [m["content"] for m in store.recent("eh003-console", 20)]
        self.assertEqual(texts.count("only once please"), 1, texts)


@contextlib.contextmanager
def console():
    srv = door_console.open_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown(); srv.server_close()


def post(port, body, headers):
    """The status the console answers with. On Windows the server's early close on a
    refusal can reset the socket before the client has read the status; that is the
    same refusal, so the request is retried, and the status is still asserted."""
    for attempt in range(3):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            c.request("POST", "/api/ask", body=body, headers=headers)
            r = c.getresponse(); r.read()
            return r.status
        except (ConnectionResetError, ConnectionAbortedError, http.client.RemoteDisconnected):
            if attempt == 2:
                raise
        finally:
            c.close()


class TheConsoleRefusesOtherWebPages(unittest.TestCase):
    """EH-005. The ask is empty, so an accepted request never starts any work."""

    def test_a_foreign_origin_is_refused(self):
        with console() as port:
            self.assertEqual(post(port, '{"text": ""}', {"Content-Type": "application/json",
                                                         "Origin": "https://evil.example"}), 403)

    def test_a_body_that_is_not_json_is_refused(self):
        with console() as port:
            self.assertEqual(post(port, '{"text": ""}', {"Content-Type": "text/plain"}), 415)

    def test_an_oversized_body_is_refused(self):
        with console() as port:
            big = json.dumps({"text": "x" * (door_console.MAX_BODY + 1)})
            self.assertEqual(post(port, big, {"Content-Type": "application/json"}), 413)

    def test_its_own_page_and_the_cli_still_get_through(self):
        with console() as port:
            own = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
            self.assertEqual(post(port, '{"text": ""}', own), 400)     # 400 = empty ask, past the checks
            self.assertEqual(post(port, '{"text": ""}', {"Content-Type": "application/json"}), 400)

    def test_a_port_in_use_fails_at_once(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); s.listen()
            with self.assertRaises(OSError):
                door_console.open_server(s.getsockname()[1])


class ALocalFolderKb(unittest.TestCase):
    """A KB that is a folder of Markdown notes: searched and written with no server."""

    def test_search_and_ingest(self):
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "refunds.md"), "w") as fh:
            fh.write("Refunds are allowed for 30 days.")
        saved = kb._MAP
        kb._MAP = {"local": {"purpose": "p", "privacy": "work", "write": True, "folder": folder}}
        try:
            hits = kb.search("local", "how long are refunds allowed", k=3)
            job = kb.ingest("local", "new-note.md", "a new note", {})
        finally:
            kb._MAP = saved
        self.assertEqual([h["source"] for h in hits], ["refunds.md"])
        self.assertTrue(os.path.isfile(os.path.join(folder, "new-note.md")))
        self.assertEqual(job["job_id"], "local:new-note.md")


class TheDemoRunsWithNoKey(unittest.TestCase):
    """`./run.sh --demo`: route, launch, close-out and ledger, with no key or server."""

    def test_the_demo_ends_in_a_close_out(self):
        env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "ETHAN_STATE_DIR")}
        out = subprocess.run([sys.executable, "-m", "ethan.main", "--demo"], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        for line in ("router › review · kb shop_kb · decided by hint",
                     "launch › hand:codex as reviewer via sky build", "Kept: kept in shop_kb",
                     "Session can close", "ledger › task #1 review · kb shop_kb"):
            self.assertIn(line, out.stdout)


def fake_sky_echoing_role():
    """A fake `sky` whose result is the role it was asked for."""
    folder = tempfile.mkdtemp()
    script = os.path.join(folder, "sky")
    with open(script, "w") as fh:
        fh.write("#!/usr/bin/env python3\nimport json, sys\na = sys.argv\n"
                 "role = a[a.index('--role') + 1]\n"
                 "print(json.dumps({'sky': 'build', 'ok': True, 'result_text': 'role=' + role}))\n")
    os.chmod(script, 0o755)
    return script


class ChainStepsRunWithTheRightRole(unittest.TestCase):
    """EH-004. The real hands.run, against a fake `sky` that reports the role."""

    def test_a_build_step_runs_as_developer_and_a_review_step_as_reviewer(self):
        chain = dict(route("chain", "billing_kb"), steps=[
            {"hand": "claude", "kind": "build", "goal": "fix it"},
            {"hand": "codex", "kind": "review", "goal": "review the fix"}])
        real_run = hands.run
        roles, harvested = [], []
        def recording_run(*a, **k):
            res = real_run(*a, **k)
            roles.append(res["out"])
            return res
        saved_bin = os.environ.get("SKY_BIN")
        os.environ["SKY_BIN"] = fake_sky_echoing_role()
        try:
            with stubbed(chain):
                hands.run = recording_run
                harvest.run = lambda *a, **k: harvested.append(a) or ("nothing", "stub")
                router.handle("eh004", "fix PROJ-1 with claude then review with codex",
                              lambda m: None, door="console")
        finally:
            if saved_bin is None:
                os.environ.pop("SKY_BIN", None)
            else:
                os.environ["SKY_BIN"] = saved_bin
        self.assertEqual(roles, ["role=developer", "role=reviewer"])
        last_task = store.recent_tasks(1)[0]["id"]
        self.assertEqual(harvested[0][5], last_task, "the close-out must name the last step's task")


class EveryAskEndsWithOneCloseOutLine(unittest.TestCase):
    """EH-008."""

    def close_outs(self, the_route, ask="hello", raising=False):
        with stubbed(the_route):
            if raising:
                llm.ask = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model down"))
            replies = handle(ask)
        return replies, [r for r in replies if r.startswith(router.CLOSE_OUT)]

    def test_each_kind_ends_with_exactly_one(self):
        for kind in ("question", "chat", "followup", "status", "build", "review"):
            replies, closes = self.close_outs(route(kind, "billing_kb", "auto"))
            self.assertEqual(len(closes), 1, f"{kind}: {replies}")
            self.assertTrue(replies[-1].startswith(router.CLOSE_OUT), f"{kind}: {replies}")

    def test_an_error_is_reported_and_still_closes(self):
        replies, closes = self.close_outs(None, raising=True)
        self.assertTrue(any(r.startswith("error: model down") for r in replies), replies)
        self.assertEqual(len(closes), 1, replies)

    def test_a_failed_task_still_closes(self):
        with stubbed(route("build", "billing_kb", "auto")):
            hands.run = lambda *a, **k: {"ok": False, "out": "it broke"}
            replies = handle("please tidy up")
        self.assertEqual(len([r for r in replies if r.startswith(router.CLOSE_OUT)]), 1, replies)


class AFileIsIngestedByWhereItLives(unittest.TestCase):
    """EH-006. The folder the file is in picks the KB, never the caller's directory."""

    def setUp(self):
        self.repo, self.outside = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.saved = kb._MAP
        kb._MAP = {"work_kb": {"purpose": "p", "privacy": "work", "write": True,
                               "folder": tempfile.mkdtemp(), "repos": [self.repo]}}

    def tearDown(self):
        kb._MAP = self.saved

    def note(self, folder):
        path = os.path.join(folder, "note.md")
        with open(path, "w") as fh:
            fh.write("A note long enough to pass the minimum-length gate for ingest.\n")
        return path

    def test_a_file_outside_every_kb_is_refused_even_from_inside_one(self):
        status, info = harvest.ingest_document(self.note(self.outside), "learning",
                                               "console", "t", cwd=self.repo)
        self.assertEqual(status, "refused", info)

    def test_a_file_inside_a_kb_goes_there_from_anywhere(self):
        status, info = harvest.ingest_document(self.note(self.repo), "learning",
                                               "console", "t", cwd=self.outside)
        self.assertEqual(status, "written", info)
        self.assertEqual(info["kb"], "work_kb")


class TheOntologyValidatorStarts(unittest.TestCase):
    """EH-009."""

    def test_with_no_arguments_it_prints_usage_and_exits_2(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "config", "ontologies",
                              "validate_ontology.py")], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("KB_REPO=", out.stdout)

    def test_without_pyyaml_it_names_the_package(self):
        blocker = tempfile.mkdtemp()
        with open(os.path.join(blocker, "yaml.py"), "w") as fh:
            fh.write("raise ImportError('blocked for the test')\n")
        env = dict(os.environ, PYTHONPATH=blocker)
        out = subprocess.run([sys.executable, os.path.join(ROOT, "config", "ontologies",
                              "validate_ontology.py"), "x.yaml"], capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("PyYAML is not installed", out.stdout)


class DoorsShipWithThePrivacyWallOn(unittest.TestCase):
    """EH-007. Telegram files only into personal KBs; the CLI is a door of its own."""

    DECISION = {"keep": True, "kb": "billing_kb", "title": "a-note",
                "body": "A note long enough to pass the minimum length for a harvest.", "why": "w"}

    def test_the_shipped_config_has_telegram_refuse_work(self):
        from ethan import policy
        doors = policy.doors()
        self.assertEqual(doors["telegram-private"]["classes"], ["personal"])
        self.assertIn("work", doors["cli"]["classes"])
        self.assertIn("work", doors["console"]["classes"])

    def test_a_harvest_through_telegram_into_a_work_kb_is_refused(self):
        saved = kb._MAP
        kb._MAP = MAP
        try:
            status, msg = harvest.apply(dict(self.DECISION), "telegram-private", "t", "claude")
        finally:
            kb._MAP = saved
        self.assertEqual(status, "refused", msg)
        self.assertIn("may not write", msg)

    def test_the_same_harvest_through_the_cli_passes_the_wall(self):
        folder = tempfile.mkdtemp()
        saved = kb._MAP
        kb._MAP = {"billing_kb": dict(MAP["billing_kb"], folder=folder)}
        try:
            status, msg = harvest.apply(dict(self.DECISION), "cli", "t", "claude")
        finally:
            kb._MAP = saved
        self.assertEqual(status, "written", msg)

    def test_cli_asks_are_recorded_under_the_cli_door(self):
        import time
        with stubbed(route("build", "billing_kb", "auto")), console() as port:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("POST", "/api/ask", headers={"Content-Type": "application/json"},
                      body=json.dumps({"text": "tidy the docs", "chat": "eh007-cli", "door": "cli"}))
            c.getresponse().read(); c.close()
            for _ in range(50):
                rows = [t for t in store.recent_tasks(10) if t["chat_id"] == "eh007-cli"]
                if rows:
                    break
                time.sleep(0.1)
        self.assertTrue(rows, "the ask never reached the ledger")
        self.assertEqual(rows[0]["door"], "cli")

    def test_a_caller_cannot_claim_another_doors_classes(self):
        self.assertEqual(door_console._door("backfill"), "console")
        self.assertEqual(door_console._door("cli"), "cli")


class NoAbsoluteHomePaths(unittest.TestCase):
    """EH-010: no tracked file names a folder on one person's machine."""

    def test_no_tracked_file_has_a_home_directory_path(self):
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        if files.returncode != 0:
            self.skipTest("not a git checkout")
        pattern = __import__("re").compile(r"/(Users|home)/[A-Za-z0-9._-]+/")
        hits = []
        for rel in files.stdout.split():
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for n, line in enumerate(fh, 1):
                    if pattern.search(line) and "pattern" not in line:
                        hits.append(f"{rel}:{n}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
