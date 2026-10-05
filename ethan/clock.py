"""Ethan's own clock — reminders you set, and recurring checks that only read.

Ethan acts when a door asks. The clock is the one exception, and a narrow one: at a
time you named it may remind you, or run an ask that only reads — a question, a status
ask, a review-only relay. It never starts a hand: the router refuses the `clock` door
for build, review and chain. Every reminder is a ledger row, so a restart loses
nothing, and one that came due while Ethan was stopped is reported as missed, not run
late without a word.

What it understands, on purpose a short list:
  remind me at 15:00 to send the report
  remind me in 20 minutes to call back
  remind me tomorrow at 9 to book the room
  at 17:30, ask the codex session to check the open reviews
  every weekday at 09:00, what is running?
  every day at 18:00 … · every hour …
  my reminders · cancel reminder #3
"""
import datetime as dt
import re
import time
from . import policy, store
from .util import log

DOOR = "clock"
#: A reminder due longer ago than this is told as missed, not fired as if on time.
GRACE_SEC = 300

_REMIND = re.compile(r"^\s*(?:please\s+|ethan,?\s+)?remind me\b", re.I)
_EVERY = re.compile(r"\bevery\s+(weekday|day|morning|hour)\b", re.I)
_AT = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)
_IN = re.compile(r"\bin\s+(\d+)\s*(min(?:ute)?s?|h(?:ou)?rs?|days?)\b", re.I)
_TOMORROW = re.compile(r"\btomorrow\b", re.I)
_LIST = re.compile(r"^\s*(?:my|list|show)\s+reminders\b|^\s*what(?:'s| is) scheduled\b", re.I)
_CANCEL = re.compile(r"^\s*cancel\s+reminder\s+#?(\d+)\b", re.I)
_LEADING_TIME = re.compile(
    r"^\s*(?:(?:please\s+|ethan,?\s+)?remind me\s+)?(?:every\s+\w+\s*)?(?:tomorrow\s*)?"
    r"(?:at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|in\s+\d+\s*\w+)?\s*[,:]?\s*(?:to\s+)?", re.I)

COLS = "id,ts,chat_id,door,kind,what,due,every,at_time,state,last_fired,note"


# ── the ledger ──────────────────────────────────────────────────────────────
def _ensure():
    d = store.db()
    d.execute("""CREATE TABLE IF NOT EXISTS reminders(
        id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, door TEXT, kind TEXT, what TEXT,
        due REAL, every TEXT, at_time TEXT, state TEXT, last_fired REAL, note TEXT)""")
    d.execute("CREATE TABLE IF NOT EXISTS clock_state(key TEXT PRIMARY KEY, value REAL)")
    d.commit()
    return d


def _rows(where="1=1", args=()):
    d = _ensure()
    rows = d.execute(f"SELECT {COLS} FROM reminders WHERE {where} ORDER BY due", args).fetchall()
    return [dict(zip(COLS.split(","), r)) for r in rows]


def scheduled(chat_id=None):
    if chat_id is None:
        return _rows("state='scheduled'")
    return _rows("state='scheduled' AND chat_id=?", (str(chat_id),))


def _add(chat_id, door, kind, what, due, every, at_time):
    with store._LOCK:
        d = _ensure()
        cur = d.execute("INSERT INTO reminders(ts,chat_id,door,kind,what,due,every,at_time,state) "
                        "VALUES(?,?,?,?,?,?,?,?,'scheduled')",
                        (time.time(), str(chat_id), door, kind, what, due, every, at_time))
        d.commit()
        return cur.lastrowid


def _set(rid, **fields):
    with store._LOCK:
        d = _ensure()
        d.execute("UPDATE reminders SET " + ", ".join(f"{k}=?" for k in fields) + " WHERE id=?",
                  (*fields.values(), rid))
        d.commit()


def last_tick():
    row = _ensure().execute("SELECT value FROM clock_state WHERE key='last_tick'").fetchone()
    return row[0] if row else None


def _note_tick(now):
    with store._LOCK:
        d = _ensure()
        d.execute("INSERT INTO clock_state(key,value) VALUES('last_tick',?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now,))
        d.commit()


# ── reading a time ──────────────────────────────────────────────────────────
def _clock_time(m):
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= mi < 60):
        return None
    return h, mi


def _next(at_time, every, after):
    """The first moment strictly after `after` that matches `every` at `at_time`."""
    h, mi = map(int, at_time.split(":"))
    base = dt.datetime.fromtimestamp(after)
    cand = base.replace(hour=h, minute=mi, second=0, microsecond=0)
    while cand <= base or (every == "weekday" and cand.weekday() >= 5):
        cand += dt.timedelta(days=1)
    return cand.timestamp()


