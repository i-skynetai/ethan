"""EH-067: one policy file, read in one place; every never and every ask is tried."""
import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, harvest, hands, llm, policy, relay, router, util  # noqa: E402
from tests.test_relay import SESSIONS, FakeBridge  # noqa: E402


def with_policy(**changes):
    """The shipped policy with some values changed, served as the config."""
    p = json.load(open(os.path.join(ROOT, "config", "policy.json"), encoding="utf-8"))
    for path, value in changes.items():
        d = p
        *keys, last = path.split(".")
        for k in keys:
            d = d.setdefault(k, {})
        d[last] = value
    return mock.patch.object(policy, "cfg", side_effect=lambda name: p if name == "policy.json" else util.cfg(name))


class TheFile(unittest.TestCase):
    def test_only_policy_py_reads_the_rules(self):
        for root, _, files in os.walk(os.path.join(ROOT, "ethan")):
            for f in files:
                if f.endswith(".py") and f != "policy.py":
                    src = open(os.path.join(root, f), encoding="utf-8").read()
                    self.assertNotIn('cfg("policy.json")', src, f)
                    self.assertNotIn('"doors.json"', src, f)

    def test_the_shipped_values(self):
        self.assertEqual(policy.action("relay_implementation"), "ask")
        for never in ("send_in_your_name", "push_or_merge", "start_or_resume_a_session"):
            self.assertEqual(policy.action(never), "never", never)
        self.assertEqual(policy.action("something nobody wrote down"), "never")
        self.assertTrue(policy.may_relay("console") and policy.may_relay("cli"))
        self.assertFalse(policy.may_relay("telegram-private"))
        self.assertFalse(policy.may_build("backfill"))
        self.assertTrue(policy.may_build("console"))
        self.assertEqual(policy.may_file("telegram-private", "work"), (False, ["personal"]))

    def test_an_unknown_door_may_do_nothing(self):
        self.assertIsNone(policy.door("smoke-signal"))
        self.assertFalse(policy.may_relay("smoke-signal"))
        self.assertFalse(policy.may_build("smoke-signal"))
        self.assertEqual(policy.may_file("smoke-signal", "personal"), (False, []))

    def test_a_value_that_is_not_a_level_is_never(self):
        with with_policy(**{"actions.phone": "sometimes"}):
            self.assertEqual(policy.action("phone"), "never")

    def test_an_older_config_folder_with_doors_json_still_works(self):
        """Found in review: the fallback used to fill in four actions and let the rest
        default to never, and a legacy clock door with no `build` key could build."""
        shipped = json.load(open(os.path.join(ROOT, "ethan", "defaults", "policy.json"), encoding="utf-8"))
        legacy = {"telegram-private": {"classes": ["personal"]},
                  "console": {"classes": ["personal"], "relay": True},
                  "my-door": {"classes": ["work"]}}
        with tempfile.TemporaryDirectory() as tmp:
            json.dump(legacy, open(os.path.join(tmp, "doors.json"), "w"))
            json.dump({}, open(os.path.join(tmp, "ethan.json"), "w"))
            with mock.patch.dict(os.environ, {"ETHAN_CONFIG_DIR": tmp}):
                self.assertEqual(policy.load()["actions"], shipped["actions"])     # every shipped action
                for name in ("remind", "read_ledger", "relay_review_only", "watch", "phone", "file_to_kb"):
                    self.assertTrue(policy.allowed(name), name)
                self.assertEqual(policy.action("relay_implementation"), "ask")
                self.assertEqual(policy.may_file("console", "personal"), (True, ["personal"]))   # the person's doors win
                self.assertEqual(policy.may_file("console", "work"), (False, ["personal"]))
                self.assertFalse(policy.may_build("backfill"))                     # shipped build=false fills the gap
                self.assertTrue(policy.may_build("console") and policy.may_build("my-door"))
                self.assertEqual(policy.may_file("my-door", "work"), (True, ["work"]))
                # and the behaviour, not only the values: a reminder is set, a relay goes out
                from ethan import clock
                out = []
                clock.take("legacy-remind", "remind me in 5 minutes to stretch", out.append, "console")
                self.assertIn("I will remind you", out[0])


