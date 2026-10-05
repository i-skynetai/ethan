"""The release review of 0.2.0: each finding, reproduced and fixed."""
import datetime as dt
import os, sys, tempfile, threading, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, clock, door_telegram, hands, llm, reach, relay, router, store, todo, watch  # noqa: E402
from tests.test_follow import StatefulBridge, Delivered  # noqa: E402
from tests.test_relay import SESSIONS, FakeBridge  # noqa: E402
from tests.test_routing import stubbed  # noqa: E402

NOW = dt.datetime(2026, 10, 7, 10, 0).timestamp()        # Wednesday 10:00


def clean():
    for r in store.open_relays():
        store.update_relay(r["id"], state="dropped", note="test isolation")
    for r in clock.scheduled():
        clock._set(r["id"], state="cancelled")
    for t in todo.open_tasks(NOW + 10 ** 9):
        todo.set_state(t["id"], "dropped")


class P0ScheduledAsksKeepTheirDoorsRights(unittest.TestCase):
    def setUp(self):
        clean()
        self.reg = {"available": True, "sessions": SESSIONS, "note": ""}

    def test_telegram_cannot_reach_a_relay_through_the_clock(self):
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            out = []
            clock.take("tg", "at 17:30, ask the codex session codex-ethan to implement EH-1 and push it",
                       out.append, "telegram-private", now=NOW)
            self.assertIn("I will ask", out[0])
            got = Delivered()
            clock.tick(now=dt.datetime(2026, 10, 7, 17, 30).timestamp(), deliver=got)
        self.assertEqual(fake.sends(), [])
        self.assertTrue(any("telegram-private door" in t for t in got.texts("tg")), got.texts("tg"))

    def test_a_scheduled_implement_from_the_console_is_sent_review_only(self):
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            clock.take("con", "at 17:30, tell the codex session codex-ethan to implement EH-1",
                       print, "console", now=NOW)
            clock.tick(now=dt.datetime(2026, 10, 7, 17, 30).timestamp(), deliver=Delivered())
        (send,) = fake.sends()
        self.assertEqual(send[send.index("--mode") + 1], "review-only")

    def test_a_pending_question_cannot_be_answered_by_a_scheduled_run_or_another_door(self):
        """Found in review: '1' from a scheduled run finished an implementation
        clarification; an answer from another door would have used the asker's rights."""
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            out = []
            router.handle("pq", "ask the claude session to implement EH-1", out.append, door="console")
            self.assertIn("Which session", out[0])
            # a scheduled run that happens to say "1" is not an answer; the question stays open
            with stubbed({"kind": "chat", "kb": "none", "hand": "none", "steps": [], "search_query": "", "reason": ""}), \
                    mock.patch.object(bridge_registry, "sessions", return_value=self.reg):
                out = []
                router.handle("pq", "1", out.append, door="console", scheduled=True)
            self.assertEqual(fake.sends(), [])
            self.assertIsNotNone(store.open_question("pq"))
            # an answer from another door is refused and the question stays open
            out = []
            router.handle("pq", "1", out.append, door="telegram-private")
            self.assertIn("waiting for an answer from the console door", out[0])
            self.assertEqual(fake.sends(), [])
            self.assertIsNotNone(store.open_question("pq"))
            # the right door, the right answer
            router.handle("pq", "1", print, door="console")
            (send,) = fake.sends()
            self.assertEqual(send[send.index("--mode") + 1], "implementation")

    def test_a_scheduled_build_is_refused_whatever_the_door(self):
        route = {"kind": "build", "kb": "none", "hand": "claude", "steps": [], "search_query": "", "reason": ""}
        with stubbed(route) as stub:
            out = []
            router.handle("sb", "write the weekly summary", out.append, door="console", scheduled=True)
        self.assertIn("this was scheduled", out[0])
        self.assertEqual(stub.runs, [])


