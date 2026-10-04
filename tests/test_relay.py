"""EH-058: an ask for a running session is relayed through the bridge, never launched.

The bridge is faked twice: in-process for the routing rules, and as a real
`agent_bridge` package in a temporary folder for the process boundary. The model and
the hand are stubs that fail the test if anything reaches them.
"""
import contextlib, json, os, sys, tempfile, textwrap, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, hands, llm, relay, router, store  # noqa: E402
from tests.test_routing import stubbed  # noqa: E402

SESSIONS = [
    {"agent": "claude", "native_id": "c-1", "name": "ethan", "project": "/w/ethan",
     "delivery": "claude-inbox", "status": "busy", "last_seen": None},
    {"agent": "claude", "native_id": "c-2", "name": "review", "project": "/w/skynet",
     "delivery": "claude-inbox", "status": "busy", "last_seen": None},
    {"agent": "codex", "native_id": "x-1", "name": "codex-ethan", "project": "/w/ethan",
     "delivery": "codex-exec", "status": "unknown", "last_seen": None},
    {"agent": "app", "native_id": "ethan", "name": "ethan", "project": "/w/ethan",
     "delivery": "app-poll", "status": "unknown", "last_seen": None},
]


class FakeBridge:
    def __init__(self, state="queued", refuse=None):
        self.calls, self.state, self.refuse = [], state, refuse

    def __call__(self, *args, timeout=60):
        self.calls.append(args)
        if args[0] == "register":
            return {"agent": "app", "name": "ethan"}
        if self.refuse:
            raise relay.RelayError(self.refuse)
        return {"id": f"m_{len(self.calls)}", "state": self.state, "note": "fake"}

    def sends(self):
        return [a for a in self.calls if a[0] == "send"]


@contextlib.contextmanager
def bridge(sessions=SESSIONS, available=True, **kw):
    fake = FakeBridge(**kw)
    reg = {"available": available, "sessions": sessions if available else [], "note": "fake registry."}
    with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
            mock.patch.object(relay, "_bridge", fake), \
            mock.patch.object(relay, "_REGISTERED", []), \
            mock.patch.object(llm, "ask", side_effect=AssertionError("no model call for a relay")), \
            mock.patch.object(hands, "run", side_effect=AssertionError("a relay never starts a hand")):
        yield fake


def ask(text, chat, door="console", cwd=None):
    out = []
    router.handle(chat, text, out.append, door=door, cwd=cwd)
    return out


def last_relay():
    return store.recent_relays(1)[0]


class WhatIsARelay(unittest.TestCase):
    def test_asks_that_tell_ethan_to_pass_work_on(self):
        for text in ("ask the running Claude session to develop EH-023",
                     "Tell the codex session to review the README",
                     "please send this to codex-ethan: check the tests"):
            self.assertTrue(relay.wants_relay(text, SESSIONS), text)

    def test_asks_that_are_not_relays(self):
        for text in ("fix the invoice bug", "ask codex to review README.md",
                     "tell me about sessions", "what sessions are running?"):
            self.assertFalse(relay.wants_relay(text, SESSIONS), text)


class OneTarget(unittest.TestCase):
    def test_named_session_gets_the_ask_review_only(self):
        with bridge() as fake:
            out = ask("ask the codex session codex-ethan to look at EH-023", "one-named")
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--to") + 1], "codex:x-1")
        self.assertEqual(send[send.index("--from") + 1], "app:ethan")
        self.assertEqual(send[send.index("--mode") + 1], "review-only")
        self.assertIn("look at EH-023", send[-1])
        self.assertIn("queued, not read", out[0])
        self.assertIn("review-only", out[0])
        r = last_relay()
        self.assertEqual((r["state"], r["message_id"], r["target"]), ("queued", "m_2", "codex:codex-ethan"))

    def test_implement_hands_over_ownership(self):
        with bridge() as fake:
            ask("tell the codex session to implement EH-023", "one-impl")
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--mode") + 1], "implementation")

    def test_mentioning_an_implementation_plan_stays_review_only(self):
        with bridge() as fake:
            ask("ask the codex session to review the implementation plan", "one-plan")
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--mode") + 1], "review-only")

    def test_callers_folder_narrows_the_choice(self):
        with bridge() as fake:
            ask("ask the claude session to look at the roadmap", "one-cwd",
                cwd=os.path.join(os.sep, "w", "ethan", "docs"))
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--to") + 1], "claude:c-1")

    def test_delivered_is_not_called_done(self):
        with bridge(state="delivered"):
            out = ask("ask the codex session to review the tests", "one-delivered")
        self.assertIn("not the same as done", out[0])


