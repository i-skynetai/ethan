"""Actual loopback request identity, scope and cancellation seams, no provider calls."""
import http.client
import json
import os
import tempfile
import threading
import unittest
import uuid
from unittest import mock

from ethan import door_console, store, conversation_events as events


class ResponseHTTP(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patch = mock.patch.dict(os.environ, {'ETHAN_STATE_DIR': temp.name})
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(store, '_DB', None)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: store._DB.close() if store._DB else None)
        self.server = door_console.open_server(0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(3)

    def request(self, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=3)
        try:
            conn.request('GET' if body is None else 'POST', path,
                         None if body is None else json.dumps(body),
                         {**({'Content-Type': 'application/json'} if body is not None else {}), **(headers or {})})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_identity_duplicate_conflict_and_read_never_dispatch(self):
        rid = uuid.uuid4().hex
        called = threading.Event()
        with mock.patch.object(door_console.router, 'RESPONSE_EVENTS_SUPPORTED', True, create=True), \
                mock.patch.object(door_console, '_request_worker', side_effect=lambda *a: called.set()) as worker:
            payload = {'request_id': rid, 'text': 'offline test'}
            code, first = self.request('/api/requests', payload)
            self.assertEqual(code, 200)
            self.assertTrue(first['created'])
            self.assertTrue(called.wait(2))
            code, again = self.request('/api/requests', payload)
            self.assertEqual(code, 200)
            self.assertFalse(again['created'])
            self.assertEqual(self.request('/api/requests', {**payload, 'text': 'different'})[0], 409)
            for _ in range(2):
                code, data = self.request('/api/requests?request_id=' + rid + '&after=0')
                self.assertEqual(code, 200)
                self.assertFalse(data['request']['capabilities']['live_text_deltas'])
            self.assertEqual(worker.call_count, 1)

    def test_cancel_before_claim_and_no_cross_scope_read(self):
        rid = uuid.uuid4().hex
        events.create(rid, 'console', 'console', {'text': 'hello'})
        self.assertEqual(self.request('/api/requests/cancel', {'request_id': rid})[0], 200)
        with mock.patch.object(door_console.router, 'handle') as handle:
            door_console._request_worker(rid, 'hello', None, None, None)
            handle.assert_not_called()
        other = uuid.uuid4().hex
        events.create(other, 'other', 'cli', {'text': 'private fixture'})
        self.assertEqual(self.request('/api/requests?request_id=' + other)[0], 404)
        self.assertEqual(self.request('/api/requests/cancel', {'request_id': other})[0], 404)

    def test_validation_guard_and_foreign_origin(self):
        rid = uuid.uuid4().hex
        with mock.patch.object(door_console, '_request_worker') as worker:
            for extra in ({'chat': 'other'}, {'door': 'cli'}, {'text': 3}, {'chat_provider_ref': 42}, {'chat_privacy': 'work'}):
                self.assertEqual(self.request('/api/requests', {'request_id': rid, 'text': 'hello', **extra})[0], 400)
            for suffix in ('&after=', '&after=1&after=2', '&after=-1', '&chat=other'):
                self.assertEqual(self.request('/api/requests?request_id=' + rid + suffix)[0], 400)
            self.assertEqual(self.request('/api/requests', {'request_id': rid, 'text': 'hello'}, {'Origin': 'https://example.invalid'})[0], 403)
            with mock.patch.object(door_console.router, 'RESPONSE_EVENTS_SUPPORTED', False, create=True):
                self.assertEqual(self.request('/api/requests', {'request_id': rid, 'text': 'hello'})[0], 503)
            worker.assert_not_called()

    def test_worker_preserves_final_and_cancel_discards_late_reply(self):
        rid = uuid.uuid4().hex
        events.create(rid, 'console', 'console', {'text': 'fixture'})
        def reply_then_cancel(chat, text, reply, **kwargs):
            reply('checked first reply')
            events.cancel(rid, 'console', 'console')
            reply('must not appear after stop')
        with mock.patch.object(door_console.router, 'handle', side_effect=reply_then_cancel):
            door_console._request_worker(rid, 'fixture', None, None, None)
        data = events.events(rid, 'console', 'console')
        self.assertEqual(data['request']['state'], 'cancelled')
        self.assertNotIn('must not appear', json.dumps(data))
        self.assertNotIn('must not appear', json.dumps(store.replies_since('console', 0)))
        self.assertIn('checked first reply', json.dumps(store.replies_since('console', 0)))
