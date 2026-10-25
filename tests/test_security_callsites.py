"""Where a hand's output or a session's answer enters Ethan — router._launch, the chain
steps, relay._check — it is gated with redact.gate_output before anything stores,
shows, harvests or reads it. redact.gate_output itself is tested by its owner; these
tests use a fake key in a recognised shape and check the call sites."""
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, clock, harvest, redact, relay, router, store, todo, watch  # noqa: E402
from tests.test_follow import StatefulBridge, Delivered  # noqa: E402
from tests.test_relay import SESSIONS  # noqa: E402
from tests.test_routing import stubbed  # noqa: E402

FAKE_KEY = "sk-" + "Z9y8X7w6" * 4
BUILD = {"kind": "build", "kb": "notes_kb", "hand": "claude", "steps": [], "search_query": "q", "reason": "stub"}
CHAIN = {"kind": "chain", "kb": "notes_kb", "hand": "auto", "search_query": "q", "reason": "stub",
         "steps": [{"hand": "claude", "kind": "build", "goal": "write it"},
                   {"hand": "codex", "kind": "review", "goal": "review it"}]}


def say(text, chat):
    out = []
    router.handle(chat, text, out.append, door="console")
    return out


def ledger_has(fragment):
    with store._LOCK:
        d = store.db()
        n = d.execute("SELECT COUNT(*) FROM tasks WHERE result LIKE ?", (f"%{fragment}%",)).fetchone()[0]
        n += d.execute("SELECT COUNT(*) FROM messages WHERE text LIKE ?", (f"%{fragment}%",)).fetchone()[0]
        n += d.execute("SELECT COUNT(*) FROM replies WHERE text LIKE ?", (f"%{fragment}%",)).fetchone()[0]
        n += d.execute("SELECT COUNT(*) FROM relays WHERE result LIKE ?", (f"%{fragment}%",)).fetchone()[0]
    return n


class HandOutput(unittest.TestCase):
    def setUp(self):
        self.assertEqual(redact.find(FAKE_KEY), ["openai-key"])

    def test_a_hands_output_with_a_key_is_withheld_failed_and_not_harvested(self):
        with stubbed(BUILD) as stub, mock.patch.object(harvest, "run") as harvest_run:
            stub.run = lambda *a, **k: {"ok": True, "out": f"done; token {FAKE_KEY} used"}
            from ethan import hands
            hands.run = stub.run
            out = say("write the summary", "out-key")
        self.assertNotIn(FAKE_KEY, " ".join(out))
        self.assertTrue(any("FAILED" in o and "withheld" in o for o in out), out)
        self.assertEqual(ledger_has(FAKE_KEY[:12]), 0)
        harvest_run.assert_not_called()
        task = store.recent_tasks(1)[0]
        self.assertEqual(task["state"], "failed")

    def test_a_chain_stops_at_the_withheld_step(self):
        with stubbed(CHAIN):
            calls = []
            def run(hand, brief, *a, **k):
                calls.append(hand)
                return {"ok": True, "out": f"step output with {FAKE_KEY}" if hand == "claude" else "fine"}
            from ethan import hands
            hands.run = run
            out = say("write it then review it", "out-chain")
        self.assertEqual(calls, ["claude"])                                 # codex never ran
        self.assertTrue(any("Step 1 FAILED" in o for o in out), out)
        self.assertNotIn(FAKE_KEY, " ".join(out))
        self.assertEqual(ledger_has(FAKE_KEY[:12]), 0)

    def test_clean_output_is_unchanged(self):
        with stubbed(BUILD) as stub:
            out = say("write the summary", "out-clean")
        self.assertTrue(any("done" in o for o in out), out)
        self.assertEqual(stub.runs[0]["kind"], "build")


