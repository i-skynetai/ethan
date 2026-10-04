from contextlib import closing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ethan import bridge_registry
from ethan import door_console


class RegistryTests(unittest.TestCase):
    def test_assistant_help_does_not_call_model_or_launch_hand(self):
        with patch.object(door_console.store, 'remember') as remember, patch.object(door_console.store, 'add_reply') as reply, patch.object(door_console.router, 'handle') as route:
            door_console._ask('What can you do?', chat='test')
        remember.assert_called_once_with('test', 'user', 'What can you do?')
        route.assert_not_called()
        self.assertIn('already running', reply.call_args.args[1])

    def test_registry_reads_both_agents_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bridge.db"
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE sessions(agent,name,project,delivery,status,last_seen)")
                db.executemany("INSERT INTO sessions VALUES(?,?,?,?,?,?)", [(a, a + '-test', 'demo', 'inbox', 'unknown', None) for a in ('claude', 'codex')])
                db.commit()
            before = path.read_bytes()
            with patch.dict(os.environ, {"ETHAN_BRIDGE_DB": str(path)}):
                result = bridge_registry.sessions()
            self.assertTrue(result['available'])
            self.assertEqual([r['agent'] for r in result['sessions']], ['claude', 'codex'])
            self.assertEqual(before, path.read_bytes())

    def test_missing_registry_is_not_created(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "missing.db"
            with patch.dict(os.environ, {"ETHAN_BRIDGE_DB": str(path)}):
                self.assertFalse(bridge_registry.sessions()['available'])
            self.assertFalse(path.exists())
