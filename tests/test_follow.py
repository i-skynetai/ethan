"""EH-059: a relay is followed to its end, and nothing is sent twice after a restart.

The fake bridge here keeps its own little message table, so a relay can be walked
through queued → delivered → acknowledged → completed, and a "duplicate" refusal
behaves as the real bridge's does.
"""
import contextlib, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import bridge_registry, hands, llm, relay, router, store  # noqa: E402
from tests.test_relay import SESSIONS  # noqa: E402


class StatefulBridge:
    """Messages by id, with a state the test moves on; `--key` is honoured."""

    def __init__(self):
        self.msgs, self.by_key, self.calls, self.inbox, self.down = {}, {}, [], [], False

    def __call__(self, *args, timeout=60):
        self.calls.append(args)
        if self.down:
            raise relay.RelayError("the bridge did not answer: down")
        cmd = args[0]
        if cmd == "register":
            return {"agent": "app"}
        if cmd == "send":
            key = args[args.index("--key") + 1]
            if key in self.by_key:
                raise relay.RelayError(f"duplicate: this exact request is already message {self.by_key[key]}")
            mid = f"m_{len(self.msgs) + 1:03d}"
            self.msgs[mid] = {"id": mid, "state": "queued", "result": None, "failure": None,
                              "text": args[-1], "to": args[args.index("--to") + 1]}
            self.by_key[key] = mid
            return dict(self.msgs[mid])
        if cmd == "status":
            if args[1] not in self.msgs:               # as the real bridge answers
                raise relay.RelayError(f"no message {args[1]}")
            return dict(self.msgs[args[1]])
        if cmd == "inbox":
            out, self.inbox = self.inbox, []
            return out
        if cmd == "ack":
            return {"state": "completed"}
        raise AssertionError(f"unexpected bridge call {args}")

    def advance(self, mid, state, result=None):
        self.msgs[mid]["state"] = state
        if state == "completed":
            self.msgs[mid]["result"] = result
            self.inbox.append({"id": f"r_{mid}", "reply_to": mid, "state": "queued"})
        if state == "failed":
            self.msgs[mid]["failure"] = result

    def sends(self):
        return [a for a in self.calls if a[0] == "send"]


@contextlib.contextmanager
def bridge():
    fake = StatefulBridge()
    reg = {"available": True, "sessions": SESSIONS, "note": ""}
    for r in store.open_relays():                  # rows other test modules left open
        store.update_relay(r["id"], state="dropped", note="test isolation")
    with mock.patch.object(bridge_registry, "sessions", return_value=reg), \
            mock.patch.object(relay, "_bridge", fake), \
            mock.patch.object(relay, "_REGISTERED", []), \
            mock.patch.object(llm, "ask", side_effect=AssertionError("no model call")), \
            mock.patch.object(hands, "run", side_effect=AssertionError("no hand")):
        yield fake


def ask(text, chat):
    out = []
    router.handle(chat, text, out.append, door="console")
    return out


def relays_of(chat):
    return [r for r in store.recent_relays(50) if r["chat_id"] == chat]


class Delivered:
    """Collects what `follow` hands back to a conversation."""

    def __init__(self):
        self.items = []

    def __call__(self, chat_id, door, text):
        self.items.append((chat_id, door, text))

    def texts(self, chat):
        return [t for c, _, t in self.items if c == chat]