class P1Findings(unittest.TestCase):
    def setUp(self):
        clean()

    def test_an_unknown_session_name_sends_nothing(self):
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake:
            out = []
            router.handle("p1-name", "ask the claude session foobar to review the roadmap", out.append, door="console")
        self.assertEqual(fake.sends(), [])
        self.assertIn("sent nothing", out[0])
        self.assertEqual(relay.targets("the claude session", SESSIONS), [s for s in SESSIONS if s["agent"] == "claude"])
        self.assertEqual(relay.targets("the running codex session", SESSIONS), [s for s in SESSIONS if s["agent"] == "codex"])

    def test_two_concurrent_follow_ups_deliver_once(self):
        fake = StatefulBridge()
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        got = Delivered()
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", fake), mock.patch.object(relay, "_REGISTERED", []):
            router.handle("p1-race", "ask the codex session codex-ethan to look", print, door="console")
            (r,) = store.open_relays("p1-race")
            fake.advance(r["message_id"], "completed", "looked")
            threads = [threading.Thread(target=relay.follow, args=(got,)) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            relay.follow(got)                                   # a late single pass finds nothing new
        self.assertEqual(len([t for t in got.texts("p1-race") if "answered" in t]), 1)

    def test_due_dates_are_not_guessed(self):
        for text in ("end of month", "after the wedding", "sprint 14", "when ready", "3 PRs"):
            self.assertIsNone(todo.parse_due(text, NOW), text)
        self.assertEqual(dt.datetime.fromtimestamp(todo.parse_due("Oct 10", NOW)).strftime("%Y-%m-%d"), "2026-10-10")
        self.assertEqual(dt.datetime.fromtimestamp(todo.parse_due("10 Oct 2026", NOW)).strftime("%Y-%m-%d"), "2026-10-10")
        self.assertEqual(dt.datetime.fromtimestamp(todo.parse_due("Jan 5", NOW)).strftime("%Y-%m-%d"), "2027-01-05")
        self.assertEqual(dt.datetime.fromtimestamp(todo.parse_due("Oct 10 5pm", NOW)).strftime("%d %H:%M"), "10 17:00")
        self.assertEqual(dt.datetime.fromtimestamp(todo.parse_due("mon", NOW)).strftime("%a"), "Mon")
        self.assertEqual(dt.datetime.fromtimestamp(todo.parse_due("friday at 5", NOW)).strftime("%a %H:%M"), "Fri 05:00")

    def test_parsing_does_not_overreach(self):
        out = []
        self.assertFalse(todo.take("p1-parse", "completed 3 reviews today", out.append, "console", now=NOW))
        self.assertTrue(todo.take("p1-parse", "add task: stand by the door by Friday", out.append, "console", now=NOW))
        self.assertIn("Task #", out[-1])
        self.assertIn("stand by the door, due Fri", out[-1])
        self.assertIn("could not find a time", clock.parse("remind me tomorrow to look at 3 PRs", NOW))
        p = clock.parse("remind me at 9 to book the room", NOW)
        self.assertEqual(dt.datetime.fromtimestamp(p["due"]).strftime("%H:%M"), "09:00")
        p = clock.parse("every weekday at 09:00, what is running?", NOW)
        self.assertEqual(p["at_time"], "09:00")

    def test_status_asks_need_no_model(self):
        with mock.patch.object(llm, "ask", side_effect=AssertionError("a status ask called the model")), \
                mock.patch.object(hands, "run", side_effect=AssertionError("no hand")), \
                mock.patch.object(relay, "bridge_dir", return_value=None):
            for text in ("what is running?", "What's pending", "status", "anything pending?"):
                out = []
                router.handle("p1-status", text, out.append, door="console")
                self.assertTrue("running" in out[0] or "pending" in out[0] or "Nothing" in out[0], (text, out))
            out = []
            router.handle("p1-status", "what is on my task list", out.append, door="console")
            self.assertIn("list is empty", out[0])

    def test_away_means_away_from_the_laptop(self):
        phone = []
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_ALLOWED_USER_IDS": "1"}), \
                mock.patch.object(door_telegram, "send", lambda tok, c, t: phone.append(t)), \
                mock.patch.object(store, "last_desktop", return_value=NOW - 3600):
            store.remember("p1-away", "user", "a telegram message just now")   # typed on the phone
            reach.tell("p1-away", "console", "Reminder: stretch", now=NOW)
        self.assertEqual(len(phone), 1)                                       # still away from the laptop

    def test_a_sessions_answer_stays_on_the_desktop(self):
        phone = []
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_ALLOWED_USER_IDS": "1"}), \
                mock.patch.object(door_telegram, "send", lambda tok, c, t: phone.append(t)), \
                mock.patch.object(store, "last_desktop", return_value=NOW - 3600):
            relay.deliver_reply("p1-privacy", "console", "URGENT client figures: …")
        self.assertEqual(phone, [])
        self.assertIn("URGENT client figures", [x["text"] for x in store.replies_since("p1-privacy")][-1])


class P2Findings(unittest.TestCase):
    def setUp(self):
        clean()

    def test_a_reminder_whose_delivery_raises_is_told_once_not_every_tick(self):
        out = []
        clock.take("p2-raise", "remind me in 1 minute to breathe", out.append, "console", now=NOW)
        calls = []
        def deliver(c, d, t):
            calls.append(t)
            if len(calls) == 1:
                raise RuntimeError("telegram down")
        for i in range(5):
            clock.tick(now=NOW + 60 + i * 20, deliver=deliver)
        self.assertEqual(len([c for c in calls if c.startswith("Reminder #")]), 1)
        self.assertTrue(any("failed" in c for c in calls))

    def test_a_missed_notice_that_raises_is_told_once_and_later_rows_still_fire(self):
        """Found in review: the missed branch delivered before moving the row, so a
        failing notice retried every tick and held up every row behind it."""
        out = []
        clock.take("p2-missed", "remind me in 1 minute to breathe", out.append, "console", now=NOW)
        clock.take("p2-missed", "remind me in 12 minutes to stretch", out.append, "console", now=NOW)
        calls = []
        def broken(c, d, t):
            calls.append(t)
            if t.startswith("Missed"):
                raise RuntimeError("telegram down")
        for i in range(3):
            clock.tick(now=NOW + 600 + i * 20, deliver=broken)              # 10 min late: missed
        self.assertEqual(len([c for c in calls if c.startswith("Missed")]), 1)
        rows = {r["what"]: r for r in clock._rows("chat_id=?", ("p2-missed",))}
        self.assertEqual(rows["breathe"]["state"], "missed")
        self.assertIn("notice failed", rows["breathe"]["note"])
        clock.tick(now=NOW + 12 * 60, deliver=broken)                       # the next row is not held up
        self.assertTrue(any(c.startswith("Reminder #") and "stretch" in c for c in calls), calls)

    def test_every_hour_does_not_drift(self):
        clock.take("p2-hour", "every hour, what is running?", print, "console", now=NOW)
        got = Delivered()
        with mock.patch.object(clock, "_run_ask"):
            (r,) = clock.tick(now=NOW + 3600 + 19, deliver=got)          # fired 19 s late
        self.assertEqual(r["due"], NOW + 7200)                            # the next one is on the hour

    def test_a_stopped_watch_does_not_file_its_late_answer(self):
        fake = StatefulBridge()
        reg = {"available": True, "sessions": SESSIONS, "note": ""}
        got = Delivered()
        with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
                mock.patch.object(relay, "_bridge", fake), mock.patch.object(relay, "_REGISTERED", []):
            with mock.patch.object(watch.time, "time", return_value=NOW):
                router.handle("p2-stop", "watch mail through the claude session ethan every day at 09:00: what must I reply to?",
                              print, door="console")
            clock.tick(now=dt.datetime(2026, 10, 8, 9, 0).timestamp(), deliver=got)
            (r,) = store.open_relays("p2-stop")
            router.handle("p2-stop", f"stop watch #{watch.active('p2-stop')[0]['id']}", print, door="console")
            fake.advance(r["message_id"], "completed", "- Late item | https://x.example/1 | late | -")
            relay.follow(got)
        self.assertIn("was stopped while its question was out", got.texts("p2-stop")[-1])
        self.assertEqual(todo.open_tasks(NOW + 10 ** 6), [])

    def test_a_done_item_reported_again_is_not_a_new_task(self):
        tid, new = todo.add("Review MR !7", source="gitlab", link="https://git.example/mr/7")
        todo.set_state(tid, "done")
        again, new2 = todo.add("Review MR !7", source="gitlab", link="https://git.example/mr/7")
        self.assertEqual((again, new2), (tid, False))


if __name__ == "__main__":
    unittest.main()