class AskWhenUnsure(unittest.TestCase):
    def test_the_original_ask_gets_a_question_then_goes_where_the_answer_says(self):
        with bridge() as fake:
            out = ask("ask the running Claude session to develop EH-023 and EH-028", "unsure")
            self.assertEqual(fake.sends(), [])
            self.assertIn("I have not sent anything yet", out[0])
            self.assertIn("1. claude:ethan", out[0])
            self.assertIn("2. claude:review", out[0])
            self.assertNotIn("codex", out[0])
            self.assertEqual(last_relay()["state"], "needs-target")
            out = ask("2", "unsure")
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--to") + 1], "claude:c-2")
        self.assertIn("develop EH-023 and EH-028", send[-1])
        self.assertEqual(last_relay()["state"], "queued")

    def test_answer_by_name(self):
        with bridge() as fake:
            ask("ask the claude session to look at EH-028", "byname")
            ask("the ethan one", "byname")
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--to") + 1], "claude:c-1")

    def test_cancel_sends_nothing(self):
        with bridge() as fake:
            ask("ask the claude session to look at EH-028", "cancel")
            out = ask("cancel", "cancel")
        self.assertEqual(fake.sends(), [])
        self.assertIn("Nothing was sent", out[0])
        self.assertEqual(last_relay()["state"], "dropped")

    def test_an_unrelated_next_ask_drops_the_question_and_is_routed(self):
        with bridge():
            ask("ask the claude session to look at EH-028", "unrelated")
        route = {"kind": "chat", "kb": "none", "hand": "none", "steps": [],
                 "search_query": "", "reason": "small talk"}
        with stubbed(route) as stub, \
                mock.patch.object(bridge_registry, "sessions",
                                  return_value={"available": True, "sessions": SESSIONS, "note": ""}):
            out = ask("good morning", "unrelated")
        self.assertIn("dropped relay", out[0])
        self.assertEqual(out[1], "an answer")
        self.assertEqual(len(stub.calls), 2)       # routed, then answered
        self.assertEqual(stub.runs, [])

    def test_no_matching_session(self):
        only_codex = [s for s in SESSIONS if s["agent"] == "codex"]
        with bridge(sessions=only_codex) as fake:
            out = ask("ask the claude session to look at EH-023", "nomatch")
        self.assertEqual(fake.sends(), [])
        self.assertIn("sent nothing and started nothing", out[0])


class Refusals(unittest.TestCase):
    def test_telegram_may_not_relay(self):
        with bridge() as fake:
            out = ask("ask the codex session codex-ethan to look at EH-023", "tg", door="telegram-private")
        self.assertEqual(fake.calls, [])
        self.assertIn("telegram-private door", out[0])

    def test_no_bridge_is_said_plainly(self):
        with bridge(available=False) as fake:
            out = ask("ask the codex session to look at EH-023", "nobridge")
        self.assertEqual(fake.calls, [])
        self.assertIn("nothing new was started", out[0])

    def test_bridge_refusal_is_recorded_and_shown(self):
        with bridge(refuse="codex is busy in another project") as fake:
            out = ask("ask the codex session codex-ethan to look at EH-023", "refused")
        self.assertEqual(len(fake.sends()), 1)
        self.assertIn("codex is busy in another project", out[0])
        r = last_relay()
        self.assertEqual((r["state"], r["message_id"]), ("send-failed", None))

    def test_every_relay_still_ends_with_one_close_out(self):
        with bridge():
            out = ask("ask the codex session codex-ethan to look at EH-023", "closeout")
        self.assertEqual(sum(o.startswith(router.CLOSE_OUT) for o in out), 1)

    def test_an_unanswered_relay_is_not_called_nothing_pending(self):
        with bridge():
            out = ask("ask the codex session codex-ethan to look at EH-023", "pending")
        self.assertTrue(out[-1].startswith("Not closing"), out[-1])
        self.assertIn("to codex:codex-ethan is queued", out[-1])

    def test_a_relay_nobody_sent_does_not_hold_the_close_out(self):
        with bridge(refuse="no"):
            out = ask("ask the codex session codex-ethan to look at EH-023", "notsent")
        self.assertTrue(out[-1].startswith("Session can close"), out[-1])


FAKE_CLI = '''
import json, os, sys
with open(os.environ["FAKE_BRIDGE_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1] == "send" and "refuse" in sys.argv[-1]:
    print("agent-bridge: duplicate: this exact request is already message m_old", file=sys.stderr)
    sys.exit(1)
print(json.dumps({"id": "m_fake", "state": "queued", "note": "fake"}))
'''


class ProcessBoundary(unittest.TestCase):
    """The real `_bridge`: a separate process, no shell, JSON back."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ethan-fake-bridge-")
        pkg = os.path.join(self.tmp, "agent_bridge")
        os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").close()
        with open(os.path.join(pkg, "cli.py"), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(FAKE_CLI))
        self.log = os.path.join(self.tmp, "calls.log")
        env = mock.patch.dict(os.environ, {"ETHAN_BRIDGE_DIR": self.tmp, "FAKE_BRIDGE_LOG": self.log})
        env.start()
        self.addCleanup(env.stop)
        reg = mock.patch.object(relay, "_REGISTERED", [])
        reg.start()
        self.addCleanup(reg.stop)

    def calls(self):
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_text_with_shell_characters_arrives_as_one_argument(self):
        text = 'check "EH-023" & echo pwned | more; $(whoami) %PATH%'
        out = relay.send("claude:c-1", text, "review-only", "k1")
        self.assertEqual(out["id"], "m_fake")
        register, send = self.calls()
        self.assertEqual(register[:3], ["register", "app", "ethan"])
        self.assertEqual(send[-1], text)

    def test_refusal_text_comes_back_without_the_prefix(self):
        with self.assertRaisesRegex(relay.RelayError, "^duplicate: this exact request"):
            relay.send("claude:c-1", "refuse this", "review-only", "k2")

    def test_no_bridge_configured(self):
        with mock.patch.dict(os.environ, {"ETHAN_BRIDGE_DIR": ""}):
            with self.assertRaisesRegex(relay.RelayError, "ETHAN_BRIDGE_DIR"):
                relay.send("claude:c-1", "hi", "review-only", "k3")


if __name__ == "__main__":
    unittest.main()
