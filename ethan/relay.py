"""Relay — pass an ask to a coding session that is already running.

Some work belongs with a session that is already open and already has the context.
Ethan passes the ask through a local message bridge (agent-bridge) and records the
bridge's message id. It never starts a session and never wakes a closed one: a
target that is not reading its inbox keeps the message queued, and Ethan says so.
Starting new work is `sky build`'s job, in `hands.py`, and a relay never reaches it.

The bridge is optional. Ethan finds it through `ETHAN_BRIDGE_DIR` (the bridge's
checkout) and runs its command line as a separate process with no shell, so the text
of an ask is never parsed by a shell.
"""
import json, os, re, subprocess, sys, time, uuid
from . import bridge_registry, identity, policy, store
from .util import cfg, log, state_dir

#: The name Ethan registers under in the bridge, as an app that polls for replies.
APP = "ethan"

AGENTS = ("claude", "codex")

# A relay ask opens with an instruction to someone else ("ask …", "tell …"), never to
# Ethan ("tell me …"), and names a session: the word itself or a registered name.
_VERB = re.compile(r"^\s*(?:please\s+|ethan,?\s+)?(ask|tell|message|send|pass|forward|hand|relay|have)\s+(?!me\b|us\b)", re.I)
_SESSION = re.compile(r"\bsessions?\b", re.I)
# Implementation hands a session ownership of the folder, so it must be said outright:
# "implement", "implementation mode" or "own it". "the implementation plan" is not it.
_IMPLEMENT = re.compile(r"\b(implement|implementation mode|you own|owns? (?:it|this|the work))\b", re.I)
_CANCEL = re.compile(r"^\s*(cancel|never ?mind|forget it|don'?t send|do not send)\b", re.I)


class RelayError(Exception):
    """The bridge refused or could not be reached. The text is shown as it is."""


# ── the bridge, as a separate process ───────────────────────────────────────
def bridge_dir():
    return os.environ.get("ETHAN_BRIDGE_DIR") or None


