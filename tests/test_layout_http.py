"""Independent real HTTP layout API checks; display changes never dispatch agents."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from ethan import door_console, layouts, store


class LayoutHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = door_console.open_server(0)
        cls.port = cls.server.server_address[1]
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(3)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p = mock.patch.dict(os.environ, {"ETHAN_STATE_DIR": temp.name})
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(store, "_DB", None)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: store._DB.close() if store._DB else None)

    def request(self, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.request("GET" if body is None else "POST", path,
                         None if body is None else json.dumps(body),
                         {**({"Content-Type": "application/json"} if body is not None else {}), **(headers or {})})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def candidate(self):
        layout = layouts.default()
        layout["widgets"] = [w for w in layout["widgets"] if w["id"] != "tasks"]
        layout["widgets"][-1].update(width=2, title="Recorded activity")
        return layout

    def test_preview_apply_reload_and_rollback_never_dispatch(self):
        with mock.patch.object(door_console, "_ask") as ask:
            code, head = self.request("/api/layout")
            self.assertEqual(code, 200)
            self.assertEqual({r["type"] for r in head["registry"]},
                             {"core", "conversation", "tasks", "agents", "approvals", "activity"})
            code, preview = self.request("/api/layout/preview", {"layout": self.candidate()})
            self.assertEqual(code, 200)
            self.assertEqual(self.request("/api/layout")[1]["revision"], 0)
            self.assertEqual(preview["diff"]["removed"], ["tasks"])
            code, applied = self.request("/api/layout/apply", {"preview_id": preview["preview_id"]})
            self.assertEqual((code, applied["revision"]), (200, 1))
            self.assertEqual(self.request("/api/layout")[1]["layout"], self.candidate())
            self.assertEqual(self.request("/api/layout/apply", {"preview_id": preview["preview_id"]})[0], 400)
            code, back = self.request("/api/layout/rollback", {"expected_revision": 1})
            self.assertEqual((code, back["revision"], back["layout"]), (200, 2, layouts.default()))
            ask.assert_not_called()

    def test_no_raw_layout_apply_or_arbitrary_fields(self):
        for path, body in (("/api/layout/apply", {"layout": self.candidate(), "expected_revision": 0}),
                           ("/api/layout/rollback", {"expected_revision": True}),
                           ("/api/layout/preview", {"layout": self.candidate(), "door": "cli"}),
                           ("/api/layout/preview", {"layout": self.candidate(), "chat": "other"})):
            self.assertEqual(self.request(path, body)[0], 400)
        candidate = self.candidate()
        candidate["widgets"][0]["data_source"] = "https://evil.example/data"
        self.assertEqual(self.request("/api/layout/preview", {"layout": candidate})[0], 400)
        self.assertEqual(self.request("/api/layout")[1]["revision"], 0)

    def test_scope_expiry_stale_and_foreign_origin_reject(self):
        private = layouts.preview(self.candidate(), "other-chat", "cli")
        self.assertEqual(self.request("/api/layout/apply", {"preview_id": private["preview_id"]})[0], 400)
        _, preview = self.request("/api/layout/preview", {"layout": self.candidate()})
        with mock.patch.object(layouts.time, "time", return_value=preview["expires"] + 1):
            self.assertEqual(self.request("/api/layout/apply", {"preview_id": preview["preview_id"]})[0], 400)
        _, winner = self.request("/api/layout/preview", {"layout": layouts.default()})
        self.assertEqual(self.request("/api/layout/apply", {"preview_id": winner["preview_id"]})[0], 200)
        self.assertEqual(self.request("/api/layout/apply", {"preview_id": preview["preview_id"]})[0], 400)
        self.assertEqual(self.request("/api/layout/preview", {"layout": self.candidate()},
                                      {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/layout", headers={"Host": "evil.example"})[0], 403)


if __name__ == "__main__":
    unittest.main()
