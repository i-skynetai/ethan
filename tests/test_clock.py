"""EH-061: reminders and recurring checks on Ethan's own clock, with a fake clock."""
import datetime as dt
import os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import clock, store  # noqa: E402

# a Wednesday at 10:00 local time
NOW = dt.datetime(2026, 10, 7, 10, 0).timestamp()
MIN = 60


class Got:
    def __init__(self):
        self.items, self.asks = [], []

    def deliver(self, chat, door, text):
        self.items.append((chat, text))

    def run(self, chat, text, deliver, door):
        self.asks.append((chat, text, door))

    def texts(self, chat):
        return [t for c, t in self.items if c == chat]


def take(text, chat, now=NOW):
    out = []
    handled = clock.take(chat, text, out.append, "console", now=now)
    return handled, out


def tick(now, got):
    return clock.tick(now=now, deliver=got.deliver, run=got.run)


class ReadingTheAsk(unittest.TestCase):
    def test_at_a_clock_time_today_or_tomorrow(self):
        p = clock.parse("remind me at 15:00 to send the report", NOW)
        self.assertEqual((p["kind"], p["what"]), ("reminder", "send the report"))
        self.assertEqual(dt.datetime.fromtimestamp(p["due"]).strftime("%d %H:%M"), "07 15:00")
        p = clock.parse("remind me at 9 to book the room", NOW)      # 09:00 is gone: tomorrow
        self.assertEqual(dt.datetime.fromtimestamp(p["due"]).strftime("%d %H:%M"), "08 09:00")
        p = clock.parse("remind me tomorrow at 3pm to call back", NOW)
        self.assertEqual(dt.datetime.fromtimestamp(p["due"]).strftime("%d %H:%M"), "08 15:00")

    def test_in_a_while(self):
        p = clock.parse("remind me in 20 minutes to call back", NOW)
        self.assertEqual((p["due"] - NOW, p["what"]), (20 * MIN, "call back"))

    def test_recurring_asks(self):
        p = clock.parse("every weekday at 09:00, what is running?", NOW)
        self.assertEqual((p["kind"], p["every"], p["at_time"], p["what"]),
                         ("ask", "weekday", "09:00", "what is running?"))
        self.assertEqual(dt.datetime.fromtimestamp(p["due"]).strftime("%a %H:%M"), "Thu 09:00")
        friday = dt.datetime(2026, 10, 9, 10, 0).timestamp()
        p = clock.parse("every weekday at 09:00, what is running?", friday)
        self.assertEqual(dt.datetime.fromtimestamp(p["due"]).strftime("%a"), "Mon")
        p = clock.parse("every hour, ask the codex session to check CI", NOW)
        self.assertEqual((p["every"], p["due"] - NOW), ("hour", 3600))

    def test_what_it_cannot_read_is_said_not_guessed(self):
        self.assertIn("could not find a time", clock.parse("remind me to breathe", NOW))
        self.assertIn("time as well", clock.parse("every weekday, stretch", NOW))
        self.assertIn("what to remind", clock.parse("remind me at 15:00", NOW))
        self.assertIn("not a time", clock.parse("remind me at 25:00 to sleep", NOW))