class EveryNeverAndEveryAsk(unittest.TestCase):
    """The rules as the code enforces them, not as the file states them."""

    def test_a_door_that_may_not_build_is_refused_a_build(self):
        route = {"kind": "build", "kb": "none", "hand": "claude", "steps": [], "search_query": "", "reason": ""}
        with mock.patch.object(llm, "ask", return_value=dict(route)), \
                mock.patch.object(hands, "run", side_effect=AssertionError("a hand started")):
            out = []
            router.handle("p-build", "write the summary", out.append, door="console", scheduled=True)
            self.assertIn("may only remind and read", out[0])
            out = []
            router.handle("p-build2", "write the summary", out.append, door="backfill")
            self.assertIn("may only remind and read", out[0])

    def test_a_door_that_may_not_relay_is_refused_a_relay(self):
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake:
            out = []
            router.handle("p-relay", "ask the codex session codex-ethan to look", out.append, door="telegram-private")
        self.assertIn("telegram-private door", out[0])
        self.assertEqual(fake.calls, [])

    def test_implementation_is_ask_so_only_an_explicit_ask_gets_it_and_never_downgrades(self):
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            router.handle("p-impl", "tell the codex session codex-ethan to look at EH-1", print, door="console")
            router.handle("p-impl", "tell the codex session codex-ethan to implement EH-1", print, door="console")
            modes = [s[s.index("--mode") + 1] for s in fake.sends()]
            self.assertEqual(modes, ["review-only", "implementation"])
            with with_policy(**{"actions.relay_implementation": "never"}):
                router.handle("p-impl", "tell the codex session codex-ethan to implement EH-2", print, door="console")
            self.assertEqual(fake.sends()[-1][fake.sends()[-1].index("--mode") + 1], "review-only")

    def test_filing_outside_a_doors_classes_is_refused(self):
        from tests.test_routing import stubbed
        decision = {"keep": True, "kb": "billing_kb", "title": "n", "why": "w",
                    "body": "A note long enough to pass the minimum length for a harvest."}
        with stubbed():
            status, msg = harvest.apply(decision, "telegram-private", "p-file", "codex")
        self.assertEqual(status, "refused")
        self.assertIn("may not write", msg)
        with stubbed():
            status, msg = harvest.apply(decision, "smoke-signal", "p-file", "codex")
        self.assertEqual((status, "unknown door" in msg), ("refused", True))


