"""EH-023: a status ask is answered from the ledger, with no model call beyond routing."""
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import door_console, relay, router, status, store  # noqa: E402
from tests.test_routing import stubbed  # noqa: E402

ROUTE = {"kind": "status", "kb": "none", "hand": "none", "steps": [], "search_query": "", "reason": "status"}


def seed():
    for r in store.open_relays():
        store.update_relay(r["id"], state="dropped", note="test isolation")
    running = store.add_task("s", "build", "notes_kb", "claude", "write the release notes", "console")
    done = store.add_task("s", "review", "notes_kb", "codex", "review the README", "console")
    store.finish_task(done, "done", "two findings")
    rid = store.add_relay("s", "console", "ask the codex session to check CI", "review-only")
    store.update_relay(rid, state="queued", target="codex:codex-ethan", message_id="m_x")
    return running, done, rid


class StatusFromTheLedger(unittest.TestCase):
    def test_what_is_running_lists_tasks_and_relays_with_one_model_call(self):
        running, done, rid = seed()
        with stubbed(ROUTE) as stub, mock.patch.object(relay, "bridge_dir", return_value=None):
            out = []
            router.handle("status-1", "what is running?", out.append, door="console")
        self.assertEqual(len(stub.calls), 1)                 # routing only
        self.assertEqual(stub.runs, [])
        text = out[0]
        self.assertIn(f"#{running} build/claude", text)
        self.assertIn(f"relay #{rid} to codex:codex-ethan — queued", text)
        self.assertIn(f"#{done} done review/codex", text)

    def test_the_console_shortcut_gives_the_same_answer_without_any_model(self):
        seed()
        with mock.patch.object(router, "handle") as route, \
                mock.patch.object(relay, "bridge_dir", return_value=None), \
                mock.patch.object(door_console.store, "add_reply") as reply:
            door_console._ask("status", chat="status-2")
        route.assert_not_called()
        self.assertEqual(reply.call_args.args[1], status.text())

    def test_updates_asks_are_declined_honestly(self):
        route = dict(ROUTE, kind="updates")
        with stubbed(route) as stub:
            out = []
            router.handle("status-3", "any new mail?", out.append, door="console")
        self.assertIn("do not read mail", out[0])
        self.assertEqual(stub.runs, [])

    def test_quiet_when_nothing_is_happening(self):
        for t in store.pending():
            store.finish_task(t["id"], "done", "")
        for r in store.open_relays():
            store.update_relay(r["id"], state="dropped")
        with mock.patch.object(relay, "bridge_dir", return_value=None):
            self.assertTrue(status.text().startswith("Nothing is running."))


if __name__ == "__main__":
    unittest.main()
