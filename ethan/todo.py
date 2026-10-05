"""One task list, gathered from every source.

A task is something you have to do: a line you typed, an action item from a meeting, a
mail a watch says you must answer. Whatever the source, it lands here, so "what should
I do now?" has one answer, ordered by what is due. Marking a task done touches only
this list, never the source. A task that a source reports again is merged, not added
twice. No model is involved: the list is read and written by rules.

What it understands:
  add task: send the report by Friday      task: book the room by 15:00
  my tasks · what should I do now · what's on my list
  done #3 · drop task #3 · snooze task #3 until tomorrow · snooze task #3 for 2 hours
"""
import datetime as dt
import re
import time
from . import store
from .util import log

COLS = "id,ts,chat_id,title,source,link,why,due,state,until,note,dedupe,updated"
OPEN = ("open", "snoozed")
#: A task marked done is not re-added when its source reports it again within this long.
DONE_STAYS_DONE = 30 * 86400

_ADD = re.compile(r"^\s*(?:add\s+(?:a\s+)?task|task|todo)\s*[:\-]\s*(.+)$", re.I | re.S)
_LIST = re.compile(r"^\s*(?:my tasks|list tasks|show (?:my )?tasks|what should i do(?: now| next)?|what(?:'s| is) on my (?:task )?list)\b", re.I)
#: "done #3", "done task 3", "task #3 done" — not "completed 3 reviews today".
_DONE = re.compile(r"^\s*(?:done|finished|completed)\s+(?:task\s+#?|#)(\d+)\s*$|^\s*task\s+#?(\d+)\s+(?:is\s+)?done\s*$", re.I)
_DROP = re.compile(r"^\s*(?:drop|remove|delete)\s+task\s+#?(\d+)\b", re.I)
_SNOOZE = re.compile(r"^\s*snooze\s+(?:task\s+)?#?(\d+)\s+(until|for)\s+(.+)$", re.I)
_BY = re.compile(r"\s+by\s+", re.I)             # the LAST "by": "stand by the door by Friday"
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
#: A time is "17:00", "5pm" or "at 5" — never a bare number: "sprint 14" is not two o'clock.
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b|\b(\d{1,2})\s*(am|pm)\b|\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)


# ── the ledger ──────────────────────────────────────────────────────────────
def _ensure():
    with store._LOCK:
        return __ensure()


def __ensure():
    d = store.db()
    d.execute("""CREATE TABLE IF NOT EXISTS todos(
        id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, title TEXT, source TEXT, link TEXT,
        why TEXT, due REAL, state TEXT, until REAL, note TEXT, dedupe TEXT, updated REAL)""")
    d.execute("CREATE INDEX IF NOT EXISTS todos_dedupe ON todos(source, dedupe)")
    d.commit()
    return d


def _rows(where="1=1", args=()):
    d = _ensure()
    rows = d.execute(f"SELECT {COLS} FROM todos WHERE {where} "
                     "ORDER BY CASE WHEN due IS NULL THEN 1 ELSE 0 END, due, id", args).fetchall()
    return [dict(zip(COLS.split(","), r)) for r in rows]


def get(tid):
    rows = _rows("id=?", (tid,))
    return rows[0] if rows else None


def open_tasks(now=None):
    """Open tasks, snoozed ones included once their time has come."""
    now = now or time.time()
    return [t for t in _rows(f"state IN ({','.join('?' * len(OPEN))})", OPEN)
            if t["state"] == "open" or (t["until"] or 0) <= now]


def add(title, source="you", link=None, why=None, due=None, chat_id=None, dedupe=None):
    """Add a task, or return the open one it duplicates. A source that reports the same
    item twice — same link, or same title when there is no link — gets one task."""
    title = " ".join(title.split())[:300]
    key = (dedupe or link or title).strip().lower()
    with store._LOCK:
        d = _ensure()
        row = d.execute(f"SELECT id FROM todos WHERE source=? AND dedupe=? AND (state IN "
                        f"({','.join('?' * len(OPEN))}) OR (state='done' AND updated>?))",
                        (source, key, *OPEN, time.time() - DONE_STAYS_DONE)).fetchone()
        if row:
            return row[0], False
        now = time.time()
        cur = d.execute("INSERT INTO todos(ts,chat_id,title,source,link,why,due,state,dedupe,updated) "
                        "VALUES(?,?,?,?,?,?,?,'open',?,?)",
                        (now, str(chat_id) if chat_id is not None else None, title, source, link,
                         why, due, key, now))
        d.commit()
        log(f"task #{cur.lastrowid} from {source}: {title[:60]}")
        return cur.lastrowid, True


def set_state(tid, state, until=None, note=None):
    with store._LOCK:
        d = _ensure()
        d.execute("UPDATE todos SET state=?, until=?, note=COALESCE(?, note), updated=? WHERE id=?",
                  (state, until, note, time.time(), tid))
        d.commit()


# ── reading a due date ──────────────────────────────────────────────────────
def parse_due(text, now=None):
    """'tomorrow', 'friday', '17:00', '2026-10-10', 'tomorrow 9:00', 'in 2 hours'. None
    when there is nothing Ethan can read; a due date is never guessed. The text may come
    from a session's answer, so a date that does not exist (2026-02-30) is unreadable,
    not an error."""
    try:
        return _parse_due(text, now)
    except (ValueError, OverflowError, OSError):
        return None


