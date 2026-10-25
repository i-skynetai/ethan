"""Shared HUD and voice HTTP seams without touching microphone hardware."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault('ETHAN_STATE_DIR', tempfile.mkdtemp(prefix='ethan-hud-tests-'))
from ethan import door_console, voice  # noqa: E402


class HudHTTP(unittest.TestCase):
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

    def request(self, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            c.request('GET' if body is None else 'POST', path,
                      None if body is None else json.dumps(body),
                      {} if body is None else {'Content-Type': 'application/json'})
            r = c.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            c.close()

    def test_assets_are_packaged_whitelisted_and_csp_restricts_code(self):
        for path, content in (('/', b'Control center'), ('/assets/hud.css', b'--cyan'),
                              ('/assets/hud.js', b'textContent'), ('/assets/voice_queue.js', b'createVoiceQueue')):
            code, headers, data = self.request(path)
            self.assertEqual(code, 200)
            self.assertIn(content, data)
            self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        for path in ('/assets/../door_console.py', '/assets/%2e%2e/voice.py', '/assets/index.html', '/.env'):
            self.assertEqual(self.request(path)[0], 404)

    def test_voice_routes_do_not_dispatch_or_open_mic_on_read(self):
        status = {'supported': True, 'state': 'idle', 'muted': True, 'transcript': '', 'detail': 'Microphone off'}
        with mock.patch.object(voice, 'status', return_value=status), \
                mock.patch.object(voice, 'command', return_value=status) as command, \
                mock.patch.object(door_console, '_ask') as ask:
            self.assertEqual(json.loads(self.request('/api/voice/status')[2]), status)
            command.assert_not_called()
            for action in ('start', 'stop', 'cancel', 'mute', 'unmute', 'wake-enable', 'wake-disable'):
                self.assertEqual(self.request('/api/voice/' + action, {})[0], 200)
            self.assertEqual([c.args[0] for c in command.call_args_list], ['start','stop','cancel','mute','unmute','wake-enable','wake-disable'])
            self.assertEqual(self.request('/api/voice/approve', {})[0], 404)
            self.assertEqual(self.request('/api/voice/start', [1])[0], 400)
            ask.assert_not_called()

    def test_selected_provider_refuses_invalid_and_unavailable_hook(self):
        from ethan import providers
        with mock.patch.object(providers, 'resolve', side_effect=ValueError('private metadata')), \
                mock.patch.object(door_console, '_ask') as ask:
            code, _, body = self.request('/api/ask', {'text': 'hello', 'chat_provider_ref': 'claude:missing'})
            self.assertEqual(code, 400)
            self.assertNotIn(b'private metadata', body)
            ask.assert_not_called()
        def old_handle(chat, text, reply, door=None, cwd=None):
            raise AssertionError('must not dispatch')
        with mock.patch.object(providers, 'resolve', return_value={'agent': 'claude', 'native_id': 'test', 'name': 'test'}), \
                mock.patch.object(door_console.router, 'handle', old_handle), \
                mock.patch.object(door_console, '_ask') as ask:
            self.assertEqual(self.request('/api/ask', {'text': 'hello', 'chat_provider_ref': 'claude:test'})[0], 503)
            ask.assert_not_called()
        self.assertEqual(self.request('/api/ask', {'text': 'hello', 'chat_provider_ref': 42})[0], 400)

    def test_selected_provider_is_forwarded_to_existing_router(self):
        called = []
        def handle(chat, text, reply, door=None, cwd=None, chat_provider_ref=None):
            called.append((chat, text, door, cwd, chat_provider_ref))
        with mock.patch.object(door_console.router, 'handle', handle), \
                mock.patch.object(door_console.store, 'note_desktop'):
            door_console._ask('hello', 'console', 'C:/project', 'console', 'claude:test')
        self.assertEqual(called, [('console', 'hello', 'console', 'C:/project', 'claude:test')])

    def test_voice_errors_are_reported_without_internal_details(self):
        with mock.patch.object(voice, 'command', side_effect=RuntimeError('private path')):
            code, _, data = self.request('/api/voice/start', {})
            self.assertEqual(code, 503)
            self.assertNotIn(b'private path', data)


if __name__ == '__main__':
    unittest.main()