class ModelOutput(unittest.TestCase):
    """What the router's own model says — a chat answer, a plan — is gated too: the
    door never shows a credential, and a plan carrying one never becomes work."""

    def test_a_chat_answer_with_a_key_is_withheld_at_the_door(self):
        with stubbed({"kind": "chat", "kb": "", "hand": "none", "steps": [], "search_query": "", "reason": "stub"}) as stub:
            stub.ask = lambda messages, json_schema=None: dict(stub.route) if json_schema else f"sure: {FAKE_KEY}"
            from ethan import llm
            llm.ask = stub.ask
            out = say("hello there", "model-chat")
        self.assertNotIn(FAKE_KEY, " ".join(out))
        self.assertTrue(any("withheld" in o for o in out), out)
        self.assertEqual(ledger_has(FAKE_KEY[:12]), 0)

    def test_an_error_text_with_a_key_is_withheld_at_the_door(self):
        with stubbed(BUILD):
            from ethan import llm
            def boom(*a, **k):
                raise RuntimeError(f"upstream said {FAKE_KEY}")
            llm.ask = boom
            out = say("write the summary", "model-err")
        self.assertNotIn(FAKE_KEY, " ".join(out))
        self.assertTrue(any("withheld" in o for o in out), out)

    def test_a_plan_with_a_key_is_refused_before_log_task_or_approval(self):
        from ethan import approvals
        bad = {**CHAIN, "steps": [{"hand": "claude", "kind": "build", "goal": f"use {FAKE_KEY}"},
                                  {"hand": "codex", "kind": "review", "goal": "review"}]}
        with stubbed(bad, console_build="ask") as stub, mock.patch.object(approvals, "request") as req:
            before = len(store.recent_tasks(50))
            out = say("do the thing and review it", "model-route")
        self.assertEqual(stub.runs, [])                                      # no hand
        req.assert_not_called()                                              # no approval
        self.assertEqual(len(store.recent_tasks(50)), before)                # no task
        self.assertTrue(any("Not routed" in o for o in out), out)
        self.assertNotIn(FAKE_KEY, " ".join(out))
        self.assertEqual(ledger_has(FAKE_KEY[:12]), 0)


class SessionAnswer(unittest.TestCase):
    def setUp(self):
        for r in store.open_relays():
            store.update_relay(r["id"], state="dropped", note="test isolation")
        for r in clock.scheduled():
            clock._set(r["id"], state="cancelled")
        self.reg = {"available": True, "sessions": SESSIONS, "note": ""}

    def test_a_relay_answer_with_a_key_is_withheld_before_store_and_delivery(self):
        fake, got = StatefulBridge(), Delivered()
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", fake), mock.patch.object(relay, "_REGISTERED", []):
            say("ask the codex session codex-ethan to look at EH-1", "ans-key")
            (r,) = store.open_relays("ans-key")
            fake.advance(r["message_id"], "completed", f"looked; the key is {FAKE_KEY}")
            relay.follow(got)
        row = store.relay(r["id"])
        self.assertEqual(row["state"], "failed")
        self.assertIn("withheld", row["result"])
        self.assertNotIn(FAKE_KEY, row["result"])
        self.assertNotIn(FAKE_KEY, " ".join(got.texts("ans-key")))
        self.assertTrue(any("FAILED" in t for t in got.texts("ans-key")), got.texts("ans-key"))
        self.assertEqual(ledger_has(FAKE_KEY[:12]), 0)

    def test_a_watch_answer_with_a_key_makes_no_tasks(self):
        import datetime as dt
        fake, got = StatefulBridge(), Delivered()
        now = dt.datetime(2026, 10, 7, 10, 0).timestamp()
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", fake), mock.patch.object(relay, "_REGISTERED", []), \
                mock.patch.object(watch.time, "time", return_value=now):
            say("watch mail through the claude session ethan every day at 09:00: what must I reply to?", "ans-watch")
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", fake), mock.patch.object(relay, "_REGISTERED", []):
            clock.tick(now=dt.datetime(2026, 10, 8, 9, 0).timestamp(), deliver=got)
            (r,) = store.open_relays("ans-watch")
            before = len(todo.open_tasks(now + 10 ** 6))
            fake.advance(r["message_id"], "completed", f"- Reply to Dana | https://x.example/1 | key {FAKE_KEY} | -")
            relay.follow(got)
        self.assertEqual(len(todo.open_tasks(now + 10 ** 6)), before)        # nothing filed
        self.assertNotIn(FAKE_KEY, " ".join(got.texts("ans-watch")))
        self.assertTrue(any("FAILED" in t for t in got.texts("ans-watch")), got.texts("ans-watch"))


if __name__ == "__main__":
    unittest.main()
