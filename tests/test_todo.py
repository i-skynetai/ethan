"""EH-065: one task list from every source, read and written by rules, no model."""
import datetime as dt
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import hands, llm, router, todo  # noqa: E402

NOW = dt.datetime(2026, 10, 7, 10, 0).timestamp()      # a Wednesday


def take(text, chat="t", now=NOW):
    out = []
    handled = todo.take(chat, text, out.append, "console", now=now)
    return handled, out


def clear():
    for t in todo.open_tasks(now=NOW + 10 ** 9):
        todo.set_state(t["id"], "dropped")


def stamp(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%a %d %H:%M")


class ReadingADate(unittest.TestCase):
    def test_days_times_and_dates(self):
        self.assertEqual(stamp(todo.parse_due("friday", NOW)), "Fri 09 23:59")
        self.assertEqual(stamp(todo.parse_due("tomorrow", NOW)), "Thu 08 23:59")
        self.assertEqual(stamp(todo.parse_due("tomorrow 9:00", NOW)), "Thu 08 09:00")
        self.assertEqual(stamp(todo.parse_due("17:00", NOW)), "Wed 07 17:00")
        self.assertEqual(stamp(todo.parse_due("9:00", NOW)), "Thu 08 09:00")     # today's is gone
        self.assertEqual(stamp(todo.parse_due("2026-10-10", NOW)), "Sat 10 23:59")
        self.assertEqual(todo.parse_due("in 2 hours", NOW), NOW + 7200)
        self.assertEqual(stamp(todo.parse_due("wednesday", NOW)), "Wed 14 23:59")  # next one, not today

    def test_nothing_readable_means_no_date(self):
        self.assertIsNone(todo.parse_due("soon", NOW))
        self.assertIsNone(todo.parse_due("the end of the quarter", NOW))

    def test_a_date_that_does_not_exist_is_unreadable_not_an_error(self):
        self.assertIsNone(todo.parse_due("2026-02-30", NOW))
        self.assertIsNone(todo.parse_due("2026-13-01", NOW))
        self.assertIsNone(todo.parse_due("2026-10-10 25:00", NOW))      # a time that does not exist
        self.assertIsNone(todo.parse_due("friday 17:60", NOW))
        self.assertIsNone(todo.parse_due("tomorrow 24:00", NOW))


class TheList(unittest.TestCase):
    def setUp(self):
        clear()

    def test_add_list_done(self):
        handled, out = take("add task: send the report by friday")
        self.assertTrue(handled)
        self.assertRegex(out[0], r"Task #\d+ added — send the report, due Fri 09 Oct\.")
        take("task: book the room by 15:00")
        take("todo: read the design note")
        handled, out = take("what should I do now?")
        lines = out[0].splitlines()
        self.assertEqual(lines[0], "3 open:")
        self.assertIn("book the room", lines[1])             # soonest first
        self.assertIn("send the report", lines[2])
        self.assertIn("no date — read the design note", lines[3])
        tid = int(lines[1].split()[0].lstrip("#"))
        handled, out = take(f"done #{tid}")
        self.assertIn(f"Task #{tid} done — book the room.", out[0])
        self.assertEqual(len(todo.open_tasks(NOW)), 2)
        handled, out = take(f"done #{tid}")
        self.assertIn("no open task", out[0])

    def test_overdue_is_flagged(self):
        take("add task: pay the invoice by 2026-10-01")
        handled, out = take("my tasks")
        self.assertIn("OVERDUE Thu 01 Oct — pay the invoice", out[0])

    def test_an_unreadable_date_sets_none_and_says_so(self):
        handled, out = take("add task: tidy the backlog by whenever")
        self.assertIn("could not read that date", out[0])
        self.assertIn("tidy the backlog by whenever", out[0])   # the words stay in the title

    def test_snooze_hides_until_then_returns(self):
        take("add task: call the bank")
        tid = todo.open_tasks(NOW)[0]["id"]
        handled, out = take(f"snooze task #{tid} for 2 hours")
        self.assertIn("snoozed until Wed 07 Oct 12:00", out[0])
        self.assertEqual(todo.open_tasks(NOW), [])
        self.assertEqual([t["id"] for t in todo.open_tasks(NOW + 7200)], [tid])
        handled, out = take(f"snooze #{tid} until friday 9:00")
        self.assertIn("Fri 09 Oct 09:00", out[0])

    def test_drop_and_the_source_is_untouched(self):
        tid, new = todo.add("Reply to the quarterly plan thread", source="mail",
                            link="https://mail.example/thread/42", why="asked for a decision")
        self.assertTrue(new)
        handled, out = take(f"drop task #{tid}")
        self.assertIn("Its source (mail) is untouched.", out[0])

    def test_the_same_item_from_a_source_is_merged(self):
        a, new_a = todo.add("Review MR !12", source="gitlab", link="https://git.example/mr/12")
        b, new_b = todo.add("Review MR !12 (updated title)", source="gitlab", link="https://git.example/mr/12")
        self.assertEqual((a, new_a, new_b), (b, True, False))
        c, new_c = todo.add("Review MR !12", source="you")                # another source: its own
        self.assertNotEqual(a, c)
        handled, out = take("add task: Review MR !12")
        self.assertIn(f"already on your list as task #{c}", out[0])

    def test_other_asks_are_not_the_lists(self):
        for text in ("fix the invoice bug", "what is running?", "remind me at 15:00 to call",
                     "tell me about tasks", "task force meeting"):
            handled, out = take(text)
            self.assertFalse(handled, text)
            self.assertEqual(out, [])


class ThroughTheRouter(unittest.TestCase):
    def test_list_asks_need_no_model_and_start_nothing(self):
        clear()
        with mock.patch.object(llm, "ask", side_effect=AssertionError("no model for the list")), \
                mock.patch.object(hands, "run", side_effect=AssertionError("no hand")):
            out = []
            router.handle("todo-router", "add task: write the handover by tomorrow", out.append, door="console")
            router.handle("todo-router", "my tasks", out.append, door="console")
        self.assertIn("Task #", out[0])
        self.assertIn("write the handover", out[2])
        self.assertEqual(sum(o.startswith(router.CLOSE_OUT) for o in out), 2)


if __name__ == "__main__":
    unittest.main()
