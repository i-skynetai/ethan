"""An ask that carries a recognised credential is refused before anything is stored,
routed or sent — and the selected-session chat route goes through the same gates.

Detection is ethan/redact.py's recognised patterns and nothing wider; these tests use a
fake key in one of those shapes. They do not claim universal secret detection."""
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import approvals, bridge_registry, context, hands, llm, providers, redact, relay, router, store  # noqa: E402
from tests.test_relay import SESSIONS, FakeBridge  # noqa: E402

FAKE_KEY = "sk-" + "A1b2C3d4" * 4                 # the shape of an OpenAI key; not a real one


def messages_with(fragment):
    with store._LOCK:
        rows = store.db().execute("SELECT text FROM messages WHERE text LIKE ?", (f"%{fragment}%",)).fetchall()
    return [r[0] for r in rows]


def say(text, chat, door="console", scheduled=False, ref=None):
    out = []
    router.handle(chat, text, out.append, door=door, scheduled=scheduled, chat_provider_ref=ref)
    return out


class CredentialIngress(unittest.TestCase):
    def setUp(self):
        self.assertEqual(redact.find(FAKE_KEY), ["openai-key"])      # the fixture is a recognised shape
        self.patches = [mock.patch.object(llm, "ask", side_effect=AssertionError("the model saw a credential")),
                        mock.patch.object(hands, "run", side_effect=AssertionError("a hand saw a credential")),
                        mock.patch.object(context, "take", side_effect=AssertionError("context saw a credential")),
                        mock.patch.object(relay, "_bridge", side_effect=AssertionError("the bridge saw a credential"))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_an_ordinary_ask_with_a_key_is_refused_and_nothing_is_stored(self):
        before = (len(approvals._rows()), len(store.recent_relays(500)), len(store.recent_tasks(500)))
        out = say(f"use {FAKE_KEY} to review the billing repo", "sec-ask")
        self.assertIn("Refused", out[0])
        self.assertIn("openai-key", out[0])
        self.assertNotIn(FAKE_KEY, " ".join(out))                     # never echoed
        self.assertEqual(messages_with(FAKE_KEY[:12]), [])              # never stored
        self.assertEqual(store.recent("sec-ask"), [])
        self.assertEqual((len(approvals._rows()), len(store.recent_relays(500)), len(store.recent_tasks(500))), before)
        self.assertTrue(out[-1].startswith("Session can close"))

    def test_a_coordinate_command_with_a_key_is_refused_before_context_sees_it(self):
        out = say('coordinate {"kb": "notes_kb", "project": "/w/x", "note": "' + FAKE_KEY + '"}', "sec-coord")
        self.assertIn("Refused", out[0])
        self.assertEqual(messages_with(FAKE_KEY[:12]), [])

    def test_the_scheduled_path_is_refused_too(self):
        out = say(f"remind me to rotate {FAKE_KEY}", "sec-sched", scheduled=True)
        self.assertIn("Refused", out[0])
        self.assertEqual(messages_with(FAKE_KEY[:12]), [])

    def test_a_clean_command_still_works(self):
        with mock.patch.object(context, "take", return_value=True) as take:
            out = say('coordinate {"kb": "notes_kb", "project": "/w/x", "goal": "ship 0.3"}', "sec-clean")
        self.assertEqual(take.call_count, 1)
        self.assertFalse(any(o.startswith("Refused") for o in out))


class SelectedSessionChat(unittest.TestCase):
    def setUp(self):
        for r in store.open_relays():
            store.update_relay(r["id"], state="dropped", note="test isolation")
        self.reg = {"available": True, "sessions": SESSIONS, "note": ""}
        self.codex = {"agent": "codex", "native_id": "x-1", "name": "codex-ethan"}

    def test_ordinary_conversation_goes_to_the_selected_session_review_only_with_no_model(self):
        with mock.patch.object(llm, "ask", side_effect=AssertionError("no model for a selected session")), \
                mock.patch.object(hands, "run", side_effect=AssertionError("no hand")), \
                mock.patch.object(providers, "resolve", return_value=self.codex), \
                mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            out = say("how is the migration going?", "sel-chat", ref="codex:x-1")
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--to") + 1], "codex:x-1")
        self.assertEqual(send[send.index("--mode") + 1], "review-only")
        self.assertIn("how is the migration going?", send[-1])
        self.assertTrue(any("Relay #" in o for o in out), out)

    def test_rules_still_win_first(self):
        with mock.patch.object(providers, "resolve", return_value=self.codex), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake:
            out = say("my tasks", "sel-rule", ref="codex:x-1")
        self.assertEqual(fake.sends(), [])
        self.assertTrue(any("open" in o or "list is empty" in o for o in out), out)

    def test_an_invalid_selection_refuses_with_no_fallback(self):
        with mock.patch.object(providers, "resolve", side_effect=providers.SelectionError("not registered")), \
                mock.patch.object(llm, "ask", side_effect=AssertionError("no fallback to the model")), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake:
            out = say("hello there", "sel-bad", ref="codex:nobody")
        self.assertIn("No session selected", out[0])
        self.assertEqual(fake.sends(), [])

    def test_a_scheduled_run_cannot_use_a_selection_and_a_door_without_relay_rights_is_refused(self):
        with mock.patch.object(providers, "resolve", return_value=self.codex), \
                mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            out = say("hello there", "sel-sched", ref="codex:x-1", scheduled=True)
            self.assertIn("scheduled run cannot", out[0])
            out = say("hello there", "sel-tg", ref="codex:x-1", door="telegram-private")
            self.assertIn("telegram-private door may not pass work", out[0])
        self.assertEqual(fake.sends(), [])


if __name__ == "__main__":
    unittest.main()
