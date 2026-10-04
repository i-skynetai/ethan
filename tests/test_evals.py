"""EH-068: the eval suite — does the assistant behave, not just do its code paths run?

Each scenario is a short story told with stub sources, a fake bridge and a fake
clock, and a score that must stay at its target. Unit tests elsewhere check one
function; these check the four promises the vision makes:

  1. reminders are on time        2. nothing is nagged twice
  3. nothing important is missed  4. nothing goes out without a yes

A change that lowers a score fails here before it ships. New features add scenarios.
"""
import datetime as dt
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, clock, door_telegram, hands, harvest, llm, reach, relay, router, store, todo  # noqa: E402
from tests.test_follow import StatefulBridge, Delivered  # noqa: E402
from tests.test_relay import SESSIONS  # noqa: E402

T0 = dt.datetime(2026, 10, 7, 9, 0).timestamp()        # Wednesday 09:00
MIN = 60
TICK = 20                                               # the service's clock period


class Scenario(unittest.TestCase):
    """A clean world: no open relays, reminders or tasks from other tests; a bridge
    that remembers; no model and no hand reachable, so any call to them fails loudly."""

    def setUp(self):
        for r in store.open_relays():
            store.update_relay(r["id"], state="dropped", note="eval isolation")
        for r in clock.scheduled():
            clock._set(r["id"], state="cancelled")
        for t in todo.open_tasks(T0 + 10 ** 9):
            todo.set_state(t["id"], "dropped")
        self.bridge = StatefulBridge()
        self.got = Delivered()
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        self.patches = [
            mock.patch.object(bridge_registry, "sessions", return_value=reg),
            mock.patch.object(relay, "_bridge", self.bridge),
            mock.patch.object(relay, "_REGISTERED", []),
            mock.patch.object(llm, "ask", side_effect=AssertionError("the assistant called a model")),
            mock.patch.object(hands, "run", side_effect=AssertionError("the assistant started a hand")),
            mock.patch.object(reach, "phone_configured", return_value=False),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def say(self, text, chat, door="console", now=T0):
        out = []
        with mock.patch.object(clock.time, "time", return_value=now), \
                mock.patch.object(todo.time, "time", return_value=now):
            router.handle(chat, text, out.append, door=door)
        return out

    def run_clock(self, start, end):
        """Every tick the service would make between two moments."""
        t = start
        while t <= end:
            clock.tick(now=t, deliver=self.got)
            relay.follow(self.got)
            t += TICK


class OnTime(Scenario):
    def test_every_reminder_fires_within_one_tick_of_its_time(self):
        due = {}
        for i, mins in enumerate((5, 17, 42, 90)):
            self.say(f"remind me in {mins} minutes to do thing {i}", "ev-time")
            due[f"do thing {i}"] = T0 + mins * MIN
        fired_at = {}
        t = T0
        while t <= T0 + 100 * MIN:
            for r in clock.tick(now=t, deliver=self.got):
                fired_at[r["what"]] = t
            t += TICK
        late = {k: fired_at[k] - due[k] for k in due}
        self.assertEqual(len(late), 4, late)
        self.assertTrue(all(0 <= d < TICK for d in late.values()), late)      # score: 4/4 within a tick

    def test_a_reminder_missed_while_stopped_is_told_within_one_tick_of_restart(self):
        self.say("remind me in 5 minutes to join the call", "ev-miss")
        restart = T0 + 60 * MIN                                              # Ethan was down an hour
        fired = clock.tick(now=restart, deliver=self.got)
        self.assertEqual([r["state"] for r in fired], ["missed"])
        self.assertIn("Missed reminder", self.got.texts("ev-miss")[0])
        self.assertIn("55 min ago", self.got.texts("ev-miss")[0])


class NoDoubleNag(Scenario):
    def test_a_reminder_is_told_once_and_a_watch_item_becomes_one_task(self):
        self.say("remind me in 1 minute to breathe", "ev-nag")
        self.say("watch mail through the claude session ethan every day at 09:30: what must I reply to?", "ev-nag")
        self.run_clock(T0, T0 + 29 * MIN)
        reminders = [t for t in self.got.texts("ev-nag") if t.startswith("Reminder #")]
        self.assertEqual(len(reminders), 1)                                  # once, over 90 ticks
        # the watch runs at 09:30, answers, and the same answer comes again the next day
        self.run_clock(T0 + 30 * MIN, T0 + 31 * MIN)
        (r,) = store.open_relays("ev-nag")
        answer = "- Reply to Dana | https://mail.example/t/1 | asked twice | -"
        self.bridge.advance(r["message_id"], "completed", answer)
        relay.follow(self.got)
        day2 = T0 + 24 * 3600 + 30 * MIN
        self.run_clock(day2, day2 + MIN)
        (r2,) = store.open_relays("ev-nag")
        self.bridge.advance(r2["message_id"], "completed", answer)
        relay.follow(self.got)
        self.assertEqual(len(todo.open_tasks(day2)), 1)                     # score: 1 task, not 2
        self.assertIn("1 already on your list", self.got.texts("ev-nag")[-1])

    def test_a_relay_state_is_told_once_per_change(self):
        self.say("ask the codex session codex-ethan to look at the tests", "ev-once")
        (r,) = store.open_relays("ev-once")
        for _ in range(5):
            relay.follow(self.got)
        self.bridge.advance(r["message_id"], "acknowledged")
        for _ in range(5):
            relay.follow(self.got)
        self.assertEqual(len(self.got.texts("ev-once")), 1)                 # one line for one change


class NothingImportantMissed(Scenario):
    def test_every_item_a_watch_reports_is_on_the_list_or_shown_as_unreadable(self):
        self.say("watch tickets via codex-ethan every day at 09:30: which tickets assigned to me changed?", "ev-miss2")
        self.run_clock(T0 + 30 * MIN, T0 + 31 * MIN)
        (r,) = store.open_relays("ev-miss2")
        self.bridge.advance(r["message_id"], "completed",
                            "- PROJ-1 needs an estimate | https://t.example/1 | due this week | friday\n"
                            "- PROJ-2 was reassigned to you | https://t.example/2 | new | -\n"
                            "some prose the session added\n"
                            "- PROJ-3 comment awaits you | https://t.example/3 | asked a question | tomorrow")
        relay.follow(self.got)
        tasks = todo.open_tasks(T0 + 31 * MIN)
        self.assertEqual(len(tasks), 3)                                     # score: 3/3 items kept
        self.assertTrue(all(t["link"] for t in tasks))
        self.assertIn("could not read these lines", self.got.texts("ev-miss2")[-1])
        self.assertIn("some prose the session added", self.got.texts("ev-miss2")[-1])

    def test_an_unanswered_relay_is_never_called_nothing_pending(self):
        self.say("ask the codex session codex-ethan to look at the tests", "ev-pending")
        for _ in range(3):
            self.assertFalse(harvest.can_close("ev-pending")[0])
            relay.follow(self.got)
        (r,) = store.open_relays("ev-pending")
        self.bridge.advance(r["message_id"], "completed", "looked")
        relay.follow(self.got)
        self.assertTrue(harvest.can_close("ev-pending")[0])


class NothingWithoutAYes(Scenario):
    def test_the_clock_and_telegram_cannot_start_or_hand_off_work(self):
        route = {"kind": "build", "kb": "none", "hand": "claude", "steps": [], "search_query": "", "reason": ""}
        with mock.patch.object(llm, "ask", return_value=dict(route)):
            out = self.say("write the weekly summary", "ev-yes", door=clock.DOOR)
        self.assertIn("may only remind and read", out[0])
        out = self.say("ask the codex session codex-ethan to implement EH-1", "ev-yes", door="telegram-private")
        self.assertIn("telegram-private door", out[0])
        self.assertEqual(self.bridge.sends(), [])                            # score: 0 sends

    def test_watches_and_plain_relays_are_review_only(self):
        self.say("watch mail through the claude session ethan every day at 09:30: what must I reply to?", "ev-ro")
        self.say("ask the claude session ethan to look at the roadmap", "ev-ro")
        self.run_clock(T0 + 30 * MIN, T0 + 31 * MIN)
        modes = [s[s.index("--mode") + 1] for s in self.bridge.sends()]
        self.assertEqual(modes, ["review-only", "review-only"])
        self.assertTrue(any("send nothing and change nothing" in s[-1] for s in self.bridge.sends()))

    def test_the_phone_is_used_only_when_urgent_or_away_and_every_attempt_is_recorded(self):
        phone = []
        with mock.patch.object(reach, "phone_configured", return_value=True), \
                mock.patch.object(reach, "_phone_ids", return_value=["1"]), \
                mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t"}), \
                mock.patch.object(door_telegram, "send", lambda tok, c, t: phone.append(t)), \
                mock.patch.object(reach, "last_seen", return_value=T0):
            reach.tell("ev-phone", "console", "Reminder: stretch", now=T0 + MIN)            # here: no
            reach.tell("ev-phone", "console", "URGENT: prod is down", now=T0 + MIN)         # urgent: yes
            reach.tell("ev-phone", "console", "Reminder: stretch", now=T0 + 45 * MIN)       # away: yes
            reach.tell("ev-phone", "console", "Reminder: stretch",
                       now=dt.datetime(2026, 10, 7, 23, 0).timestamp())                    # quiet: no
        self.assertEqual(len(phone), 2)
        mine = [r for r in reach.recent(50) if r["chat_id"] == "ev-phone"]
        self.assertEqual(len(mine), 8)                                      # 4 desktop + 4 phone decisions
        self.assertTrue(all(r["why"] for r in mine))


if __name__ == "__main__":
    unittest.main()
