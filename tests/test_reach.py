"""EH-062: the conversation always; the phone when urgent or when you are away."""
import datetime as dt
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import clock, door_telegram, reach, store  # noqa: E402

NOON = dt.datetime(2026, 10, 7, 12, 0).timestamp()
NIGHT = dt.datetime(2026, 10, 7, 23, 30).timestamp()
PHONE = {"TELEGRAM_BOT_TOKEN": "t-test", "TELEGRAM_ALLOWED_USER_IDS": "111, 222"}


class Phone:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def __call__(self, token, chat_id, text):
        if self.fail:
            raise OSError("network down")
        self.sent.append((chat_id, text))


def last(chat):
    return [r["text"] for r in store.replies_since(chat)]


def attempts(chat):
    return [(r["route"], r["state"], r["why"]) for r in reversed(reach.recent(50)) if r["chat_id"] == chat]


class WhereItGoes(unittest.TestCase):
    def test_without_a_phone_only_the_conversation_and_it_is_recorded(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_ALLOWED_USER_IDS": ""}):
            routes = reach.tell("r-none", "console", "Reminder: stretch", now=NOON)
        self.assertEqual(routes, ["conversation"])
        self.assertEqual(last("r-none"), ["Reminder: stretch"])
        self.assertEqual(attempts("r-none"), [("conversation", "sent", "always"),
                                              ("phone", "skipped", "Telegram is not configured")])

    def test_urgent_goes_to_the_phone_even_when_you_are_here(self):
        phone = Phone()
        store.remember("r-urgent", "user", "hi")                 # at the laptop just now
        with mock.patch.dict(os.environ, PHONE), mock.patch.object(door_telegram, "send", phone):
            routes = reach.tell("r-urgent", "console", "URGENT: the deploy is failing", now=NOON)
        self.assertEqual(routes, ["conversation", "phone"])
        self.assertEqual([c for c, _ in phone.sent], ["111", "222"])
        self.assertTrue(phone.sent[0][1].startswith("Ethan: URGENT"))
        self.assertIn(("phone", "sent", "urgent"), attempts("r-urgent"))

    def test_not_urgent_and_at_the_laptop_stays_on_the_desktop(self):
        phone = Phone()
        with mock.patch.dict(os.environ, PHONE), mock.patch.object(door_telegram, "send", phone), \
                mock.patch.object(reach, "last_seen", return_value=NOON):   # typed a minute ago
            routes = reach.tell("r-here", "console", "Reminder: stretch", now=NOON + 60)
        self.assertEqual((routes, phone.sent), (["conversation"], []))
        self.assertIn(("phone", "skipped", "you were at the laptop"), attempts("r-here"))

    def test_away_goes_to_the_phone(self):
        phone = Phone()
        with mock.patch.dict(os.environ, PHONE), mock.patch.object(door_telegram, "send", phone), \
                mock.patch.object(reach, "last_seen", return_value=NOON - 3600):
            routes = reach.tell("r-away", "console", "Reminder: stretch", now=NOON)
        self.assertEqual(routes, ["conversation", "phone"])
        self.assertIn(("phone", "sent", "you were away"), attempts("r-away"))

    def test_quiet_hours_hold_the_phone_unless_urgent(self):
        phone = Phone()
        with mock.patch.dict(os.environ, PHONE), mock.patch.object(door_telegram, "send", phone), \
                mock.patch.object(reach, "last_seen", return_value=NIGHT - 3600):
            reach.tell("r-quiet", "console", "Reminder: stretch", now=NIGHT)
            self.assertEqual(phone.sent, [])
            reach.tell("r-quiet", "console", "URGENT: server down", now=NIGHT)
            self.assertEqual(len(phone.sent), 2)
        self.assertIn(("phone", "skipped", "quiet hours 22:00-07:00"), attempts("r-quiet"))

    def test_a_phone_failure_is_recorded_and_the_desktop_still_has_it(self):
        with mock.patch.dict(os.environ, PHONE), mock.patch.object(door_telegram, "send", Phone(fail=True)):
            routes = reach.tell("r-fail", "console", "URGENT: look", now=NOON)
        self.assertEqual(routes, ["conversation"])
        self.assertIn("Telegram refused", last("r-fail")[-1])
        self.assertIn(("phone", "failed", "OSError: network down"), attempts("r-fail"))

    def test_the_clock_delivers_through_reach(self):
        phone = Phone()
        for r in clock.scheduled():
            clock._set(r["id"], state="cancelled")
        out = []
        clock.take("r-clock", "remind me in 5 minutes to call the client — urgent", out.append, "console", now=NOON)
        with mock.patch.dict(os.environ, PHONE), mock.patch.object(door_telegram, "send", phone):
            clock.tick(now=NOON + 300)
        self.assertEqual(len(phone.sent), 2)
        self.assertIn("call the client", phone.sent[0][1])


if __name__ == "__main__":
    unittest.main()