def _bridge(*args, timeout=60):
    where = bridge_dir()
    if not where:
        raise RelayError("no message bridge is configured (set ETHAN_BRIDGE_DIR in .env)")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [where, env.get("PYTHONPATH")]))
    env.setdefault("PYTHONUTF8", "1")
    try:
        p = subprocess.run([sys.executable, "-m", "agent_bridge.cli", *args], capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RelayError(f"the bridge did not answer: {e}")
    if p.returncode != 0:
        raise RelayError((p.stderr or p.stdout).strip().removeprefix("agent-bridge: ") or "the bridge refused")
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise RelayError(f"the bridge printed something that is not JSON: {p.stdout[:200]}")


_REGISTERED = []


def _register_app():
    """Ethan is a sender in the bridge, so replies come back to Ethan. Once per process."""
    if not _REGISTERED:
        _bridge("register", "app", APP, "--project", state_dir())
        _REGISTERED.append(True)


def ref_of(target):
    """How the bridge addresses a session: agent and native id, never a name that could
    be shared."""
    return f"{target['agent']}:{target.get('native_id') or target['name']}"


def send(ref, text, mode, key):
    _register_app()
    return _bridge("send", "--from", f"app:{APP}", "--to", ref, "--mode", mode, "--key", key, text)


# ── which ask is a relay, and to whom ──────────────────────────────────────
def allowed(door):
    """A door may relay only when the policy says so. Telegram is reachable from a
    phone, so by default it cannot put work in front of a coding session."""
    return policy.may_relay(door)


_TO_AFTER = ("send", "pass", "forward", "hand", "relay")   # "send this TO <session>: …"


def addressee(text):
    """The part of the ask that says who it is for. "ask the codex session to review
    X" is for "the codex session"; "send this to codex-ethan: check X" is for
    "codex-ethan". The rest is the work, and a session name in the work ("review")
    must not choose the target."""
    m = _VERB.match(text)
    if not m:
        return ""
    rest = text[m.end():]
    head, to, tail = rest.partition(" to ")
    if m.group(1).lower() in _TO_AFTER:
        return re.split(r"[:,]", tail, 1)[0] if to else ""
    return head


def _named(text, sessions):
    low = text.lower()
    return [s for s in sessions
            if re.search(r"(?<![\w-])" + re.escape(s["name"].lower()) + r"(?![\w-])", low)]


def wants_relay(text, sessions):
    who = addressee(text)
    return bool(who and (_SESSION.search(who) or _named(who, sessions)))


def targets(text, sessions, cwd=None):
    """The sessions this ask could mean. One is a decision; more or none is a question."""
    sessions = [s for s in sessions if s["agent"] in AGENTS]
    who = addressee(text) or text
    agent = [a for a in AGENTS if re.search(rf"\b{a}\b", who.lower())]
    if len(agent) == 1:
        sessions = [s for s in sessions if s["agent"] == agent[0]]
    pool = _named(who, sessions) or sessions
    if cwd and len(pool) > 1:
        here = os.path.normcase(os.path.abspath(cwd))
        inside = [s for s in pool if s.get("project") and
                  (here + os.sep).startswith(os.path.normcase(os.path.abspath(s["project"])) + os.sep)]
        pool = inside or pool
    return pool


def _mode(text):
    """Review-only unless the ask says to implement AND the policy lets an explicit ask
    do that ("ask"). Under "never", the ask is still relayed, review-only."""
    if _IMPLEMENT.search(text) and policy.action("relay_implementation") in ("allow", "ask"):
        return "implementation"
    return "review-only"


def _label(s):
    return f"{s['agent']}:{s['name']}"


def _seen(s):
    """When the bridge last heard from a session. Reading an inbox refreshes it too,
    so it never shows that the session is open now, and the words do not claim it."""
    if not s.get("last_seen"):
        return "the bridge has not heard from it"
    mins = int((time.time() - s["last_seen"]) // 60)
    when = f"{mins} min ago" if mins else "within the last minute"
    return f"the bridge last heard from it {when}, which does not show it is open now"


# ── the conversation ───────────────────────────────────────────────────────
def take(chat_id, text, reply, door, cwd=None):
    """Handle the ask when it is Ethan's to relay, and say whether it was.

    An ask is a relay's when it answers "which session did you mean?", or when it
    tells Ethan to pass something to a session. An open question that the next ask
    does not answer is dropped, said so, and the ask is routed as usual."""
    question = store.open_question(chat_id)
    if question:
        pool = json.loads(question["candidates"] or "[]")
        if _CANCEL.match(text):
            store.update_relay(question["id"], state="dropped", note="cancelled")
            reply("Cancelled. Nothing was sent.")
            return True
        pick = _pick(text, pool)
        if pick:
            _send(question["id"], pick, reply)
            return True
        store.update_relay(question["id"], state="dropped", note="the next ask named no candidate")
        reply(f"(I dropped relay #{question['id']}: that does not name one of the sessions I listed, "
              "and nothing was sent.)")
    if not _VERB.match(text):                    # most asks: no need to read the registry
        return False
    reg = bridge_registry.sessions()
    if not wants_relay(text, reg["sessions"]):
        return False
    _relay(chat_id, text, reply, door, cwd, reg)
    return True


def _pick(text, pool):
    m = re.match(r"\s*#?(\d+)\s*\.?\s*$", text)
    if m:
        n = int(m.group(1))
        return pool[n - 1] if 1 <= n <= len(pool) else None
    named = _named(text, pool)
    return named[0] if len(named) == 1 else None


def _relay(chat_id, text, reply, door, cwd, reg):
    if not allowed(door):
        reply(f"I do not pass work to coding sessions from the {door} door. "
              "Ask from the console or the command line.")
        return
    if not policy.allowed("relay_review_only"):
        reply(policy.refusal("relay_review_only", "I may not pass asks to coding sessions") + " Nothing was sent.")
        return
    if not reg["available"]:
        reply(f"I cannot reach a running session: {reg['note']} Nothing was sent, and nothing new was started.")
        return
    pool = targets(text, reg["sessions"], cwd)
    if len(pool) == 1:
        return _send(store.add_relay(chat_id, door, text, _mode(text)), pool[0], reply)
    if not pool:
        rid = store.add_relay(chat_id, door, text, _mode(text))
        store.update_relay(rid, state="dropped", note="no registered session matched")
        reply("No registered Claude or Codex session matches that, so I sent nothing and started nothing. "
              "`show my agents` lists the sessions I can reach.")
        return
    store.add_relay(chat_id, door, text, _mode(text), candidates=pool)
    lines = "\n".join(f"{i}. {_label(s)} · {s.get('project') or '?'} · {_seen(s)}"
                      for i, s in enumerate(pool, 1))
    reply(f"Which session should get this? I have not sent anything yet.\n{lines}\n"
          "Answer with the number or the name, or say cancel.")


def _text_of(row):
    return f"{row['ask']}\n\n(Passed on by {identity.stamp(row['door'])}.)"


def dispatch(chat_id, door, target, text, mode, purpose=None):
    """Send a relay that no door asked for in so many words — a watch's question, for
    example. Returns what to tell the person. `purpose` tags the row so `follow` knows
    who reads the answer."""
    rid = store.add_relay(chat_id, door, text, mode, purpose=purpose)
    return _dispatch_row(rid, target)


def _send(rid, target, reply):
    reply(_dispatch_row(rid, target))


def _gate(row):
    """The one check every send goes through, whatever path led here — a fresh ask,
    an answer to "which session?", a watch at its time, a recovery after a restart.
    It reads the door and the policy as they are NOW, not as they were when the ask was
    made. Returns why the send is refused, or None; may lower the mode."""
    if not policy.may_relay(row["door"]):
        return f"the {row['door']} door may not pass work to coding sessions"
    if not policy.allowed("relay_review_only"):
        return policy.refusal("relay_review_only", "I may not pass asks to coding sessions")
    if row["mode"] == "implementation" and policy.action("relay_implementation") == "never":
        store.update_relay(row["id"], mode="review-only",
                           note="implementation is never in the policy; sent review-only")
        row["mode"] = "review-only"
    return None


def _dispatch_row(rid, target):
    """The intent, the target and the dedupe key are saved BEFORE the bridge is called.
    A crash between the send and saving the message id leaves the row at `sending`, and
    `follow` recovers it by sending the same key again: the bridge refuses the duplicate
    and names the message it already has."""
    row = store.relay(rid)
    why = _gate(row)
    if why:
        store.update_relay(rid, state="refused", target=_label(target), note=why)
        return f"Not sent to {_label(target)}: {why}. Nothing new was started."
    key = f"relay-{rid}-{uuid.uuid4().hex[:8]}"
    store.update_relay(rid, state="sending", target=_label(target), target_ref=ref_of(target), bridge_key=key)
    try:
        msg = send(ref_of(target), _text_of(row), row["mode"], key)
    except RelayError as e:
        store.update_relay(rid, state="send-failed", note=str(e))
        return f"The bridge refused the message to {_label(target)}: {e}\nNothing was sent, and nothing new was started."
    store.update_relay(rid, state=msg["state"], message_id=msg["id"], note=msg.get("note") or "")
    log(f"relay #{rid}: {msg['id']} to {_label(target)} is {msg['state']}")
    return (f"Relay #{rid}: sent to {_label(target)} as {msg['id']} ({row['mode']}). "
            f"{_meaning(msg['state'], target)}"
            + ("" if row["mode"] == "implementation" or row.get("purpose") else
               " It is review-only, so the session will not change files; say 'implement' to hand it the work."))


# ── following a relay to its end ────────────────────────────────────────────
_DUPLICATE = re.compile(r"already message (m_[0-9a-f]+)")


def deliver_reply(chat_id, door, text):
    """Where a relay's answer goes: the conversation that asked, and your phone when
    you are away (see `reach.py`). The console and the CLI read the conversation."""
    from . import reach
    reach.tell(chat_id, door, text, urgent=False)


def follow(deliver=deliver_reply, recover=False):
    """One pass over every relay that is not finished. Safe to run at any time, as
    often as wanted, and first thing after a restart.

    - A row still at `sending` is recovered (see `_send`), never sent again blind —
      but only when `recover` is set, which the follower does on its first pass after
      a start. In a running service a `sending` row is a send in flight on another
      thread, not a crash, and is left alone.
    - Every other open row is checked against the bridge; each change of state is told
      to the conversation that asked, in plain words, and a completed or failed relay
      delivers its answer.
    - Replies in Ethan's own bridge inbox are acknowledged, so they do not pile up.
    Returns the rows it changed."""
    changed = []
    for r in store.open_relays():
        touched = False
        try:
            if r["state"] == "sending":
                if not recover:
                    continue
                r = _recover(r, deliver)
                if r is None:
                    continue
                touched = True
            if r.get("message_id"):
                after = _check(r, deliver)
                if after:
                    r, touched = after, True
            if touched:
                changed.append(r)
        except RelayError as e:
            log(f"relay #{r['id']}: bridge not reachable — {e}")
            store.update_relay(r["id"], note=f"bridge not reachable at last check: {e}")
    try:
        _drain_inbox()
    except RelayError as e:
        log(f"relay inbox: {e}")
    return changed


def _recover(r, deliver=deliver_reply):
    why = _gate(r)
    if why:                                       # the rules changed while Ethan was down
        store.update_relay(r["id"], state="refused", note=f"after a restart: {why}")
        deliver(r["chat_id"], r["door"], f"Relay #{r['id']} was not sent after the restart: {why}.")
        return None
    try:
        msg = send(r["target_ref"], _text_of(r), r["mode"], r["bridge_key"])
    except RelayError as e:
        m = _DUPLICATE.search(str(e))
        if not m:
            store.update_relay(r["id"], state="send-failed", note=f"after a restart: {e}")
            return None
        store.update_relay(r["id"], message_id=m.group(1), state="queued",
                           note="recovered after a restart: the bridge already had it")
        log(f"relay #{r['id']}: recovered as {m.group(1)}, not sent again")
        return store.relay(r["id"])
    store.update_relay(r["id"], message_id=msg["id"], state=msg["state"], note=msg.get("note") or "")
    log(f"relay #{r['id']}: sent after a restart as {msg['id']}")
    return store.relay(r["id"])


def _check(r, deliver):
    status = _bridge("status", r["message_id"], timeout=30)
    state = status.get("state")
    if state == r["state"]:
        return None
    fields = {"state": state}
    if state == "completed":
        fields["result"] = status.get("result") or ""
    if state == "failed":
        fields["result"] = status.get("failure") or ""
    store.update_relay(r["id"], **fields)
    log(f"relay #{r['id']}: {r['message_id']} is now {state}")
    if (r.get("purpose") or "").startswith("watch:") and state in ("completed", "failed"):
        from . import watch                       # late: watch imports this module
        try:
            text = watch.absorb(r, state, fields.get("result"))
        except Exception as e:                    # the answer is already final: never lose it
            log(f"relay #{r['id']}: watch could not read the answer ({type(e).__name__}: {e})")
            text = (f"Relay #{r['id']}: the watch could not read this answer ({type(e).__name__}), "
                    f"so here it is as it came:\n{(fields.get('result') or '')[-3000:]}")
        deliver(r["chat_id"], r["door"], text)
    else:
        deliver(r["chat_id"], r["door"], _update_text(r, state, fields.get("result")))
    return store.relay(r["id"])


def _update_text(r, state, result):
    who = r["target"]
    if state == "completed":
        return f"Relay #{r['id']} answered by {who}:\n{(result or '(no text)')[-3000:]}"
    if state == "failed":
        return f"Relay #{r['id']} to {who} FAILED: {(result or 'no reason given')[-1500:]}"
    if state == "acknowledged":
        return f"Relay #{r['id']}: {who} has started on it."
    if state == "delivered":
        return f"Relay #{r['id']}: delivered to {who}, which is not the same as done."
    return f"Relay #{r['id']}: now {state}."


def _drain_inbox():
    msgs = _bridge("inbox", f"app:{APP}", timeout=30)
    if not isinstance(msgs, list):                # the bridge answers a list; anything else is not an inbox
        return
    for m in msgs:
        if isinstance(m, dict) and m.get("reply_to"):
            _bridge("ack", f"app:{APP}", m["id"], timeout=30)


def follower(stop=None):
    """The background loop: `follow` every `relay_poll_sec`, until `stop` is set."""
    import threading
    stop = stop or threading.Event()
    every = int(cfg("ethan.json").get("relay_poll_sec", 30))
    first = True                                  # the pass after a start may recover
    while not stop.is_set():
        try:
            follow(recover=first)
            first = False
        except Exception as e:                   # the loop must outlive any one bad pass
            log(f"relay follower: {type(e).__name__}: {e}")
        stop.wait(every)


def _meaning(state, target):
    """What a bridge state means, in words that do not promise more than it does."""
    if state == "queued":
        return (f"It is queued, not read: {_label(target)} gets it when that session next reads its inbox "
                f"({_seen(target)}).")
    if state == "delivered":
        return "It was delivered, which is not the same as done."
    if state == "acknowledged":
        return "The session has started on it."
    if state == "completed":
        return "The session has answered."
    return "The bridge marked it failed."
