"""Coordination continuity in the canonical ledger, with no source ingestion or agent run."""
import json
import os
import tempfile
import unittest
from unittest import mock

from ethan import context, kb, store


class Coordination(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(os.environ, {"ETHAN_STATE_DIR": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db_patch = mock.patch.object(store, "_DB", None)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(lambda: store._DB.close() if store._DB else None)
        self.project = os.path.join(self.tmp.name, "project")

    def put(self, **changes):
        values = dict(chat_id="console", project=self.project, privacy="work", kind="goal", name="release",
                      summary="Finish the current review", source="docs/plan.md#release", owner="person", door="console")
        values.update(changes)
        return context.set_record(**values)

    def test_restart_preserves_goal_constraint_owner_and_source_without_dispatch(self):
        self.put()
        self.put(kind="constraint", name="publish", summary="Do not publish", source="decision:review-1")
        self.put(kind="next_step", name="next", summary="Request independent review", source="task:7")
        with store._LOCK:
            path = store.db().execute("PRAGMA database_list").fetchone()[2]
            self.assertEqual(os.path.basename(path), "ethan.db")
            store._DB.close()
            store._DB = None
        with mock.patch.object(kb, "search", side_effect=AssertionError("source retrieval is agent-owned")), \
                mock.patch.object(kb, "ingest", side_effect=AssertionError("no ingestion")):
            rows = context.records("console", self.project, "work")
        self.assertEqual([r["kind"] for r in rows], ["goal", "constraint", "next_step"])
        self.assertEqual(rows[0]["source"], "docs/plan.md#release")
        self.assertEqual(rows[0]["owner"], "person")
        self.assertEqual(store.pending(), [])
        self.assertEqual(store.open_relays(), [])

    def test_task_results_and_interruption_stay_authoritative_on_restart(self):
        self.put(kind="next_step", name="continue", summary="Ask before continuing interrupted work", source="task:1")
        done = store.add_task("console", "review", "chosen", "codex", "Review result", "console")
        store.finish_task(done, "done", "Reviewed; source docs/result.md")
        interrupted = store.add_task("console", "build", "chosen", "claude", "Unfinished patch", "console")
        with store._LOCK:
            store._DB.close()
            store._DB = None
        self.assertEqual(store.reap_orphans(), 1)
        self.assertEqual(store.task(done)["result"], "Reviewed; source docs/result.md")
        self.assertEqual(store.task(interrupted)["state"], "interrupted")
        self.assertEqual(store.pending(), [])
        self.assertEqual(context.records("console", self.project, "work")[0]["kind"], "next_step")

    def test_relative_project_and_control_characters_are_refused(self):
        with self.assertRaises(ValueError):
            self.put(project="relative-project")
        with self.assertRaises(ValueError):
            self.put(summary="one\rtwo")

    def test_updates_preserve_audit_and_only_one_current_value(self):
        self.put()
        self.put(summary="Review completed", source="task:12/result")
        rows = context.records("console", self.project, "work")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["summary"], "Review completed")
        with store._LOCK:
            self.assertEqual(store.db().execute("SELECT state FROM coordination ORDER BY id").fetchall(),
                             [("superseded",), ("current",)])

    def test_chat_project_and_privacy_never_mix(self):
        self.put()
        self.assertEqual(context.records("other", self.project, "work"), [])
        self.assertEqual(context.records("console", self.project + "-other", "work"), [])
        self.assertEqual(context.records("console", self.project, "personal"), [])
        with self.assertRaises(ValueError):
            context.records("console", self.project, "work", "telegram-private")
        with self.assertRaises(ValueError):
            self.put(door="unknown")

    def test_secrets_are_refused_and_do_not_persist(self):
        with self.assertRaises(ValueError):
            self.put(summary="sk-" + "x" * 30)
        with self.assertRaises(ValueError):
            self.put(source="Bearer " + "x" * 30)
        self.assertEqual(context.records("console", self.project, "work"), [])

    def test_brief_is_bounded_coordination_and_never_permission(self):
        self.put(kind="decision", summary="Historical note: approvals used to be disabled")
        with mock.patch.object(kb, "kb_map", return_value={"chosen": {"privacy": "work"}}), \
                mock.patch.object(kb, "search", side_effect=AssertionError("no source retrieval")):
            brief = context.for_brief("console", "chosen", self.project, "console")
            self.assertIn("NEVER authorization", brief)
            self.assertIn("source: docs/plan.md#release", brief)
            self.assertLessEqual(len(brief), 2000)
            self.assertNotIn("Historical note", context.for_brief("console", "chosen", self.project, "telegram-private"))
            self.assertIsNone(context.for_brief("console", None, self.project))

    def test_missing_records_are_reported_without_invention(self):
        with mock.patch.object(kb, "kb_map", return_value={"chosen": {"privacy": "work"}}):
            self.assertIn("No current coordination records", context.for_brief("console", "chosen", self.project))

    def test_rule_requires_explicit_structured_update(self):
        out = []
        self.assertFalse(context.take("console", "remember everything", out.append, "console"))
        self.assertTrue(context.take("console", "coordinate " + json.dumps({"project": self.project,
            "privacy": "work", "kind": "ownership", "name": "review", "summary": "Review patch",
            "source": "task:5", "owner": "reviewer"}), out.append, "console"))
        self.assertIn("starts nothing", out[-1])

    def test_handoff_audit_restarts_without_reexecution_and_scrubs_result(self):
        aid = context.record_handoff("console", "console", "build", {"hand": "codex", "workdir": self.project,
                                                                     "brief": "Review scoped patch"}, task_id=7)
        context.finish_handoff(aid, "interrupted", "sk-" + "x" * 30)
        with store._LOCK:
            row = store.db().execute("SELECT action,executor,task_id,state,result FROM handoff_audit WHERE id=?", (aid,)).fetchone()
        self.assertEqual(row[:4], ("build", "codex", 7, "interrupted"))
        self.assertNotIn("sk-", row[4])
        context.finish_handoff(aid, "completed", "late result")
        with store._LOCK:
            self.assertEqual(store.db().execute("SELECT state FROM handoff_audit WHERE id=?", (aid,)).fetchone()[0], "interrupted")


if __name__ == "__main__":
    unittest.main()
