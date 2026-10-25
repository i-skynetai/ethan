"""Real HTTP boundary checks; no live ledger, model, or agent required."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault('ETHAN_STATE_DIR', tempfile.mkdtemp(prefix='ethan-boundary-'))
from ethan import door_console  # noqa: E402


class ConsoleBoundary(unittest.TestCase):
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

    def request(self, method='GET', path='/', body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            conn.request(method, path, body, headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_rebinding_cannot_read_html_or_private_state(self):
        with mock.patch.object(door_console, '_state') as state:
            for path in ('/', '/api/state', '/api/conversation', '/api/agents'):
                self.assertEqual(self.request(path=path, headers={'Host': 'evil.example'})[0], 403)
            state.assert_not_called()
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request(headers={'Host': f'localhost:{self.port}'})[0], 200)

    def test_rebinding_and_foreign_origin_cannot_dispatch(self):
        with mock.patch.object(door_console, '_ask') as ask:
            for extra in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}):
                self.assertEqual(self.request('POST', '/api/ask', '{"text":"status"}',
                    {'Content-Type': 'application/json', **extra})[0], 403)
            ask.assert_not_called()

    def test_bad_json_shapes_never_reach_ingest_or_ask(self):
        with mock.patch.object(door_console.harvest, 'ingest_document') as ingest, \
                mock.patch.object(door_console, '_ask') as ask:
            for path in ('/api/ask', '/api/ingest'):
                for data in ([], None, 1, 'text', {'chat': []}, {'path': 3}, {'text': {}}):
                    self.assertEqual(self.request('POST', path, json.dumps(data),
                        {'Content-Type': 'application/json'})[0], 400)
            ingest.assert_not_called()
            ask.assert_not_called()
        self.assertEqual(self.request()[0], 200)

    def test_invalid_cursors_are_client_errors(self):
        for query in ('after=', 'after', 'after=1&after=', 'offset=-1', 'run=abc', 'id=1&id=2', 'after=1.2', 'after=' + '9'*19):
            self.assertEqual(self.request(path='/api/log?' + query)[0], 400)

    def test_ambiguous_body_framing_is_rejected(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            conn.putrequest('POST', '/api/ask')
            conn.putheader('Content-Type', 'application/json')
            conn.putheader('Content-Length', '2')
            conn.putheader('Content-Length', '2')
            conn.endheaders(b'{}')
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            conn.close()
        self.assertEqual(self.request('POST', '/api/ask', '{}',
            {'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked'})[0], 400)

    def test_valid_request_still_dispatches(self):
        event = threading.Event()
        with mock.patch.object(door_console, '_ask', side_effect=lambda *args: event.set()) as ask:
            self.assertEqual(self.request('POST', '/api/ask', '{"text":"status"}',
                {'Content-Type': 'application/json'})[0], 200)
            self.assertTrue(event.wait(3))
            ask.assert_called_once_with('status', 'console', None, 'console')


if __name__ == '__main__':
    unittest.main()
