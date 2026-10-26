"""Canonical event lifecycle fixtures only; no provider, API or bridge sends."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ethan import conversation_events as ce, redact, store

ID = "a"*32
REF = "claude:fixture-session"


class RequestEvents(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"ETHAN_STATE_DIR": str(Path(temp.name)/"state"), "PYTHONUTF8": "1"})
        env.start()
        self.addCleanup(env.stop)
        db = patch.object(store, "_DB", None)
        db.start()
        self.addCleanup(db.stop)
        self.addCleanup(lambda: store._DB.close() if store._DB else None)

    def make(self, rid=ID, text="original unique request", provider=None):
        return ce.create(rid, "console", "console", {"text": text, "chat_provider_ref": provider})

    def read(self, rid=ID, after=0, limit=100):
        return ce.events(rid, "console", "console", after, limit)

    def relay(self):
        rid = store.add_relay("console", "console", "fixture payload", "review-only", purpose="chat")
        store.update_relay(rid, target_ref=REF, target="fixture", message_id=f"fixture-{rid}", state="queued")
        return rid

    def test_identity_digest_normalization_and_no_raw_ask(self):
        first = self.make()
        self.assertTrue(first["created"])
        self.assertFalse(ce.create(ID, "console", "console", text="original unique request")["created"])
        self.assertFalse(ce.create(ID, "console", "console", "original unique request")["created"])
        with self.assertRaises(ce.Conflict):
            self.make(text="different request")
        self.assertNotIn("original unique request", "\n".join(store.db().iterdump()))
        caps = first["request"]["capabilities"]
        self.assertFalse(caps["live_text_deltas"])
        self.assertEqual(caps["text_delivery"], "whole_answer_guarded_final")

    def test_secret_and_unknown_input_refused_before_persistence(self):
        secret = "sk-" + "FAKEEVENTONLY"*3
        self.assertTrue(redact.find(secret))
        for inputs in ({"text": secret}, {"text": "hi", "token": "not accepted"},
                       {"text": "hi", "chat_privacy": "unknown"}):
            with self.assertRaises(ValueError):
                ce.create(ID, "console", "console", inputs)
        with store._LOCK:
            self.assertEqual(ce._ensure().execute("SELECT COUNT(*) FROM conversation_requests").fetchone()[0], 0)

    def test_one_claim_winner_and_scope_isolation(self):
        self.make()
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(lambda _: ce.claim(ID), range(8))).count(True), 1)
        for chat, door in (("other", "console"), ("console", "cli")):
            with self.assertRaises(ce.NotFound):
                ce.events(ID, chat, door)
            with self.assertRaises(ce.NotFound):
                ce.cancel(ID, chat, door)

    def test_sequence_cursor_pagination_and_replay_never_claims(self):
        self.make()
        self.assertTrue(ce.start(ID))
        self.assertTrue(ce.record_reply(ID, "real completed reply"))
        ce.finish(ID)
        first = self.read(limit=2)
        rest = self.read(after=first["after"])
        events = first["events"]+rest["events"]
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events)+1)))
        self.assertEqual(self.read()["request"]["state"], "completed")
        self.assertFalse(ce.start(ID))
        self.assertEqual(self.read(after=rest["after"])["events"], [])
        self.assertEqual(store.recent_relays(), [])
        for after, limit in ((True, 1), (-1, 1), (999, 1), (0, 101), (0, False)):
            with self.assertRaises(ce.RequestError):
                self.read(after=after, limit=limit)

    def test_cancel_before_start_and_late_reply_cannot_revive(self):
        self.make()
        self.assertEqual(ce.cancel(ID, "console", "console")["state"], "cancelled")
        self.assertFalse(ce.claim(ID))
        before = self.read()
        self.assertFalse(ce.record_reply(ID, "late reply must not appear"))
        ce.fail(ID, "late failure")
        ce.finish(ID)
        self.assertEqual(self.read(), before)

    def test_concurrent_cancel_and_finish_has_one_terminal_decision(self):
        self.make()
        ce.claim(ID)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ce.cancel, ID, "console", "console"), pool.submit(ce.finish, ID)]
            for future in futures:
                future.result()
        result = self.read()
        self.assertIn(result["request"]["state"], ("cancelled", "completed"))
        terminal = [e for e in result["events"] if e["kind"] == "cancelled" or e["text"] == "Request processing completed."]
        self.assertEqual(len(terminal), 1)

    def test_waiting_relay_and_gated_answer_once(self):
        self.make(provider=REF)
        ce.claim(ID)
        rid = self.relay()
        self.assertTrue(ce.bind_relay(ID, rid))
        self.assertFalse(ce.bind_relay(ID, rid))
        self.assertEqual(ce.finish(ID)["state"], "waiting")
        store.update_relay(rid, state="completed", result="actual canonical answer")
        self.assertTrue(ce.finish_relay(rid, "completed", "actual canonical answer"))
        before = self.read()
        self.assertFalse(ce.finish_relay(rid, "completed", "actual canonical answer"))
        self.assertEqual(self.read(), before)
        self.assertEqual(before["request"]["state"], "completed")
        self.assertEqual([e["text"] for e in before["events"] if e["kind"] == "final"], ["actual canonical answer"])

    def test_cancel_waiting_does_not_touch_independent_relay(self):
        self.make(provider=REF)
        ce.claim(ID)
        rid = self.relay()
        ce.bind_relay(ID, rid)
        ce.finish(ID)
        ce.cancel(ID, "console", "console")
        self.assertEqual(store.relay(rid)["state"], "queued")
        store.update_relay(rid, state="completed", result="independent late answer")
        self.assertFalse(ce.finish_relay(rid, "completed", "independent late answer"))
        self.assertEqual(store.relay(rid)["result"], "independent late answer")
        self.assertNotIn("independent late answer", str(self.read()))

    def test_fast_relay_final_before_binding_is_backfilled_exactly_once(self):
        self.make(provider=REF)
        ce.claim(ID)
        rid = self.relay()
        store.update_relay(rid, state="completed", result="fast canonical answer")
        self.assertTrue(ce.bind_relay(ID, rid))
        snapshot = self.read()
        self.assertEqual(snapshot["request"]["state"], "completed")
        self.assertEqual([e["text"] for e in snapshot["events"] if e["kind"] == "final"], ["fast canonical answer"])
        self.assertFalse(ce.bind_relay(ID, rid))
        self.assertFalse(ce.finish_relay(rid, "completed", "fast canonical answer"))
        self.assertEqual(self.read(), snapshot)
        self.assertEqual(len(store.recent_relays()), 1)

    def test_split_secret_is_checked_only_as_whole_reply_not_fake_deltas(self):
        self.make()
        ce.claim(ID)
        fragments = ["sk-", "FAKE", "WHOLEANSWER"*3]
        self.assertFalse(self.read()["request"]["capabilities"]["live_text_deltas"])
        # No fragment publication API is exposed: current adapters finish a whole
        # message before invoking record_reply. Do not claim streaming-prefix safety.
        self.assertFalse(ce.record_reply(ID, "".join(fragments)))
        self.assertNotIn("".join(fragments), "\n".join(store.db().iterdump()))

    def test_reply_credentials_and_bounds_fail_without_raw_event(self):
        secret = "sk-" + "FAKEOUTPUTONLY"*3
        self.make()
        ce.claim(ID)
        self.assertFalse(ce.record_reply(ID, secret))
        result = self.read()
        self.assertEqual(result["request"]["state"], "failed")
        self.assertNotIn(secret, "\n".join(store.db().iterdump()))
        other = "b"*32
        self.make(other)
        ce.claim(other)
        self.assertFalse(ce.record_reply(other, "x"*(ce.MAX_TEXT+1)))
        self.assertEqual(self.read(other)["request"]["state"], "failed")

    def test_event_count_is_bounded_with_terminal_slot_reserved(self):
        self.make()
        ce.claim(ID)
        for _ in range(ce.MAX_EVENTS+5):
            ce.record_reply(ID, "real callback")
        result = self.read()
        self.assertEqual(result["request"]["state"], "failed")
        self.assertLessEqual(result["request"]["after"], ce.MAX_EVENTS)

    def test_recovery_only_old_instance_not_current_open_servers(self):
        self.make()
        other = "b"*32
        self.make(other)
        ce.claim(other)
        self.assertEqual(ce.recover(), 0)
        with patch.object(ce, "_INSTANCE", "another-process-instance"):
            current = "c"*32
            self.make(current)
            self.assertEqual(ce.startup_recover(), 2)
            self.assertEqual(self.read(current)["request"]["state"], "accepted")
        self.assertEqual(self.read()["request"]["state"], "interrupted")
        self.assertFalse(ce.claim(ID))

    def test_fresh_process_replay_does_not_redispatch(self):
        self.make()
        ce.claim(ID)
        ce.record_reply(ID, "persisted completed answer")
        ce.finish(ID)
        store.db().close()
        store._DB = None
        code = ("from ethan import conversation_events as c, store; "
                f"r=c.events({ID!r},'console','console'); "
                "assert r['request']['state']=='completed'; "
                "assert any(e['text']=='persisted completed answer' for e in r['events']); "
                f"assert not c.claim({ID!r}); assert store.recent_relays()==[]; "
                "print('EVENT_REPLAY_OK'); store._DB.close()")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVENT_REPLAY_OK", result.stdout)

    def test_observer_and_active_context_compatibility(self):
        self.make()
        ce.start(ID)
        observer = ce.Observer(ID)
        with ce.active_request(ID):
            self.assertEqual(ce.current_request(), ID)
            self.assertTrue(observer.status("Actual processing stage"))
            self.assertTrue(observer.reply("Safe reply"))
        self.assertIsNone(ce.current_request())
        observer.complete()
        self.assertTrue(observer.cancelled())
        self.assertFalse(observer.reply("late"))
