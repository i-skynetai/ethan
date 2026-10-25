"""Dynamic display preferences cannot become executable widgets or action permissions."""
import copy
import os
import tempfile
import threading
import unittest
from unittest import mock

from ethan import layouts, store


class Layouts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"ETHAN_STATE_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(store, "_DB", None)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: store._DB.close() if store._DB else None)

    def without_tasks(self):
        layout = layouts.default()
        layout["widgets"] = [w for w in layout["widgets"] if w["id"] != "tasks"]
        return layout

    def test_preview_does_not_change_layout_and_apply_persists_restart(self):
        before = layouts.current()
        p = layouts.preview(self.without_tasks())
        self.assertEqual(layouts.current(), before)
        result = layouts.apply_preview(p["preview_id"])
        self.assertEqual(result["revision"], 1)
        store._DB.close()
        store._DB = None
        self.assertEqual(layouts.current(), result)
        self.assertEqual(store.pending(), [])
        self.assertEqual(store.open_relays(), [])

    def test_schema_refuses_executable_unknown_or_unbounded_configuration(self):
        bad = []
        x = layouts.default(); x["widgets"][0]["url"] = "https://evil.example"; bad.append(x)
        x = layouts.default(); x["widgets"][0]["type"] = "custom-script"; bad.append(x)
        x = layouts.default(); x["widgets"][0]["title"] = "<script>run()</script>"; bad.append(x)
        x = layouts.default(); x["widgets"][0]["title"] = "x" * 65; bad.append(x)
        x = layouts.default(); x["widgets"][0]["width"] = True; bad.append(x)
        x = layouts.default(); x["version"] = True; bad.append(x)
        x = layouts.default(); x["widgets"][0]["id"] = "arbitrary-id"; bad.append(x)
        x = layouts.default(); x["widgets"].append(copy.deepcopy(x["widgets"][0])); bad.append(x)
        for x in bad:
            with self.subTest(layout=x), self.assertRaises(layouts.LayoutError):
                layouts.preview(x)
        self.assertEqual(layouts.current()["revision"], 0)

    def test_core_and_conversation_are_mandatory_fixed_cards(self):
        for kind in ("core", "conversation"):
            x = layouts.default()
            x["widgets"] = [w for w in x["widgets"] if w["type"] != kind]
            with self.assertRaises(layouts.LayoutError):
                layouts.validate(x)
            x = layouts.default()
            next(w for w in x["widgets"] if w["type"] == kind)["title"] = "Changed"
            with self.assertRaises(layouts.LayoutError):
                layouts.validate(x)

    def test_add_order_resize_and_configure_registered_cards(self):
        x = self.without_tasks()
        x["widgets"].append(next(w for w in layouts.default()["widgets"] if w["id"] == "tasks"))
        task = x["widgets"][-1]
        task.update(width=2, title="My current tasks")
        result = layouts.apply(x, 0)
        self.assertEqual(result["layout"]["widgets"][-1], task)
        self.assertEqual(result["revision"], 1)

    def test_wrong_chat_door_expiry_and_replay_never_apply(self):
        p = layouts.preview(self.without_tasks(), "chat-one", "console")
        for chat, door in (("chat-two", "console"), ("chat-one", "cli")):
            with self.assertRaises(layouts.LayoutError):
                layouts.apply_preview(p["preview_id"], chat, door)
        with mock.patch.object(layouts.time, "time", return_value=p["expires"] + 1):
            with self.assertRaises(layouts.LayoutError):
                layouts.apply_preview(p["preview_id"], "chat-one", "console")
        self.assertEqual(layouts.current()["revision"], 0)
        layouts.apply_preview(p["preview_id"], "chat-one", "console")
        with self.assertRaises(layouts.LayoutError):
            layouts.apply_preview(p["preview_id"], "chat-one", "console")

    def test_stale_revision_and_bool_revision_are_refused(self):
        p = layouts.preview(self.without_tasks())
        layouts.apply(layouts.default(), 0)
        with self.assertRaises(layouts.LayoutError):
            layouts.apply_preview(p["preview_id"])
        for revision in (True, False, -1, "1"):
            with self.assertRaises(layouts.LayoutError):
                layouts.apply(layouts.default(), revision)

    def test_rollback_is_new_revision_and_invalid_previous_cannot_be_used(self):
        layouts.apply(self.without_tasks(), 0)
        result = layouts.rollback(1)
        self.assertEqual(result["revision"], 2)
        self.assertEqual(result["layout"], layouts.default())
        with self.assertRaises(layouts.LayoutError):
            layouts.rollback(1)
        with store._LOCK:
            store.db().execute("UPDATE hud_layouts SET layout='{}' WHERE revision=1")
            store.db().commit()
        with self.assertRaises(layouts.LayoutError):
            layouts.rollback(2)
        self.assertEqual(layouts.current()["revision"], 2)

    def test_corrupt_stored_layout_falls_back_without_executing_unknown_widget(self):
        layouts.current()
        with store._LOCK:
            store.db().execute("UPDATE hud_layouts SET layout='not JSON' WHERE revision=0")
            store.db().commit()
        self.assertTrue(layouts.current()["recovered"])
        self.assertEqual(layouts.current()["layout"], layouts.default())

    def test_rules_preview_only_then_require_exact_explicit_apply(self):
        for text in ("hide tasks", "show activity", "move agents before tasks", "reset dashboard"):
            out = []
            self.assertTrue(layouts.take("console", text, out.append, "console"))
            self.assertIn("Nothing changed", out[0])
            self.assertEqual(layouts.current()["revision"], 0)
        p = layouts.preview(self.without_tasks())
        out = []
        self.assertTrue(layouts.take("console", "apply dashboard " + p["preview_id"], out.append, "console"))
        self.assertEqual(layouts.current()["revision"], 1)
        out = []
        layouts.take("console", "hide core", out.append, "console")
        self.assertIn("refused", out[0])

    def test_concurrent_apply_one_revision_has_exactly_one_winner(self):
        result = []
        def worker():
            try:
                layouts.apply(self.without_tasks(), 0)
                result.append("applied")
            except layouts.LayoutError:
                result.append("stale")
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertCountEqual(result, ["applied", "stale"])
        self.assertEqual(layouts.current()["revision"], 1)


if __name__ == "__main__":
    unittest.main()