def parse(text, now=None):
    """What the ask schedules: {kind, what, due, every, at_time}, or a string saying
    what Ethan could not read. Times are local."""
    now = now or time.time()
    every = _EVERY.search(text)
    at, within = _AT.search(text), _IN.search(text)
    kind = "reminder" if _REMIND.match(text) else "ask"
    what = _LEADING_TIME.sub("", text, count=1).strip().rstrip(".") or None
    if not what:
        return "I need to know what to remind you of, or what to ask."
    if every:
        unit = every.group(1).lower()
        if unit == "hour":
            return {"kind": kind, "what": what, "due": now + 3600, "every": "hour", "at_time": None}
        if not at and unit != "morning":
            return "Say the time as well: 'every weekday at 09:00, …'."
        hm = _clock_time(at) if at else (9, 0)
        if hm is None:
            return "That is not a time I can read; use HH:MM."
        at_time = f"{hm[0]:02d}:{hm[1]:02d}"
        rule = "weekday" if unit == "weekday" else "day"
        return {"kind": kind, "what": what, "due": _next(at_time, rule, now), "every": rule, "at_time": at_time}
    if within:
        n, unit = int(within.group(1)), within.group(2).lower()
        secs = n * (60 if unit.startswith("m") else 3600 if unit.startswith("h") else 86400)
        return {"kind": kind, "what": what, "due": now + secs, "every": None, "at_time": None}
    if at:
        hm = _clock_time(at)
        if hm is None:
            return "That is not a time I can read; use HH:MM."
        base = dt.datetime.fromtimestamp(now)
        cand = base.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if _TOMORROW.search(text):
            cand += dt.timedelta(days=1)
        elif cand <= base:
            cand += dt.timedelta(days=1)          # that time today is gone: tomorrow
        return {"kind": kind, "what": what, "due": cand.timestamp(), "every": None, "at_time": None}
    return ("I could not find a time. Say 'at 15:00', 'in 20 minutes', 'tomorrow at 9' "
            "or 'every weekday at 09:00'.")


def _when(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%a %d %b %H:%M")


def describe(r):
    """What a clock row is for, in words: the reminder text, or the watch it runs."""
    return f"watch #{r['what']}" if r["kind"] == "watch" else r["what"]


# ── the conversation ────────────────────────────────────────────────────────
def take(chat_id, text, reply, door, now=None):
    """Handle the ask when it is the clock's, and say whether it was."""
    if _LIST.match(text):
        rows = scheduled(chat_id)
        if not rows:
            reply("Nothing is scheduled for this conversation.")
        else:
            reply("Scheduled:\n" + "\n".join(
                f"  #{r['id']} {_when(r['due'])}{' · every ' + r['every'] if r['every'] else ''} — {r['what']}"
                for r in rows))
        return True
    m = _CANCEL.match(text)
    if m:
        rid = int(m.group(1))
        row = next((r for r in scheduled(chat_id) if r["id"] == rid), None)
        if not row:
            reply(f"There is no scheduled reminder #{rid} in this conversation.")
        else:
            _set(rid, state="cancelled")
            reply(f"Cancelled reminder #{rid}.")
        return True
    if not (_REMIND.match(text) or (_EVERY.search(text) and (_AT.search(text) or "hour" in text.lower()))
            or (_AT.match(text.strip()) and "," in text)):
        return False
    if not policy.allowed("remind"):
        reply(policy.refusal("remind", "I may not set reminders or scheduled asks"))
        return True
    got = parse(text, now)
    if isinstance(got, str):
        reply(got)
        return True
    rid = _add(chat_id, door, got["kind"], got["what"], got["due"], got["every"], got["at_time"])
    how = f"every {got['every']}" + (f" at {got['at_time']}" if got["at_time"] else "") if got["every"] else "once"
    verb = "remind you" if got["kind"] == "reminder" else "ask"
    reply(f"Reminder #{rid}: I will {verb} — {got['what']} — at {_when(got['due'])}, {how}. "
          f"Say 'cancel reminder #{rid}' to drop it.")
    log(f"clock: #{rid} {got['kind']} at {_when(got['due'])} {how}")
    return True


# ── firing ──────────────────────────────────────────────────────────────────
def _deliver(chat_id, door, text):
    from . import reach                           # the conversation, and your phone when it matters
    reach.tell(chat_id, door, text)


def _run_ask(chat_id, text, deliver, door):
    from . import router                          # late: router imports this module
    router.handle(chat_id, text, lambda t, c=chat_id: deliver(c, door, t), door=DOOR)


def tick(now=None, deliver=_deliver, run=_run_ask):
    """Fire what is due. Safe to call as often as wanted. Returns the rows it fired or
    marked missed. A reminder due more than GRACE_SEC ago is missed: told as such, and a
    recurring one moves on to its next time."""
    now = now or time.time()
    out = []
    if not policy.allowed("remind"):              # the policy changed after rows were set: hold them
        _note_tick(now)
        return out
    for r in _rows("state='scheduled' AND due<=?", (now,)):
        late = now - r["due"]
        if late > GRACE_SEC:
            what = f"watch #{r['what']}" if r["kind"] == "watch" else r["what"]
            deliver(r["chat_id"], r["door"],
                    f"Missed reminder #{r['id']} — it was due {_when(r['due'])}, {int(late // 60)} min ago, "
                    f"and Ethan was not running then: {what}")
            _set(r["id"], state="missed" if not r["every"] else "scheduled", last_fired=now,
                 note=f"missed at {_when(r['due'])}")
        else:
            if r["kind"] == "reminder":
                deliver(r["chat_id"], r["door"], f"Reminder #{r['id']}: {r['what']}")
            elif r["kind"] == "watch":
                from . import watch               # late: watch imports this module
                watch.run(int(r["what"]), deliver, now)
            else:
                deliver(r["chat_id"], r["door"], f"Scheduled ask #{r['id']}: {r['what']}")
                run(r["chat_id"], r["what"], deliver, r["door"])
            _set(r["id"], state="fired" if not r["every"] else "scheduled", last_fired=now)
        if r["every"]:
            nxt = now + 3600 if r["every"] == "hour" else _next(r["at_time"], r["every"], now)
            _set(r["id"], due=nxt)
        out.append(store.db().execute(f"SELECT {COLS} FROM reminders WHERE id=?", (r["id"],)).fetchone())
    _note_tick(now)
    return [dict(zip(COLS.split(","), o)) for o in out]


def ticker(stop=None, every=20):
    import threading
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            tick()
        except Exception as e:                    # the clock must outlive any one bad pass
            log(f"clock: {type(e).__name__}: {e}")
        stop.wait(every)