class FollowToTheEnd(unittest.TestCase):
    def test_each_state_change_is_told_once_and_the_answer_arrives(self):
        got = Delivered()
        with bridge() as fake:
            ask("ask the codex session codex-ethan to look at EH-023", "f-end")
            (r,) = relays_of("f-end")
            mid = r["message_id"]
            self.assertEqual(relay.follow(got), [])            # nothing changed yet
            fake.advance(mid, "delivered")
            relay.follow(got)
            fake.advance(mid, "acknowledged")
            relay.follow(got)
            relay.follow(got)                                   # same state again: silence
            fake.advance(mid, "completed", "two findings, no blockers")
            relay.follow(got)
        texts = got.texts("f-end")
        self.assertEqual(len(texts), 3, texts)
        self.assertIn("not the same as done", texts[0])
        self.assertIn("has started on it", texts[1])
        self.assertIn("answered by codex:codex-ethan", texts[2])
        self.assertIn("two findings, no blockers", texts[2])
        (r,) = relays_of("f-end")
        self.assertEqual((r["state"], r["result"]), ("completed", "two findings, no blockers"))
        self.assertEqual(store.open_relays("f-end"), [])
        self.assertTrue(any(c[0] == "ack" for c in fake.calls))   # the reply was acknowledged

    def test_a_failed_relay_says_why(self):
        got = Delivered()
        with bridge() as fake:
            ask("ask the codex session codex-ethan to look at EH-023", "f-fail")
            (r,) = relays_of("f-fail")
            fake.advance(r["message_id"], "failed", "codex exec failed: sandbox refused")
            relay.follow(got)
        (text,) = got.texts("f-fail")
        self.assertIn("FAILED", text)
        self.assertIn("sandbox refused", text)
        self.assertEqual(relays_of("f-fail")[0]["state"], "failed")

    def test_the_answer_lands_in_the_asking_conversations_reply_queue(self):
        with bridge() as fake:
            ask("ask the codex session codex-ethan to look at EH-023", "f-queue")
            (r,) = relays_of("f-queue")
            fake.advance(r["message_id"], "completed", "done")
            relay.follow()                                      # the default delivery
        texts = [x["text"] for x in store.replies_since("f-queue")]
        self.assertTrue(any("answered by" in t and "done" in t for t in texts), texts)

    def test_the_close_out_opens_once_the_relay_is_answered(self):
        from ethan import harvest
        with bridge() as fake:
            ask("ask the codex session codex-ethan to look at EH-023", "f-close")
            self.assertFalse(harvest.can_close("f-close")[0])
            fake.advance(relays_of("f-close")[0]["message_id"], "completed", "ok")
            relay.follow(Delivered())
            self.assertTrue(harvest.can_close("f-close")[0])


class AfterARestart(unittest.TestCase):
    def test_a_relay_sent_but_not_recorded_is_recovered_not_resent(self):
        with bridge() as fake:
            ask("ask the codex session codex-ethan to look at EH-023", "r-sent")
            (r,) = relays_of("r-sent")
            # a crash right after the bridge accepted it: the id never reached the ledger
            store.update_relay(r["id"], state="sending", message_id=None)
            self.assertEqual(relay.follow(Delivered()), [])        # a periodic pass: in flight
            self.assertEqual(len(fake.sends()), 1)
            changed = relay.follow(Delivered(), recover=True)      # the pass after a start
        self.assertEqual(len(fake.sends()), 2)                   # the retry carries the SAME key
        self.assertEqual(fake.sends()[0][fake.sends()[0].index("--key") + 1],
                         fake.sends()[1][fake.sends()[1].index("--key") + 1])
        self.assertEqual(len(fake.msgs), 1)                      # the bridge holds one message
        (r,) = relays_of("r-sent")
        self.assertEqual((r["state"], r["message_id"]), ("queued", "m_001"))
        self.assertIn("recovered", r["note"])
        self.assertEqual([c["id"] for c in changed], [r["id"]])

    def test_a_relay_that_never_reached_the_bridge_is_sent_once_now(self):
        with bridge() as fake:
            ask("ask the codex session codex-ethan to look at EH-023", "r-never")
            (r,) = relays_of("r-never")
            fake.msgs.clear(); fake.by_key.clear(); fake.calls.clear()   # the bridge never saw it
            store.update_relay(r["id"], state="sending", message_id=None)
            relay.follow(Delivered(), recover=True)
        self.assertEqual(len(fake.sends()), 1)
        (r,) = relays_of("r-never")
        self.assertEqual((r["state"], r["message_id"]), ("queued", "m_001"))
        self.assertEqual(fake.msgs["m_001"]["to"], "codex:x-1")   # the saved ref, not the registry

    def test_a_bridge_that_is_down_leaves_the_row_open_and_says_so(self):
        got = Delivered()
        with bridge() as fake:
            ask("ask the codex session codex-ethan to look at EH-023", "r-down")
            fake.down = True
            self.assertEqual(relay.follow(got), [])
            (r,) = relays_of("r-down")
            self.assertEqual(r["state"], "queued")
            self.assertIn("not reachable", r["note"])
            fake.down = False
            fake.advance(r["message_id"], "completed", "late but here")
            relay.follow(got)
        self.assertIn("late but here", got.texts("r-down")[-1])

    def test_the_follower_loop_runs_and_stops(self):
        import threading
        stop = threading.Event()
        with bridge() as fake, mock.patch.object(relay, "cfg", return_value={"relay_poll_sec": 0}):
            t = threading.Thread(target=relay.follower, args=(stop,))
            t.start()
            for _ in range(200):
                if any(c[0] == "inbox" for c in fake.calls):
                    break
                threading.Event().wait(0.01)
            stop.set()
            t.join(timeout=2)
        self.assertFalse(t.is_alive())
        self.assertTrue(any(c[0] == "inbox" for c in fake.calls))


if __name__ == "__main__":
    unittest.main()
