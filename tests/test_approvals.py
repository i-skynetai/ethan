"""EH-040: the yes before an act the policy marks ask — and every way a yes is refused."""
import os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ETHAN_STATE_DIR", tempfile.mkdtemp(prefix="ethan-test-state-"))

from ethan import approvals, bridge_registry, harvest, relay, router, store  # noqa: E402
from tests.test_policy import with_policy  # noqa: E402
from tests.test_relay import SESSIONS, FakeBridge  # noqa: E402
from tests.test_routing import stubbed  # noqa: E402

BUILD = {"kind": "build", "kb": "notes_kb", "hand": "claude", "steps": [], "search_query": "q", "reason": "stub"}
CHAIN = {"kind": "chain", "kb": "notes_kb", "hand": "auto", "search_query": "q", "reason": "stub",
         "steps": [{"hand": "claude", "kind": "build", "goal": "write it"},
                   {"hand": "codex", "kind": "review", "goal": "review it"}]}
ASK_CONSOLE = with_policy(**{"doors.console.build": "ask"})            # the shipped default, stated
ALLOW_CONSOLE = with_policy(**{"doors.console.build": "allow"})


def say(text, chat, door="console", scheduled=False):
    out = []
    router.handle(chat, text, out.append, door=door, scheduled=scheduled)
    return out


def last_approval(chat):
    rows = [r for r in approvals._rows("chat_id=?", (chat,))]
    return rows[-1] if rows else None


