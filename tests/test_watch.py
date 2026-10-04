"""EH-063: a watch asks a running session on a schedule and turns its answer into tasks."""
import contextlib, datetime as dt, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, clock, hands, llm, relay, router, store, todo, watch  # noqa: E402
from tests.test_follow import StatefulBridge, Delivered  # noqa: E402
from tests.test_relay import SESSIONS  # noqa: E402

NOW = dt.datetime(2026, 10, 7, 10, 0).timestamp()       # Wednesday 10:00
THU9 = dt.datetime(2026, 10, 8, 9, 0).timestamp()
FRI9 = dt.datetime(2026, 10, 9, 9, 0).timestamp()

ANSWER = """- Reply to Dana about the Q4 plan | https://mail.example/t/101 | she asked for a decision | friday
- Approve the access request | https://mail.example/t/102 | blocks the new starter | -
- nothing to see here, really"""


@contextlib.contextmanager
def world():
    fake = StatefulBridge()
    reg = {"available": True, "sessions": SESSIONS, "note": ""}
    for r in store.open_relays():
        store.update_relay(r["id"], state="dropped", note="test isolation")
    for r in clock.scheduled():
        clock._set(r["id"], state="cancelled")
    for t in todo.open_tasks(NOW + 10 ** 9):
        todo.set_state(t["id"], "dropped")
    with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
            mock.patch.object(relay, "_bridge", fake), \
            mock.patch.object(relay, "_REGISTERED", []), \
            mock.patch.object(llm, "ask", side_effect=AssertionError("no model")), \
            mock.patch.object(hands, "run", side_effect=AssertionError("no hand")):
        yield fake


def ask(text, chat, now=NOW):
    out = []
    with mock.patch.object(watch.time, "time", return_value=now):
        router.handle(chat, text, out.append, door="console")
    return out


class SettingAWatch(unittest.TestCase):
    def test_a_watch_is_set_and_scheduled_with_no_model(self):
        with world() as fake:
            out = ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-set")
        self.assertIn("Watch #", out[0])
        self.assertIn("claude:ethan (review-only)", out[0])
        self.assertIn("Thu 08 Oct 09:00", out[0])
        self.assertEqual(fake.sends(), [])                     # nothing sent until the time
        (w,) = watch.active("w-set")
        self.assertEqual((w["source"], w["target"], w["every"], w["at_time"]), ("mail", "claude:ethan", "weekday", "09:00"))
        (row,) = [r for r in clock.scheduled("w-set") if r["kind"] == "watch"]
        self.assertEqual(row["what"], str(w["id"]))

    def test_an_unclear_target_sets_nothing_up(self):
        with world() as fake:
            out = ask("watch mail through the claude session every weekday at 09:00: what must I reply to?", "w-amb")
        self.assertIn("2 sessions", out[0])
        self.assertEqual(watch.active("w-amb"), [])
        self.assertEqual(fake.sends(), [])

    def test_list_and_stop(self):
        with world():
            ask("watch tickets via codex-ethan every day at 08:30: which tickets assigned to me changed?", "w-stop")
            out = ask("my watches", "w-stop")
            self.assertIn("tickets through codex:codex-ethan · every day at 08:30", out[0])
            wid = watch.active("w-stop")[0]["id"]
            out = ask(f"stop watch #{wid}", "w-stop")
        self.assertIn(f"Stopped watch #{wid}", out[0])
        self.assertEqual(watch.active("w-stop"), [])
        self.assertEqual([r for r in clock.scheduled("w-stop") if r["kind"] == "watch"], [])


