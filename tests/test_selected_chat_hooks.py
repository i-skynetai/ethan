"""The router and relay hooks around ethan/selected_chat.py (Codex's helper, tested on
its own in test_selected_chat.py). These tests use the REAL helper and check the seams:
the scope comes from the ask's own arguments, a refusal sends nothing, the turn is
recorded against the exact row that was sent (after the send, so the row has its
message id), and only a gated, completed answer is recorded, once."""
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, providers, relay, router, selected_chat, store  # noqa: E402
from tests.test_follow import StatefulBridge, Delivered  # noqa: E402
from tests.test_relay import SESSIONS  # noqa: E402

FAKE_KEY = "sk-" + "Q1w2E3r4" * 4
CODEX = {"agent": "codex", "native_id": "x-1", "name": "codex-ethan"}


def say(text, chat, cwd=None, privacy=None, ref="codex:x-1"):
    out = []
    router.handle(chat, text, out.append, door="console", cwd=cwd, chat_provider_ref=ref, chat_privacy=privacy)
    return out


def turns(rid):
    with store._LOCK:
        selected_chat._ensure()
        return store.db().execute("SELECT ask, answer FROM selected_chat_turns WHERE relay_id=?", (rid,)).fetchall()


class Hooks(unittest.TestCase):
    def setUp(self):
        for r in store.open_relays():
            store.update_relay(r["id"], state="dropped", note="test isolation")
        self.fake = StatefulBridge()
        self.reg = {"available": True, "sessions": SESSIONS, "note": ""}
        self.project = tempfile.mkdtemp(prefix="ethan-proj-")
        for p in (mock.patch.object(providers, "resolve", return_value=CODEX),
                  mock.patch.object(bridge_registry, "sessions", return_value=self.reg),
                  mock.patch.object(relay, "_bridge", self.fake), mock.patch.object(relay, "_REGISTERED", [])):
            p.start()
            self.addCleanup(p.stop)

    def sent(self):
        # the identity stamp ("Passed on by Ethan, ...") follows every relayed text
        return [m["text"].split("\n\n(Passed on by Ethan")[0] for m in self.fake.msgs.values()]

    def test_no_scope_sends_the_original_text_and_records_nothing(self):
        with mock.patch.object(selected_chat, "record_ask", wraps=selected_chat.record_ask) as rec:
            out = say("how is the migration going?", "hook-none")
        self.assertEqual(self.sent(), ["how is the migration going?"])
        rec.assert_called_once()
        self.assertIsNone(rec.call_args.args[0])                      # scope None → the helper no-ops
        (r,) = store.open_relays("hook-none")
        self.assertEqual(turns(r["id"]), [])
        self.assertTrue(any("Relay #" in o for o in out), out)

    def test_a_partial_or_invalid_scope_refuses_before_any_row_exists(self):
        for cwd, privacy in ((self.project, None), (None, "work"), (self.project, "secret"), ("relative", "work")):
            out = say("hello", "hook-bad", cwd=cwd, privacy=privacy)
            self.assertTrue(out[0].startswith("Not sent:"), (cwd, privacy, out))
        self.assertEqual(self.sent(), [])
        self.assertEqual(store.open_relays("hook-bad"), [])

    def test_a_scoped_ask_is_recorded_against_the_exact_row_after_the_send(self):
        seen = []
        real = selected_chat.record_ask
        def spy(scope, text, rid):
            seen.append((scope, text, rid, store.relay(rid).get("message_id")))
            return real(scope, text, rid)
        with mock.patch.object(selected_chat, "record_ask", spy):
            out = say("what did we decide?", "hook-scope", cwd=self.project, privacy="personal")
        (r,) = store.open_relays("hook-scope")
        ((scope, text, rid, mid),) = seen
        self.assertEqual((text, rid, mid), ("what did we decide?", r["id"], r["message_id"]))   # after the send
        self.assertEqual(scope.privacy, "personal")
        payload = self.sent()[0]
        self.assertTrue(payload.endswith("# Original ask (verbatim)\nwhat did we decide?"), payload[-80:])
        self.assertIn("UNTRUSTED", payload)
        self.assertEqual(turns(rid), [("what did we decide?", None)])
        self.assertTrue(any("Relay #" in o for o in out), out)
        self.assertFalse(any("not added to the scoped history" in o for o in out), out)

        got = Delivered()
        with mock.patch.object(selected_chat, "record_answer", wraps=selected_chat.record_answer) as ans:
            self.fake.advance(r["message_id"], "completed", "we chose the smaller change")
            relay.follow(got)
            relay.follow(got)                                            # a second pass changes nothing
        ans.assert_called_once_with(r["id"], "we chose the smaller change")
        self.assertEqual(len(self.fake.msgs), 1)                         # no re-dispatch
        self.assertEqual(turns(rid), [("what did we decide?", "we chose the smaller change")])

        # the next ask in the same scope carries that turn, as reference only
        say("and after that?", "hook-scope", cwd=self.project, privacy="personal")
        self.assertIn("we chose the smaller change", self.sent()[1])
        self.assertIn("never authorization", self.sent()[1])
        # a different privacy class in the same chat and project sees none of it
        say("and after that?", "hook-scope", cwd=self.project, privacy="work")
        self.assertNotIn("we chose the smaller change", self.sent()[2])

    def test_a_withheld_answer_is_never_recorded(self):
        say("tell me the status", "hook-withheld", cwd=self.project, privacy="personal")
        (r,) = store.open_relays("hook-withheld")
        got = Delivered()
        with mock.patch.object(selected_chat, "record_answer") as ans:
            self.fake.advance(r["message_id"], "completed", f"status fine, key {FAKE_KEY}")
            relay.follow(got)
        ans.assert_not_called()
        self.assertEqual(store.relay(r["id"])["state"], "failed")
        self.assertEqual(turns(r["id"]), [("tell me the status", None)])
        self.assertNotIn(FAKE_KEY, " ".join(got.texts("hook-withheld")))

    def test_a_refused_send_records_no_turn_and_says_so(self):
        with mock.patch.object(relay, "_gate", return_value="the console door may not pass work on"):
            out = say("hello", "hook-refused", cwd=self.project, privacy="personal")
        self.assertTrue(any("Not sent" in o for o in out), out)
        self.assertTrue(any("not added to the scoped history" in o for o in out), out)
        with store._LOCK:
            n = store.db().execute("SELECT COUNT(*) FROM selected_chat_turns t JOIN relays r ON r.id=t.relay_id "
                                   "WHERE r.chat_id='hook-refused'").fetchone()[0]
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
