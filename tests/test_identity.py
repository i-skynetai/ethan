"""EH-066: Ethan acts as itself, on every path, and says for whom and through which door."""
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, brief, door_telegram, hands, identity, reach, relay, router  # noqa: E402
from tests.test_relay import SESSIONS, FakeBridge  # noqa: E402
from tests.test_routing import stubbed  # noqa: E402


class WhoEthanIs(unittest.TestCase):
    def test_name_owner_and_agent_id_come_from_config_or_env_never_the_machine(self):
        self.assertEqual(identity.name(), "Ethan")
        self.assertEqual(identity.sky_agent_id(), "ethan")
        with mock.patch.dict(os.environ, {"ETHAN_OWNER": ""}):
            self.assertEqual(identity.owner(), "the person who runs it")
            self.assertNotIn(os.environ.get("USERNAME", "\0"), identity.owner())
        with mock.patch.dict(os.environ, {"ETHAN_OWNER": "A. Person"}):
            self.assertEqual(identity.stamp("cli"), "Ethan, for A. Person, via the cli door")


class EveryPathCarriesIt(unittest.TestCase):
    def test_a_relay_is_sent_as_the_app_ethan_and_signed(self):
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []), \
                mock.patch.dict(os.environ, {"ETHAN_OWNER": "A. Person"}):
            router.handle("i-relay", "ask the codex session codex-ethan to look at EH-1", print, door="cli")
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--from") + 1], "app:ethan")
        self.assertTrue(send[-1].endswith("(Passed on by Ethan, for A. Person, via the cli door.)"))
        register = [c for c in fake.calls if c[0] == "register"]
        self.assertEqual(register[0][:3], ("register", "app", "ethan"))

    def test_a_brief_to_a_hand_says_who_is_asking(self):
        route = {"kind": "review", "kb": "notes_kb", "hand": "codex", "steps": [], "search_query": "q", "reason": ""}
        with stubbed(route) as stub, mock.patch.dict(os.environ, {"ETHAN_OWNER": "A. Person"}):
            router.handle("i-brief", "look over the notes", print, door="console")
        (run,) = stub.runs
        self.assertIn("# From\nEthan, for A. Person, via the console door.", run["brief"])
        self.assertIn("The person has not read this brief", run["brief"])

    def test_the_harness_records_ethans_own_agent_id(self):
        """The environment a hand is launched with names Ethan, not the person."""
        self.assertEqual(hands.build_env({"sky": {}})["SKY_AGENT_ID"], "ethan")
        self.assertEqual(hands.build_env({"sky": {"agent_id": "ethan-work"}})["SKY_AGENT_ID"], "ethan-work")
        with mock.patch.dict(os.environ, {"USERNAME": "someone", "USER": "someone"}):
            self.assertNotEqual(hands.build_env({"sky": {}})["SKY_AGENT_ID"], "someone")

    def test_the_phone_line_starts_with_ethans_name(self):
        sent = []
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_ALLOWED_USER_IDS": "1"}), \
                mock.patch.object(door_telegram, "send", lambda tok, c, t: sent.append(t)):
            reach.tell("i-phone", "console", "URGENT: look")
        self.assertTrue(sent and sent[0].startswith("Ethan: "), sent)

    def test_brief_without_a_sender_is_unchanged(self):
        self.assertNotIn("# From", brief.render("t", [], None))


if __name__ == "__main__":
    unittest.main()