class RunningAWatch(unittest.TestCase):
    def test_the_question_goes_out_review_only_with_the_shape_and_since(self):
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-run")
            clock.tick(now=THU9, deliver=got)
            (send,) = fake.sends()
            self.assertEqual(send[send.index("--to") + 1], "claude:c-1")
            self.assertEqual(send[send.index("--mode") + 1], "review-only")
            self.assertIn("what must I reply to?", send[-1])
            self.assertIn("Only items since any time", send[-1])
            self.assertIn("- <title> | <link or -> |", send[-1])
            self.assertIn("send nothing and change nothing", send[-1])
            (r,) = store.open_relays("w-run")
            self.assertTrue(r["purpose"].startswith("watch:"))
            self.assertTrue(any("Watch #" in t and "queued" in t for t in got.texts("w-run")))
            # next run says since when
            fake.advance(r["message_id"], "completed", "- nothing")
            relay.follow(got)
            clock.tick(now=FRI9, deliver=got)
            self.assertIn("Only items since Thu 08 Oct 09:00", fake.sends()[1][-1])

    def test_items_become_tasks_once(self):
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-items")
            clock.tick(now=THU9, deliver=got)
            (r,) = store.open_relays("w-items")
            fake.advance(r["message_id"], "completed", ANSWER)
            relay.follow(got)
            text = got.texts("w-items")[-1]
            self.assertIn("2 new task(s)", text)
            self.assertIn("Reply to Dana about the Q4 plan", text)
            self.assertIn("could not read these lines", text)
            tasks = todo.open_tasks(THU9)
            self.assertEqual([t["source"] for t in tasks], ["mail", "mail"])
            dana = next(t for t in tasks if "Dana" in t["title"])
            self.assertEqual(dana["link"], "https://mail.example/t/101")
            self.assertEqual(dt.datetime.fromtimestamp(dana["due"]).strftime("%a"), "Fri")
            self.assertEqual(dana["why"], "she asked for a decision")
            # the same items again, plus one new
            clock.tick(now=FRI9, deliver=got)
            (r2,) = store.open_relays("w-items")
            fake.advance(r2["message_id"], "completed", ANSWER + "\n- Sign the timesheet | - | due today | friday")
            relay.follow(got)
            text = got.texts("w-items")[-1]
            self.assertIn("1 new task(s)", text)
            self.assertIn("2 already on your list", text)
            self.assertEqual(len(todo.open_tasks(FRI9)), 3)

    def test_nothing_new_is_said_plainly(self):
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-none")
            clock.tick(now=THU9, deliver=got)
            (r,) = store.open_relays("w-none")
            fake.advance(r["message_id"], "completed", "- nothing")
            relay.follow(got)
        self.assertTrue(got.texts("w-none")[-1].endswith("nothing new."))
        self.assertEqual(todo.open_tasks(THU9), [])

    def test_a_failed_answer_is_told_not_turned_into_tasks(self):
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-fail")
            clock.tick(now=THU9, deliver=got)
            (r,) = store.open_relays("w-fail")
            fake.advance(r["message_id"], "failed", "connector not authorised")
            relay.follow(got)
        self.assertIn("FAILED to answer — connector not authorised", got.texts("w-fail")[-1])
        self.assertEqual(todo.open_tasks(THU9), [])

    def test_a_failed_send_does_not_move_the_since_bound(self):
        """Found in review: last_run advanced before the send succeeded, so the next run
        asked 'since Thursday' although Thursday's run never reached the session."""
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-sendfail")
            with mock.patch.object(relay, "send", side_effect=relay.RelayError("bridge down")):
                clock.tick(now=THU9, deliver=got)
            self.assertEqual(fake.sends(), [])
            self.assertIn("refused", got.texts("w-sendfail")[-1])
            clock.tick(now=FRI9, deliver=got)
            (send,) = fake.sends()
            self.assertIn("Only items since any time", send[-1])

    def test_a_failed_answer_does_not_move_the_since_bound_but_a_good_one_does(self):
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-ansfail")
            clock.tick(now=THU9, deliver=got)
            (r,) = store.open_relays("w-ansfail")
            fake.advance(r["message_id"], "failed", "connector timed out")
            relay.follow(got)
            self.assertIn("asks again from the same point", got.texts("w-ansfail")[-1])
            clock.tick(now=FRI9, deliver=got)
            self.assertIn("Only items since any time", fake.sends()[1][-1])
            (r2,) = store.open_relays("w-ansfail")
            fake.advance(r2["message_id"], "completed", "- nothing")
            relay.follow(got)
            mon9 = dt.datetime(2026, 10, 12, 9, 0).timestamp()
            clock.tick(now=mon9, deliver=got)
            self.assertIn("Only items since Fri 09 Oct 09:00", fake.sends()[2][-1])
            out = ask("my watches", "w-ansfail")
            self.assertIn("last answered Fri 09 Oct 09:00", out[0])

    def test_a_date_that_does_not_exist_loses_neither_item_nor_checkpoint(self):
        """Found in review: '2026-02-30' raised inside parse_due, the whole answer was
        lost, and the checkpoint had already moved."""
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-baddate")
            clock.tick(now=THU9, deliver=got)
            (r,) = store.open_relays("w-baddate")
            fake.advance(r["message_id"], "completed",
                         "- First | https://example.com/1 | due | 2026-02-30\n"
                         "- Second | https://example.com/2 | important | -")
            relay.follow(got)
            tasks = todo.open_tasks(THU9)
            self.assertEqual(sorted(t["title"] for t in tasks), ["First", "Second"])
            self.assertIsNone(next(t for t in tasks if t["title"] == "First")["due"])
            self.assertIn("2 new task(s)", got.texts("w-baddate")[-1])
            (w,) = watch.active("w-baddate")
            self.assertEqual(w["last_ok"], THU9)

    def test_an_answer_the_watch_cannot_read_is_still_delivered_as_it_came(self):
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-crash")
            clock.tick(now=THU9, deliver=got)
            (r,) = store.open_relays("w-crash")
            fake.advance(r["message_id"], "completed", "- Only | https://example.com/1 | x | -")
            with mock.patch.object(watch, "absorb", side_effect=RuntimeError("boom")):
                relay.follow(got)
        text = got.texts("w-crash")[-1]
        self.assertIn("could not read this answer (RuntimeError)", text)
        self.assertIn("https://example.com/1", text)
        self.assertEqual(store.open_relays("w-crash"), [])

    def test_a_target_gone_from_the_registry_skips_the_run_and_says_so(self):
        got = Delivered()
        with world() as fake:
            ask("watch mail through the claude session ethan every weekday at 09:00: what must I reply to?", "w-gone")
            with mock.patch.object(bridge_registry, "sessions",
                                   return_value={"available": True, "sessions": [], "note": ""}):
                clock.tick(now=THU9, deliver=got)
        self.assertEqual(fake.sends(), [])
        self.assertIn("not registered with the bridge now", got.texts("w-gone")[-1])


if __name__ == "__main__":
    unittest.main()