class AskingBeforeABuild(unittest.TestCase):
    def test_the_shipped_default_asks_and_an_explicit_allow_starts_at_once(self):
        with stubbed(BUILD, console_build="ask") as stub:
            out = say("write the summary", "a-default")
        self.assertEqual(stub.runs, [])
        self.assertTrue(any(o.startswith("Approval #") for o in out), out)
        with stubbed(BUILD) as stub, ALLOW_CONSOLE:
            out = say("write the summary", "a-allow")
        self.assertEqual(len(stub.runs), 1)
        self.assertNotIn("Approval #", out[0])

    def test_ask_records_the_exact_act_and_starts_nothing(self):
        with stubbed(BUILD) as stub, ASK_CONSOLE:
            out = say("write the summary", "a-ask")
        self.assertEqual(stub.runs, [])
        asked = next(o for o in out if o.startswith("Approval #"))
        self.assertIn("start claude as developer", asked)
        self.assertTrue(out[-1].startswith("Not closing"), out[-1])    # waiting is not "nothing pending"
        self.assertIn("approval", out[-1])
        row = last_approval("a-ask")
        self.assertEqual((row["state"], row["kind"], row["door"]), ("pending", "build", "console"))

    def test_approve_from_the_same_door_and_chat_runs_the_bound_brief_once(self):
        with stubbed(BUILD) as stub, ASK_CONSOLE:
            say("write the summary", "a-yes")
            aid = last_approval("a-yes")["id"]
            out = say(f"approve {aid}", "a-yes")
            self.assertEqual(len(stub.runs), 1)
            self.assertEqual(stub.runs[0]["brief"], __import__("json").loads(last_approval("a-yes")["payload"])["brief"])
            self.assertTrue(any("Task #" in o and "done" in o for o in out), out)
            out = say(f"approve {aid}", "a-yes")                      # replay
        self.assertEqual(len(stub.runs), 1)
        self.assertIn("already approved", out[0])

    def test_wrong_door_wrong_chat_and_scheduled_are_refused(self):
        with stubbed(BUILD) as stub, ASK_CONSOLE:
            say("write the summary", "a-door")
            aid = last_approval("a-door")["id"]
            out = say(f"approve {aid}", "a-door", door="telegram-private")
            self.assertIn("no approval", out[0])
            out = say(f"approve {aid}", "a-other-chat")
            self.assertIn("no approval", out[0])
            out = say(f"approve {aid}", "a-door", scheduled=True)
            self.assertIn("scheduled run cannot", out[0])
            self.assertEqual(stub.runs, [])
            self.assertEqual(last_approval("a-door")["state"], "pending")

    def test_deny_expiry_and_restart_each_end_it_with_nothing_done(self):
        with stubbed(BUILD) as stub, ASK_CONSOLE:
            say("write the summary", "a-deny")
            aid = last_approval("a-deny")["id"]
            out = say(f"deny {aid}", "a-deny")
            self.assertIn("denied", out[0])
            self.assertEqual(last_approval("a-deny")["state"], "denied")
            out = say(f"approve {aid}", "a-deny")
            self.assertIn("already denied", out[0])

            say("write the summary", "a-expire")
            aid = last_approval("a-expire")["id"]
            later = last_approval("a-expire")["expires"] + 1
            with mock.patch.object(approvals.time, "time", return_value=later):
                out = say(f"approve {aid}", "a-expire")
            self.assertIn("timed out", out[0])
            self.assertEqual(last_approval("a-expire")["state"], "expired")

            say("write the summary", "a-restart")
            aid = last_approval("a-restart")["id"]
            with mock.patch.object(approvals, "BOOT", last_approval("a-restart")["ts"] + 1):
                out = say(f"approve {aid}", "a-restart")
            self.assertIn("before Ethan last started", out[0])
            self.assertEqual(last_approval("a-restart")["state"], "expired")
            self.assertEqual(stub.runs, [])

    def test_the_current_policy_is_checked_again_at_execution(self):
        with stubbed(BUILD) as stub:
            with ASK_CONSOLE:
                say("write the summary", "a-policy")
                aid = last_approval("a-policy")["id"]
            with with_policy(**{"doors.console.build": False}):
                out = say(f"approve {aid}", "a-policy")
        self.assertEqual(stub.runs, [])
        self.assertIn("may not start a build now", out[0])
        self.assertIn("refused", last_approval("a-policy")["note"])

    def test_telegram_builds_wait_by_default(self):
        with stubbed(BUILD) as stub:
            out = say("write the summary", "a-tg", door="telegram-private")
        self.assertEqual(stub.runs, [])
        self.assertTrue(any(o.startswith("Approval #") for o in out), out)

    def test_a_chain_waits_as_one_approval_and_runs_in_order(self):
        with stubbed(CHAIN) as stub, ASK_CONSOLE:
            out = say("write it then review it", "a-chain")
            self.assertEqual(stub.runs, [])
            self.assertIn("2 steps", next(o for o in out if o.startswith("Approval #")))
            aid = last_approval("a-chain")["id"]
            say(f"approve {aid}", "a-chain")
        self.assertEqual([r["hand"] for r in stub.runs], ["claude", "codex"])

    def test_list_pending_shows_only_what_a_display_may_see(self):
        with stubbed(BUILD), ASK_CONSOLE:
            say("write the summary about the secret project", "a-list")
            rows = approvals.list_pending("a-list", "console")
            self.assertEqual(len(rows), 1)
            self.assertEqual(sorted(rows[0]), ["created", "expires", "id", "kind", "state", "summary"])
            self.assertEqual((rows[0]["kind"], rows[0]["state"]), ("build", "pending"))
            self.assertIn("start claude as developer", rows[0]["summary"])
            self.assertNotIn("# Task", rows[0]["summary"])             # never the brief
            self.assertEqual(approvals.list_pending("a-list", "telegram-private"), [])   # another door sees nothing
            self.assertEqual(approvals.list_pending("a-list", "console"), rows)           # read-only: same again
            say(f"deny {rows[0]['id']}", "a-list")
            self.assertEqual(approvals.list_pending("a-list", "console"), [])

    def test_a_deny_or_expiry_that_loses_the_race_to_an_approve_changes_nothing(self):
        """Found in review: deny and expiry moved the row unconditionally after reading
        it as pending, so an approve in between ran the act and was then reported as
        denied. Every transition from pending is conditional now."""
        with stubbed(BUILD) as stub, ASK_CONSOLE:
            say("write the summary", "a-race")
            snapshot = last_approval("a-race")                       # read as pending…
            say(f"approve {snapshot['id']}", "a-race")               # …approved and run meanwhile
            self.assertEqual(len(stub.runs), 1)
            out = []
            self.assertFalse(approvals._deny(snapshot, out.append))   # the late deny loses
            self.assertIn("already approved", out[0])
            self.assertFalse(approvals._expire(snapshot, "timed out"))  # so does a late expiry
            row = last_approval("a-race")
            self.assertEqual(row["state"], "approved")
            self.assertIn("task #", row["note"])
            self.assertEqual(len(stub.runs), 1)

    def test_the_close_out_counts_a_waiting_approval(self):
        with stubbed(BUILD), ASK_CONSOLE:
            say("write the summary", "a-close")
            ok, why = harvest.can_close("a-close")
            self.assertFalse(ok)
            self.assertIn("approval", why)
            say(f"deny {last_approval('a-close')['id']}", "a-close")
            self.assertTrue(harvest.can_close("a-close")[0])


