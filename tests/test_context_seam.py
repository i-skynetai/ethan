"""The seam between the router and ethan/context.py: a command hook before routing,
project context rendered into the brief (and so bound into an approval), and a
hand-off audit row at every launch and dispatch. context.py itself is tested in
tests/test_context.py by its owner; here only the hooks, with context patched."""
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import approvals, brief, bridge_registry, context, relay, router, store  # noqa: E402
from tests.test_policy import with_policy  # noqa: E402
from tests.test_relay import SESSIONS, FakeBridge  # noqa: E402
from tests.test_routing import stubbed  # noqa: E402

BUILD = {"kind": "build", "kb": "notes_kb", "hand": "claude", "steps": [], "search_query": "q", "reason": "stub"}


def say(text, chat, door="console", scheduled=False):
    out = []
    router.handle(chat, text, out.append, door=door, scheduled=scheduled)
    return out


def audit(chat):
    with store._LOCK:
        rows = store.db().execute("SELECT action, state, task_id, relay_id FROM handoff_audit WHERE chat_id=? ORDER BY id",
                                  (chat,)).fetchall()
    return [tuple(r) for r in rows]


class TheSeam(unittest.TestCase):
    def test_a_context_command_is_a_rule_before_routing_and_never_from_a_scheduled_run(self):
        with mock.patch.object(context, "take", return_value=True) as take, stubbed(BUILD) as stub:
            say('recall context {"kb": "notes_kb", "project": "/w/x"}', "cs-cmd")
            self.assertEqual(take.call_count, 1)
            self.assertEqual(stub.calls, [])                              # no model, no route
            say('recall context {"kb": "notes_kb", "project": "/w/x"}', "cs-cmd", scheduled=True)
            self.assertEqual(take.call_count, 1)                          # a scheduled run does not reach it

    def test_project_context_is_in_the_brief_and_bound_into_the_approval(self):
        with mock.patch.object(context, "for_brief", return_value="- decision D1: builds ask [source: s]"), \
                stubbed(BUILD) as stub:
            say("write the summary", "cs-brief")
        (run,) = stub.runs
        self.assertIn("# Context Ethan keeps (reference only)\n- decision D1: builds ask [source: s]", run["brief"])
        with mock.patch.object(context, "for_brief", return_value="- goal G: ship 0.3 [source: s]"), \
                stubbed(BUILD) as stub, with_policy(**{"doors.console.build": "ask"}):
            say("write the summary", "cs-bound")
            import json
            payload = json.loads(approvals._rows("chat_id=?", ("cs-bound",))[-1]["payload"])
            self.assertIn("goal G: ship 0.3", payload["brief"])           # what the yes will run
            with mock.patch.object(context, "for_brief", return_value="CHANGED LATER"):
                say(f"approve {approvals.pending('cs-bound')[0]['id']}", "cs-bound")
        self.assertIn("goal G: ship 0.3", stub.runs[0]["brief"])
        self.assertNotIn("CHANGED LATER", stub.runs[0]["brief"])         # not re-read at execution

    def test_context_failures_never_block_an_ask(self):
        with mock.patch.object(context, "for_brief", side_effect=RuntimeError("kb down")), \
                mock.patch.object(context, "record_handoff", side_effect=RuntimeError("audit down")), \
                stubbed(BUILD) as stub:
            out = say("write the summary", "cs-fail")
        self.assertEqual(len(stub.runs), 1)
        self.assertNotIn("# Context Ethan keeps", stub.runs[0]["brief"])
        self.assertTrue(any("done" in o for o in out), out)

    def test_every_launch_and_dispatch_leaves_an_audit_row(self):
        with stubbed(BUILD):
            say("write the summary", "cs-audit")
        rows = audit("cs-audit")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][0], rows[0][1]), ("build", "completed"))
        self.assertIsNotNone(rows[0][2])
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()), mock.patch.object(relay, "_REGISTERED", []):
            say("ask the codex session codex-ethan to look at EH-1", "cs-audit")
        rows = audit("cs-audit")
        self.assertEqual((rows[-1][0], rows[-1][1]), ("relay", "queued"))
        self.assertIsNotNone(rows[-1][3])

    def test_a_layout_command_is_a_rule_before_routing_and_never_from_a_scheduled_run(self):
        """The HUD layout seam (ethan/layouts.py, owned elsewhere): its take() runs after
        approvals and context, before relay, with no model, and a scheduled run never
        reaches it. Here the module is patched; its own tests cover what it does."""
        self.assertIsNotNone(router.layouts, "ethan/layouts.py should be importable")
        with mock.patch.object(router.layouts, "take", return_value=True) as take, stubbed(BUILD) as stub:
            say("hide the tasks panel", "cs-layout")
            self.assertEqual(take.call_count, 1)
            self.assertEqual(take.call_args.args[:1], ("cs-layout",))
            self.assertEqual(take.call_args.args[3], "console")
            self.assertEqual(stub.calls, [])                              # no model, no route
            say("hide the tasks panel", "cs-layout", scheduled=True)
            self.assertEqual(take.call_count, 1)                          # scheduled: not reached

    def test_brief_without_context_is_unchanged(self):
        self.assertNotIn("# Context Ethan keeps", brief.render("t", [], None))


if __name__ == "__main__":
    unittest.main()