class SettingAndFiring(unittest.TestCase):
    def setUp(self):                              # rows other tests scheduled must not fire here
        for r in clock.scheduled():
            clock._set(r["id"], state="cancelled")

    def test_a_reminder_fires_once_at_its_time_and_not_before(self):
        handled, out = take("remind me in 10 minutes to call the dentist", "c-once")
        self.assertTrue(handled)
        self.assertIn("I will remind you", out[0])
        got = Got()
        self.assertEqual(tick(NOW + 9 * MIN, got), [])
        fired = tick(NOW + 10 * MIN, got)
        self.assertEqual([r["state"] for r in fired], ["fired"])
        self.assertEqual(got.texts("c-once"), ["Reminder #%d: call the dentist" % fired[0]["id"]])
        self.assertEqual(tick(NOW + 11 * MIN, got), [])              # not again
        self.assertEqual(clock.scheduled("c-once"), [])

    def test_a_scheduled_ask_runs_through_the_clock_door(self):
        take("at 10:30, ask the codex session to check CI", "c-ask")
        got = Got()
        tick(NOW + 30 * MIN, got)
        self.assertEqual(got.asks, [("c-ask", "ask the codex session to check CI", "console")])

    def test_a_recurring_ask_moves_on_to_its_next_time(self):
        take("every weekday at 09:00, what is running?", "c-rec")
        got = Got()
        thu9 = dt.datetime(2026, 10, 8, 9, 0).timestamp()
        fired = tick(thu9, got)
        self.assertEqual(len(got.asks), 1)
        (r,) = fired
        self.assertEqual(r["state"], "scheduled")
        self.assertEqual(dt.datetime.fromtimestamp(r["due"]).strftime("%a %H:%M"), "Fri 09:00")
        fri9 = dt.datetime(2026, 10, 9, 9, 0).timestamp()
        (r,) = tick(fri9, got)
        self.assertEqual(dt.datetime.fromtimestamp(r["due"]).strftime("%a %H:%M"), "Mon 09:00")

    def test_a_reminder_that_came_due_while_stopped_is_told_as_missed(self):
        take("remind me in 5 minutes to join the call", "c-missed")
        got = Got()
        (r,) = tick(NOW + 5 * MIN + clock.GRACE_SEC + 60, got)       # Ethan was down
        self.assertEqual(r["state"], "missed")
        (text,) = got.texts("c-missed")
        self.assertIn("Missed reminder", text)
        self.assertIn("join the call", text)
        self.assertEqual(got.asks, [])

    def test_a_missed_recurring_check_is_told_and_rescheduled_not_run_late(self):
        take("every day at 18:00, what is running?", "c-missrec")
        got = Got()
        (r,) = tick(dt.datetime(2026, 10, 7, 19, 0).timestamp(), got)
        self.assertEqual(r["state"], "scheduled")
        self.assertEqual(got.asks, [])
        self.assertIn("Missed", got.texts("c-missrec")[0])
        self.assertEqual(dt.datetime.fromtimestamp(r["due"]).strftime("%d %H:%M"), "08 18:00")

    def test_list_and_cancel(self):
        take("remind me at 16:00 to send the minutes", "c-list")
        handled, out = take("my reminders", "c-list")
        self.assertTrue(handled)
        self.assertIn("send the minutes", out[0])
        rid = clock.scheduled("c-list")[0]["id"]
        handled, out = take(f"cancel reminder #{rid}", "c-list")
        self.assertEqual(out, [f"Cancelled reminder #{rid}."])
        self.assertEqual(clock.scheduled("c-list"), [])
        handled, out = take("cancel reminder #99999", "c-list")
        self.assertIn("no scheduled reminder", out[0])

    def test_other_asks_are_not_the_clocks(self):
        for text in ("fix the invoice bug", "what is running?", "tell me about reminders",
                     "ask the codex session to review the tests"):
            handled, out = take(text, "c-other")
            self.assertFalse(handled, text)
            self.assertEqual(out, [])

    def test_the_ledger_survives_a_restart(self):
        take("remind me in 50 minutes to stretch", "c-restart")
        rid = clock.scheduled("c-restart")[0]["id"]
        store._DB.close(); store._DB = None                             # a new process
        self.assertEqual([r["id"] for r in clock.scheduled("c-restart")], [rid])
        self.assertIsNotNone(clock.last_tick())


class ThroughTheRouter(unittest.TestCase):
    def test_a_reminder_ask_needs_no_model_and_starts_nothing(self):
        from unittest import mock
        from ethan import hands, llm, router
        with mock.patch.object(llm, "ask", side_effect=AssertionError("no model for a reminder")), \
                mock.patch.object(hands, "run", side_effect=AssertionError("no hand")):
            out = []
            router.handle("r-router", "remind me in 15 minutes to stand up", out.append, door="console")
        self.assertIn("I will remind you", out[0])
        self.assertTrue(out[-1].startswith("Session can close"))

    def test_the_clock_door_is_refused_a_build(self):
        from ethan import router
        from tests.test_routing import stubbed
        route = {"kind": "build", "kb": "notes_kb", "hand": "claude", "steps": [],
                 "search_query": "q", "reason": "stub"}
        with stubbed(route) as stub:
            out = []
            router.handle("r-clockdoor", "write the weekly summary", out.append, door=clock.DOOR)
        self.assertIn("may only remind and read", out[0])
        self.assertEqual(stub.runs, [])

    def test_the_clock_door_may_ask_for_status(self):
        from ethan import router
        from tests.test_routing import stubbed
        route = {"kind": "status", "kb": "none", "hand": "none", "steps": [], "search_query": "", "reason": ""}
        from unittest import mock
        from ethan import relay
        with stubbed(route), mock.patch.object(relay, "bridge_dir", return_value=None):
            out = []
            router.handle("r-clockstatus", "what is running?", out.append, door=clock.DOOR)
        self.assertTrue(out[0].startswith(("Nothing is running", "1 running", "2 running")) or "running" in out[0])


if __name__ == "__main__":
    unittest.main()