class AskingBeforeAnImplementationRelay(unittest.TestCase):
    def setUp(self):
        for r in store.open_relays():
            store.update_relay(r["id"], state="dropped", note="test isolation")
        self.reg = {"available": True, "sessions": SESSIONS, "note": ""}

    def test_implementation_waits_and_is_sent_only_on_approve(self):
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            out = say("tell the codex session codex-ethan to implement EH-1", "r-impl")
            asked = next(o for o in out if o.startswith("Approval #"))
            self.assertIn("implementation rights", asked)
            self.assertEqual(fake.sends(), [])
            self.assertEqual(store.open_relays("r-impl"), [])          # not open, not followed
            aid = last_approval("r-impl")["id"]
            say(f"approve {aid}", "r-impl")
            (send,) = fake.sends()
            self.assertEqual(send[send.index("--mode") + 1], "implementation")
            self.assertEqual(store.open_relays("r-impl")[0]["state"], "queued")

    def test_deny_drops_the_relay_and_review_only_never_waits(self):
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            say("tell the codex session codex-ethan to implement EH-1", "r-deny")
            aid = last_approval("r-deny")["id"]
            say(f"deny {aid}", "r-deny")
            self.assertEqual(fake.sends(), [])
            rows = [r for r in store.recent_relays(20) if r["chat_id"] == "r-deny"]
            self.assertEqual(rows[0]["state"], "dropped")
            say("ask the codex session codex-ethan to look at EH-1", "r-deny")
            (send,) = fake.sends()
            self.assertEqual(send[send.index("--mode") + 1], "review-only")

    def test_policy_changed_to_never_before_the_yes_refuses(self):
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            say("tell the codex session codex-ethan to implement EH-1", "r-impl-never")
            aid = last_approval("r-impl-never")["id"]
            with with_policy(**{"actions.relay_implementation": "never"}):
                out = say(f"approve {aid}", "r-impl-never")
            self.assertEqual(fake.sends(), [])
            self.assertIn("never", out[0])

    def test_a_direct_dispatch_cannot_skip_the_asking_step(self):
        """Found in review: relay.dispatch went straight to the send; the gate lives at
        the one send boundary now, whatever path led there."""
        target = next(s for s in SESSIONS if s["name"] == "codex-ethan")
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            told = relay.dispatch("r-direct", "console", target, "implement EH-1", "implementation")
            self.assertIn("Approval #", told)
            self.assertEqual(fake.sends(), [])
            rows = [r for r in store.recent_relays(20) if r["chat_id"] == "r-direct"]
            self.assertEqual(rows[0]["state"], "awaiting-approval")
            # a recovery after a restart of an unapproved implementation row is refused, not sent
            store.update_relay(rows[0]["id"], state="sending", bridge_key="k-direct")
            relay.follow(lambda c, d, t: None, recover=True)
            self.assertEqual(fake.sends(), [])
            self.assertEqual(store.relay(rows[0]["id"])["state"], "refused")

    def test_the_yes_runs_the_approved_snapshot_not_a_row_that_changed(self):
        """Found in review: the executor read the mutable relay row at the yes, and a
        note saying "approved" counted as proof. The approval's payload is compared
        field by field, and the binding is the approval row written on the relay."""
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            say("tell the codex session codex-ethan to implement EH-1", "r-tamper")
            aid = last_approval("r-tamper")["id"]
            (row,) = [r for r in store.recent_relays(20) if r["chat_id"] == "r-tamper"]
            with store._LOCK:                                              # the ask changes under the approval
                store.db().execute("UPDATE relays SET ask=? WHERE id=?", ("implement EH-1 and push to main", row["id"]))
                store.db().commit()
            out = say(f"approve {aid}", "r-tamper")
            self.assertEqual(fake.sends(), [])
            self.assertTrue(any("not what you approved" in o for o in out), out)
            self.assertEqual(store.relay(row["id"])["state"], "refused")
            # a forged note is not an approval: an unbound implementation row never goes out
            rid = store.add_relay("r-forged", "console", "implement EH-2", "implementation")
            store.update_relay(rid, note="approved", state="sending", bridge_key="k-forged",
                               target_ref="codex:x-1", target="codex:codex-ethan")
            relay.follow(lambda c, d, t: None, recover=True)
            self.assertEqual(fake.sends(), [])
            self.assertEqual(store.relay(rid)["state"], "refused")

    def test_the_approved_target_is_bound_too_so_a_redirected_row_is_not_recovered(self):
        """Found in review: the binding compared text, door, chat and mode but not the
        session the approval named; a row redirected to another session before a
        recovery would have gone there."""
        other = next(s for s in SESSIONS if s["name"] == "review")          # a claude session, not codex-ethan
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            say("tell the codex session codex-ethan to implement EH-3", "r-redirect")
            say(f"approve {last_approval('r-redirect')['id']}", "r-redirect")
            (send,) = fake.sends()
            self.assertEqual(send[send.index("--to") + 1], "codex:x-1")
            (row,) = [r for r in store.recent_relays(20) if r["chat_id"] == "r-redirect"]
            self.assertIsNotNone(relay._approved_binding(row))                # bound, as approved
            store.update_relay(row["id"], state="sending", message_id=None,
                               target_ref=relay.ref_of(other), target=relay._label(other))
            self.assertIsNone(relay._approved_binding(store.relay(row["id"])))  # points elsewhere now
            fake.calls.clear()
            relay.follow(lambda c, d, t: None, recover=True)
            self.assertEqual(fake.sends(), [])
            self.assertEqual(store.relay(row["id"])["state"], "refused")

    def test_a_clarified_implementation_relay_also_waits(self):
        with mock.patch.object(bridge_registry, "sessions", return_value=self.reg), \
                mock.patch.object(relay, "_bridge", FakeBridge()) as fake, mock.patch.object(relay, "_REGISTERED", []):
            out = say("ask the claude session to implement EH-1", "r-clarify")
            self.assertIn("Which session", out[0])
            out = say("1", "r-clarify")
            self.assertTrue(any(o.startswith("Approval #") for o in out), out)
            self.assertEqual(fake.sends(), [])


if __name__ == "__main__":
    unittest.main()
