"""Prepared authentication tests use only synthetic process-local credentials."""
import http.client
import json
import os
import threading
import unittest
from unittest import mock
from ethan import door_console, voice

TOKEN = 'synthetic-test-only-' + 'a' * 40


class LocalAuthHTTP(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict(os.environ, {'ETHAN_LOCAL_API_TOKEN': TOKEN}):
            self.server = door_console.open_server(0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(3)

    def request(self, path, auth=None, method='GET', extra=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            headers = dict(extra or {})
            if auth is not None:
                headers['Authorization'] = auth
            if method == 'POST':
                headers['Content-Type'] = 'application/json'
            conn.request(method, path, '{}' if method == 'POST' else None, headers)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_unauthenticated_api_never_reads_or_controls(self):
        with mock.patch.object(door_console, '_state') as state, mock.patch.object(voice, 'command') as command:
            for auth in (None, 'Bearer wrong', 'Basic '+TOKEN):
                self.assertEqual(self.request('/api/state', auth)[0], 401)
                self.assertEqual(self.request('/api/voice/start', auth, 'POST')[0], 401)
            state.assert_not_called()
            command.assert_not_called()
        self.assertEqual(self.request('/')[0], 200)
        self.assertEqual(self.request('/assets/hud.js')[0], 200)
        self.assertEqual(self.request('/api/state?token='+TOKEN)[0], 401)

    def test_valid_token_retains_origin_protection_and_is_not_echoed(self):
        with mock.patch.object(door_console, '_state', return_value={'test': True}):
            code, body = self.request('/api/state', 'Bearer '+TOKEN)
            self.assertEqual((code, json.loads(body)), (200, {'test': True}))
            self.assertNotIn(TOKEN.encode(), body)
        with mock.patch.object(voice, 'command') as command:
            code, _ = self.request('/api/voice/start', 'Bearer '+TOKEN, 'POST', {'Origin':'http://foreign.example'})
            self.assertEqual(code, 403)
            command.assert_not_called()

    def test_duplicate_authorization_is_rejected(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            conn.putrequest('GET', '/api/state')
            conn.putheader('Authorization', 'Bearer '+TOKEN)
            conn.putheader('Authorization', 'Bearer '+TOKEN)
            conn.endheaders()
            response=conn.getresponse()
            self.assertEqual(response.status,401)
            response.read()
        finally:
            conn.close()

    def test_startup_snapshot_does_not_change_with_environment(self):
        with mock.patch.dict(os.environ, {'ETHAN_LOCAL_API_TOKEN': 'b'*40}), mock.patch.object(door_console,'_state',return_value={}):
            self.assertEqual(self.request('/api/state','Bearer '+TOKEN)[0],200)
            self.assertEqual(self.request('/api/state','Bearer '+'b'*40)[0],401)


if __name__ == '__main__':
    unittest.main()