class EveryActionAtItsEffect(unittest.TestCase):
    """Found in review: the file advertised actions that only one call site read.
    Each value is now tried where it takes effect."""

    def test_remind_never_refuses_and_holds_the_clock(self):
        from ethan import clock
        with with_policy(**{"actions.remind": "never"}):
            out = []
            self.assertTrue(clock.take("a-remind", "remind me in 5 minutes to stretch", out.append, "console"))
            self.assertIn("may not set reminders", out[0])
            self.assertEqual(clock.scheduled("a-remind"), [])
            self.assertEqual(clock.tick(), [])

    def test_read_ledger_never_refuses_status(self):
        from ethan import status
        with with_policy(**{"actions.read_ledger": "never"}):
            self.assertIn("may not read the ledger", status.text())

    def test_relay_review_only_never_sends_nothing(self):
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []), \
                with_policy(**{"actions.relay_review_only": "never"}):
            out = []
            router.handle("a-relay", "ask the codex session codex-ethan to look", out.append, door="console")
        self.assertIn("may not pass asks", out[0])
        self.assertEqual(fake.sends(), [])

    def test_watch_never_refuses_setting_and_running(self):
        from ethan import watch
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            out = []
            with with_policy(**{"actions.watch": "never"}):
                router.handle("a-watch", "watch mail through the claude session ethan every day at 09:00: what must I reply to?",
                              out.append, door="console")
                self.assertIn("may not watch", out[0])
                self.assertEqual(watch.active("a-watch"), [])
            router.handle("a-watch", "watch mail through the claude session ethan every day at 09:00: what must I reply to?",
                          out.append, door="console")
            (w,) = watch.active("a-watch")
            got = []
            with with_policy(**{"actions.watch": "never"}):
                watch.run(w["id"], lambda c, d, t: got.append(t))
            self.assertIn("did not run", got[0])
            self.assertEqual(fake.sends(), [])

    def test_phone_never_keeps_the_desktop_and_records_why(self):
        from ethan import door_telegram, reach
        sent = []
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_ALLOWED_USER_IDS": "1"}), \
                mock.patch.object(door_telegram, "send", lambda tok, c, t: sent.append(t)), \
                with_policy(**{"actions.phone": "never"}):
            routes = reach.tell("a-phone", "console", "URGENT: look")
        self.assertEqual((routes, sent), (["conversation"], []))
        self.assertIn(("phone", "skipped", "policy: actions.phone is never"),
                      [(r["route"], r["state"], r["why"]) for r in reach.recent(5) if r["chat_id"] == "a-phone"])

    def test_file_to_kb_never_refuses_a_harvest(self):
        from tests.test_routing import stubbed
        decision = {"keep": True, "kb": "billing_kb", "title": "n", "why": "w",
                    "body": "A note long enough to pass the minimum length for a harvest."}
        with stubbed(), with_policy(**{"actions.file_to_kb": "never"}):
            status, msg = harvest.apply(decision, "console", "a-file", "codex")
        self.assertEqual(status, "refused")
        self.assertIn("file_to_kb", msg)

    def test_every_send_path_meets_the_rules_as_they_are_now(self):
        """Found in review: a watch sent through dispatch without the checks a fresh ask
        got. The gate is at the one send boundary, so a watch at its time, an answer to
        'which session?' and a recovery after a restart all meet the current rules."""
        import datetime as dt
        from ethan import store, watch
        from tests.test_follow import Delivered
        thu9 = dt.datetime(2026, 10, 8, 9, 0).timestamp()
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        for r in store.open_relays():
            store.update_relay(r["id"], state="dropped", note="test isolation")
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            # a watch set while allowed, run after relays became never
            router.handle("g-watch", "watch mail through the claude session ethan every day at 09:00: what must I reply to?",
                          print, door="console")
            (w,) = watch.active("g-watch")
            got = Delivered()
            with with_policy(**{"actions.relay_review_only": "never"}):
                watch.run(w["id"], got, now=thu9)
            self.assertIn("Not sent", got.texts("g-watch")[-1])
            self.assertEqual(fake.sends(), [])
            # the same watch, run after the console door lost its relay right
            with with_policy(**{"doors.console.relay": False}):
                watch.run(w["id"], got, now=thu9)
            self.assertIn("console door may not pass work", got.texts("g-watch")[-1])
            self.assertEqual(fake.sends(), [])
            # a "which session?" answered after the rules changed
            out = []
            router.handle("g-clarify", "ask the claude session to look at EH-1", out.append, door="console")
            self.assertIn("Which session", out[0])
            with with_policy(**{"actions.relay_review_only": "never"}):
                out = []
                router.handle("g-clarify", "1", out.append, door="console")
            self.assertIn("Not sent", out[0])
            self.assertEqual(fake.sends(), [])
            # a relay left half-sent by a crash, recovered after the rules changed
            router.handle("g-recover", "ask the codex session codex-ethan to look at EH-1", print, door="console")
            (r,) = [x for x in store.recent_relays(10) if x["chat_id"] == "g-recover"]
            store.update_relay(r["id"], state="sending", message_id=None)
            fake.calls.clear()
            got = Delivered()
            with with_policy(**{"actions.relay_review_only": "never"}):
                relay.follow(got, recover=True)
            self.assertEqual(fake.sends(), [])
            self.assertIn("was not sent after the restart", got.texts("g-recover")[-1])
            self.assertEqual(store.relay(r["id"])["state"], "refused")
            # implementation asked for, but never in the policy: sent review-only, and said so
            with with_policy(**{"actions.relay_implementation": "never"}):
                out = []
                router.handle("g-impl", "tell the codex session codex-ethan to implement EH-1", out.append, door="console")
            (send,) = fake.sends()
            self.assertEqual(send[send.index("--mode") + 1], "review-only")

    def test_the_three_promises_have_no_code_path(self):
        from ethan import brief
        # no sending or pushing in Ethan's name: the hand is told not to, and no module speaks to a remote
        self.assertIn("push to any remote", brief.render("t", [], None))
        src = {f: open(os.path.join(ROOT, "ethan", f), encoding="utf-8").read()
               for f in os.listdir(os.path.join(ROOT, "ethan")) if f.endswith(".py")}
        for f, s in src.items():
            self.assertNotIn("git push", s, f)
            self.assertNotIn("sendMessage", s.replace("door_telegram", "") if f != "door_telegram.py" else "", f)
        # no starting or resuming a session: the bridge is only ever asked to register the app, send, ask status, read and ack
        self.assertNotIn("--resume", src["relay.py"])
        self.assertNotIn("codex-session", src["relay.py"])
        self.assertNotIn('"register", "claude"', src["relay.py"])
        self.assertNotIn('"register", "codex"', src["relay.py"])


if __name__ == "__main__":
    unittest.main()
