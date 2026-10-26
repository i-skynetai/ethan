"""Scoped continuity with local fixtures only; never contacts an agent."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ethan import context, selected_chat as chat, store

REF = "claude:existing-session"


class ScopedSelectedChat(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name) / "project"
        self.project.mkdir()
        self.other = Path(temp.name) / "other"
        self.other.mkdir()
        env = patch.dict(os.environ, {"ETHAN_STATE_DIR": str(Path(temp.name)/"state"), "PYTHONUTF8": "1"})
        env.start()
        self.addCleanup(env.stop)
        db = patch.object(store, "_DB", None)
        db.start()
        self.addCleanup(db.stop)
        self.addCleanup(lambda: store._DB.close() if store._DB else None)
        self.s = chat.scope("conversation", str(self.project), "personal", "console", REF)

    def turn(self, s, ask="prior original", answer="prior answer"):
        rid = store.add_relay(s.chat, s.door, "composed payload", "review-only", purpose="chat")
        store.update_relay(rid, target_ref=s.provider, target="fixture", message_id=f"fixture-{rid}", state="queued")
        self.assertTrue(chat.record_ask(s, ask, rid))
        if answer is not None:
            store.update_relay(rid, state="completed", result=answer)
            self.assertTrue(chat.record_answer(rid, answer))
        return rid

    def test_absent_scope_current_ask_only_partial_and_invalid_refused(self):
        self.assertIsNone(chat.scope("c", None, None, "console", REF))
        self.assertEqual(chat.compose(None, "  Exact original\nask  "), "  Exact original\nask  ")
        for cwd, privacy in ((None, "personal"), (str(self.project), None),
                             ("relative", "personal"), (str(self.project), "unknown")):
            with self.subTest(cwd=cwd, privacy=privacy), self.assertRaises(chat.ScopeError):
                chat.scope("c", cwd, privacy, "console", REF)

    def test_original_ask_sources_and_reference_labels(self):
        self.turn(self.s)
        aid = context.set_record(self.s.chat, str(self.project), "personal", "goal", "goal",
                                 "Finish fixture review", "docs/plan#fixture", "owner")
        ask = "  My actual question\nkept verbatim  "
        payload = chat.compose(self.s, ask)
        self.assertTrue(payload.endswith("# Original ask (verbatim)\n" + ask))
        for value in ("UNTRUSTED", "never authorization", "prior answer", "docs/plan#fixture", f'"id": {aid}', '"ts":'):
            self.assertIn(value, payload)

    def test_no_legacy_or_cross_scope_history(self):
        store.remember("conversation", "assistant", "LEGACY_UNSCOPED")
        self.turn(self.s, answer="RIGHT_SCOPE")
        variants = [chat.scope("other-chat", str(self.project), "personal", "console", REF),
                    chat.scope("conversation", str(self.other), "personal", "console", REF),
                    chat.scope("conversation", str(self.project), "work", "console", REF),
                    chat.scope("conversation", str(self.project), "personal", "cli", REF),
                    chat.scope("conversation", str(self.project), "personal", "console", "codex:other-session")]
        for n, s in enumerate(variants):
            self.turn(s, answer=f"OTHER_SCOPE_{n}")
        context.set_record(self.s.chat, str(self.other), "personal", "goal", "other",
                           "OTHER_PROJECT_COORDINATION", "docs/other", "owner")
        context.set_record(self.s.chat, str(self.project), "work", "goal", "other",
                           "OTHER_PRIVACY_COORDINATION", "docs/work", "owner")
        context.set_record(self.s.chat, str(self.project), "personal", "goal", "other-door",
                           "OTHER_DOOR_COORDINATION", "docs/cli", "owner", door="cli")
        result = chat.compose(self.s, "next")
        self.assertIn("RIGHT_SCOPE", result)
        self.assertNotIn("OTHER_SCOPE_", result)
        self.assertNotIn("LEGACY_UNSCOPED", result)
        self.assertNotIn("OTHER_PROJECT_COORDINATION", result)
        self.assertNotIn("OTHER_PRIVACY_COORDINATION", result)
        self.assertNotIn("OTHER_DOOR_COORDINATION", result)

    def test_records_are_idempotent_pending_not_reused_and_binding_checked(self):
        rid = self.turn(self.s, answer=None)
        self.assertFalse(chat.record_ask(self.s, "prior original", rid))
        self.assertFalse(chat.record_answer(rid, "not completed"))
        self.assertNotIn("prior original", chat.compose(self.s, "new"))
        store.update_relay(rid, state="completed", result="safe answer")
        self.assertTrue(chat.record_answer(rid, "safe answer"))
        self.assertFalse(chat.record_answer(rid, "different late answer"))
        self.assertNotIn("different late answer", chat.compose(self.s, "new"))
        wrong = chat.scope("wrong", str(self.project), "personal", "console", REF)
        with self.assertRaises(chat.ScopeError):
            chat.record_ask(wrong, "wrong", rid)

    def test_recognized_secret_never_stored_or_included(self):
        secret = "sk-" + "FAKESCOPEDONLY" * 3
        with self.assertRaises(chat.ScopeError):
            chat.compose(self.s, secret)
        rid = self.turn(self.s, answer=None)
        store.update_relay(rid, state="completed", result="safe")
        self.assertFalse(chat.record_answer(rid, secret))
        self.assertNotIn(secret, "\n".join(store.db().iterdump()))

    def test_fast_answer_before_scope_link_is_backfilled_once(self):
        rid = store.add_relay(self.s.chat, self.s.door, "payload", "review-only", purpose="chat")
        store.update_relay(rid, target_ref=REF, message_id="fast-fixture", state="completed", result="FAST_SAFE_ANSWER")
        self.assertTrue(chat.record_ask(self.s, "original", rid))
        self.assertIn("FAST_SAFE_ANSWER", chat.compose(self.s, "next"))
        self.assertFalse(chat.record_answer(rid, "late repeat"))
        self.assertEqual(len(store.recent_relays()), 1)

    def test_corrupt_secret_reference_is_excluded_and_door_policy_rechecked(self):
        secret = "sk-" + "FAKEREADONLY" * 3
        rid = self.turn(self.s)
        with store._LOCK:
            store.db().execute("UPDATE selected_chat_turns SET answer=? WHERE relay_id=?", (secret, rid))
            store.db().commit()
        self.assertNotIn(secret, chat.compose(self.s, "new"))
        with patch.object(context.policy, "may_file", return_value=(False, "revoked")):
            with self.assertRaises(chat.ScopeError):
                chat.compose(self.s, "new")

    def test_budgets_preserve_current_ask_without_truncating(self):
        for _ in range(5):
            self.turn(self.s, ask="a"*2000, answer="b"*2000)
        for n in range(10):
            context.set_record(self.s.chat, str(self.project), "personal", "goal", f"g{n}",
                               "c"*400, "docs/source", "owner")
        ask = "x"*chat.ASK_LIMIT
        payload = chat.compose(self.s, ask)
        self.assertTrue(payload.endswith(ask))
        self.assertLessEqual(len(payload)-len(ask), chat.REFERENCE_LIMIT+len("\n# Original ask (verbatim)\n"))
        with self.assertRaises(chat.ScopeError):
            chat.compose(self.s, ask+"x")

    def test_fresh_process_retains_scoped_answers_without_new_relay(self):
        self.turn(self.s, answer="PERSISTED_SCOPED_ANSWER")
        context.set_record(self.s.chat, str(self.project), "personal", "decision", "choice",
                           "PERSISTED_COORDINATION", "docs/decision", "owner")
        store.db().close()
        store._DB = None
        code = ("import sys; from ethan import selected_chat as c, store; "
                f"s=c.scope('conversation',sys.argv[1],'personal','console',{REF!r}); "
                "before=len(store.recent_relays()); p=c.compose(s,'restart ask'); "
                "assert 'PERSISTED_SCOPED_ANSWER' in p and 'PERSISTED_COORDINATION' in p; "
                "assert len(store.recent_relays())==before==1; print('SCOPED_RESTART_OK'); store._DB.close()")
        run = subprocess.run([sys.executable, "-c", code, str(self.project)], capture_output=True,
                             text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("SCOPED_RESTART_OK", run.stdout)

    def test_restart_routes_one_new_handoff_with_only_scoped_references(self):
        self.turn(self.s, answer="COMPLETED_BEFORE_RESTART")
        context.set_record(self.s.chat, str(self.project), "personal", "next_step", "next",
                           "SCOPED_NEXT_STEP", "docs/next", "owner")
        store.remember(self.s.chat, "assistant", "FORBIDDEN_LEGACY_MESSAGE")
        store.db().close()
        store._DB = None
        code = '''
import sys
from unittest.mock import patch
from ethan import bridge_registry, hands, llm, providers, relay, router, store
from tests.test_follow import StatefulBridge
fake = StatefulBridge()
target = {"agent": "claude", "native_id": "existing-session", "name": "fixture"}
with patch.object(providers, "resolve", return_value=target), \
     patch.object(bridge_registry, "sessions", return_value={"available":True,"sessions":[]}), \
     patch.object(relay, "_bridge", fake), patch.object(relay, "_REGISTERED", []), \
     patch.object(llm, "ask", side_effect=AssertionError("no model")), \
     patch.object(hands, "run", side_effect=AssertionError("no hand")):
    out = []
    router.handle("conversation", "Continue our discussion.", out.append, door="console", cwd=sys.argv[1],
                  chat_provider_ref="claude:existing-session", chat_privacy="personal")
    assert len(fake.sends()) == 1, out
    payload = fake.sends()[0][-1]
    assert "COMPLETED_BEFORE_RESTART" in payload and "SCOPED_NEXT_STEP" in payload
    assert "FORBIDDEN_LEGACY_MESSAGE" not in payload
    assert "UNTRUSTED" in payload and "Original ask (verbatim)" in payload
    relay.follow(deliver=lambda *args: None)
    relay.follow(deliver=lambda *args: None)
    assert len(fake.sends()) == 1
    assert len(store.recent_relays()) == 2
    print("RESTART_HANDOFF_OK")
store._DB.close()
'''
        run = subprocess.run([sys.executable, "-c", code, str(self.project)], capture_output=True,
                             text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertIn("RESTART_HANDOFF_OK", run.stdout)