def _parse_due(text, now=None):
    now = now or time.time()
    base = dt.datetime.fromtimestamp(now)
    low = text.strip().lower()
    day = None
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    md = (re.search(rf"\b(\d{{1,2}})\s+({'|'.join(_MONTHS)})\w*(?:,?\s+(\d{{4}}))?\b", low)
          or re.search(rf"\b({'|'.join(_MONTHS)})\w*\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", low))
    if m:
        day = dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    elif md:                                      # "10 Oct", "Oct 10 2026"
        a, b, year = md.group(1), md.group(2), md.group(3)
        dnum, mon = (int(a), b) if a.isdigit() else (int(b), a)
        month = _MONTHS.index(mon[:3]) + 1
        day = dt.datetime(int(year) if year else base.year, month, dnum)
        if not year and day.date() < base.date():
            day = dt.datetime(base.year + 1, month, dnum)
    elif "tomorrow" in low:
        day = (base + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif "today" in low or "tonight" in low:
        day = base.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        for i, name in enumerate(_DAYS):          # the full name or its three letters, as a word
            if re.search(rf"\b(?:{name}|{name[:3]})\b", low):
                ahead = (i - base.weekday()) % 7 or 7
                day = (base + dt.timedelta(days=ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
                break
    m = re.search(r"\bin\s+(\d+)\s*(min(?:ute)?s?|h(?:ou)?rs?|days?)\b", low)
    if m and day is None:
        n, unit = int(m.group(1)), m.group(2)
        return now + n * (60 if unit.startswith("m") else 3600 if unit.startswith("h") else 86400)
    rest = re.sub(r"\d{4}-\d{2}-\d{2}", " ", low)          # the date's digits are not a time
    if md:
        rest = rest.replace(md.group(0), " ")
    t = _TIME.search(rest)
    hm = None
    if t:
        g = t.groups()
        h, mi, ap = (int(g[0]), int(g[1]), g[2]) if g[0] else (int(g[3]), 0, g[4]) if g[3] else \
                    (int(g[5]), int(g[6] or 0), g[7])
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if not (0 <= h < 24 and 0 <= mi < 60):
            return None                           # a time was written and it does not exist: no guess
        hm = (h, mi)
    if day is None and hm is None:
        return None
    if day is None:
        day = base.replace(hour=0, minute=0, second=0, microsecond=0)
        cand = day.replace(hour=hm[0], minute=hm[1])
        if cand <= base:
            cand += dt.timedelta(days=1)
        return cand.timestamp()
    if hm:
        return day.replace(hour=hm[0], minute=hm[1]).timestamp()
    return day.replace(hour=23, minute=59).timestamp()


def _when(ts, now=None):
    if ts is None:
        return "no date"
    d = dt.datetime.fromtimestamp(ts)
    return d.strftime("%a %d %b") + ("" if d.hour == 23 and d.minute == 59 else d.strftime(" %H:%M"))


def render(now=None):
    now = now or time.time()
    tasks = open_tasks(now)
    if not tasks:
        return "Your list is empty."
    lines = []
    for t in tasks:
        flag = "OVERDUE " if t["due"] and t["due"] < now else ""
        src = "" if t["source"] == "you" else f" · from {t['source']}"
        link = f" · {t['link']}" if t["link"] else ""
        lines.append(f"  #{t['id']} {flag}{_when(t['due'])} — {t['title']}{src}{link}")
    return f"{len(tasks)} open:\n" + "\n".join(lines)


# ── the conversation ────────────────────────────────────────────────────────
def take(chat_id, text, reply, door, now=None):
    """Handle the ask when it is the list's, and say whether it was."""
    now = now or time.time()
    m = _ADD.match(text)
    if m:
        body = m.group(1).strip().rstrip(".")
        due, title = None, body
        bys = list(_BY.finditer(body))
        by = bys[-1] if bys else None
        if by:
            due = parse_due(body[by.end():], now)
            if due is not None:
                title = body[:by.start()].strip()
        tid, new = add(title, "you", due=due, chat_id=chat_id)
        if not new:
            reply(f"That is already on your list as task #{tid}.")
        else:
            when = f", due {_when(due)}" if due else ""
            tail = "" if due or not by else " (I could not read that date, so none is set.)"
            reply(f"Task #{tid} added — {title}{when}.{tail}")
        return True
    if _LIST.match(text):
        reply(render(now))
        return True
    m = _DONE.match(text)
    if m:
        return _move(int(m.group(1) or m.group(2)), "done", reply)
    m = _DROP.match(text)
    if m:
        return _move(int(m.group(1)), "dropped", reply)
    m = _SNOOZE.match(text)
    if m:
        tid, how, when = int(m.group(1)), m.group(2).lower(), m.group(3)
        until = parse_due(("in " if how == "for" and not when.lower().startswith("in") else "") + when, now)
        if until is None:
            reply("I could not read that time. Say 'until tomorrow', 'until friday 9:00' or 'for 2 hours'.")
            return True
        t = get(tid)
        if not t or t["state"] not in OPEN:
            reply(f"There is no open task #{tid}.")
            return True
        set_state(tid, "snoozed", until=until)
        reply(f"Task #{tid} snoozed until {_when(until)}.")
        return True
    return False


def _move(tid, state, reply):
    t = get(tid)
    if not t or t["state"] not in OPEN:
        reply(f"There is no open task #{tid}.")
        return True
    set_state(tid, state)
    reply(f"Task #{tid} {state} — {t['title']}." + (f" Its source ({t['source']}) is untouched." if t["source"] != "you" else ""))
    return True
