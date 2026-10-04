"""Watch a source through a session's own connectors.

Claude and Codex can already read mail, calendars, chats and tickets through their
connectors. Ethan does not build its own. A watch is a question Ethan asks a running
session on a schedule — "what must I reply to?" — with a fixed answer shape, and each
item in the answer becomes a task on your list (`todo.py`), once. Nothing is ever sent
from the source: the relay is review-only, and the session only reads.

  watch mail through the claude session ethan every weekday at 09:00: what must I reply to?
  watch tickets via codex-ethan every day at 08:30: which tickets assigned to me changed?
  my watches · stop watch #2
"""
import re
import time
from . import bridge_registry, clock, relay, store, todo
from .util import log

#: last_run is the last attempt; last_ok the last run the session actually answered. The
#: "since" bound comes from last_ok, so a failed send or a failed answer never loses
#: the items that came in between.
COLS = "id,ts,chat_id,door,source,target,question,every,at_time,state,last_run,note,last_ok"

_WATCH = re.compile(
    r"^\s*watch\s+(?P<source>[\w][\w /-]*?)\s+(?:through|via|with|using)\s+(?P<target>.+?)\s+"
    r"(?P<when>every\s+\w+(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?)\s*[:,]\s*(?P<question>.+)$", re.I | re.S)
_LIST = re.compile(r"^\s*(?:my|list|show)\s+watches\b", re.I)
_STOP = re.compile(r"^\s*(?:stop|cancel|drop)\s+watch\s+#?(\d+)\b", re.I)
#: An item has the separators; a bullet without them is prose, and is not a task.
_ITEM = re.compile(r"^\s*[-*•]\s*(?P<title>[^|]+?)\s*\|\s*(?P<link>[^|]*?)\s*(?:\|\s*(?P<why>[^|]*?)\s*(?:\|\s*(?P<due>.*?)\s*)?)?$")
_NOTHING = re.compile(r"^\s*[-*•]?\s*(nothing|none|no items|no new items)\b[.!]?\s*$", re.I)

SHAPE = ("Answer with one line per item, in exactly this shape and nothing else:\n"
         "- <title> | <link or -> | <why it matters to me> | <due date or ->\n"
         "If there is nothing, answer exactly: - nothing")


# ── the ledger ──────────────────────────────────────────────────────────────
def _ensure():
    d = store.db()
    d.execute("""CREATE TABLE IF NOT EXISTS watches(
        id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, door TEXT, source TEXT, target TEXT,
        question TEXT, every TEXT, at_time TEXT, state TEXT, last_run REAL, note TEXT, last_ok REAL)""")
    d.commit()
    return d


def _rows(where="1=1", args=()):
    rows = _ensure().execute(f"SELECT {COLS} FROM watches WHERE {where} ORDER BY id", args).fetchall()
    return [dict(zip(COLS.split(","), r)) for r in rows]


def get(wid):
    rows = _rows("id=?", (wid,))
    return rows[0] if rows else None


def active(chat_id=None):
    return _rows("state='active'" + ("" if chat_id is None else " AND chat_id=?"),
                 () if chat_id is None else (str(chat_id),))


def _set(wid, **fields):
    with store._LOCK:
        d = _ensure()
        d.execute("UPDATE watches SET " + ", ".join(f"{k}=?" for k in fields) + " WHERE id=?",
                  (*fields.values(), wid))
        d.commit()


# ── the conversation ────────────────────────────────────────────────────────
def take(chat_id, text, reply, door, now=None):
    """Handle the ask when it is a watch's, and say whether it was."""
    now = now or time.time()
    if _LIST.match(text):
        rows = active(chat_id)
        reply("No watches in this conversation." if not rows else "Watches:\n" + "\n".join(
            f"  #{w['id']} {w['source']} through {w['target']} · every {w['every']}"
            f"{' at ' + w['at_time'] if w['at_time'] else ''} — {w['question']}"
            + (f" · last answered {clock._when(w['last_ok'])}" if w["last_ok"] else
               f" · tried {clock._when(w['last_run'])}, no answer yet" if w["last_run"] else " · not run yet")
            for w in rows))
        return True
    m = _STOP.match(text)
    if m:
        wid = int(m.group(1))
        w = next((w for w in active(chat_id) if w["id"] == wid), None)
        if not w:
            reply(f"There is no active watch #{wid} in this conversation.")
            return True
        _set(wid, state="stopped")
        for r in clock.scheduled(chat_id):
            if r["kind"] == "watch" and r["what"] == str(wid):
                clock._set(r["id"], state="cancelled")
        reply(f"Stopped watch #{wid}. Tasks it added stay on your list.")
        return True
    m = _WATCH.match(text)
    if not m:
        return False
    if not relay.allowed(door):
        reply(f"I do not pass work to coding sessions from the {door} door, so I cannot watch from here.")
        return True
    source, target, when, question = (m.group(k).strip() for k in ("source", "target", "when", "question"))
    reg = bridge_registry.sessions()
    pool = relay.targets(target, reg["sessions"]) if reg["available"] else []
    if len(pool) != 1:
        who = "no registered session" if not pool else f"{len(pool)} sessions"
        reply(f"'{target}' matches {who}, so I set nothing up. Name one session: "
              + (", ".join(relay._label(s) for s in pool) if pool else "`show my agents` lists them."))
        return True
    sched = clock.parse(f"{when}, run", now)
    if isinstance(sched, str):
        reply(sched)
        return True
    with store._LOCK:
        d = _ensure()
        cur = d.execute("INSERT INTO watches(ts,chat_id,door,source,target,question,every,at_time,state) "
                        "VALUES(?,?,?,?,?,?,?,?,'active')",
                        (now, str(chat_id), door, source, relay._label(pool[0]), question.rstrip("."),
                         sched["every"], sched["at_time"]))
        d.commit()
        wid = cur.lastrowid
    clock._add(chat_id, door, "watch", str(wid), sched["due"], sched["every"], sched["at_time"])
    reply(f"Watch #{wid}: every {sched['every']}{' at ' + sched['at_time'] if sched['at_time'] else ''}, "
          f"starting {clock._when(sched['due'])}, I will ask {relay._label(pool[0])} (review-only): "
          f"{question} Each item it reports becomes a task on your list, once. "
          f"Say 'stop watch #{wid}' to end it.")
    log(f"watch #{wid}: {source} through {relay._label(pool[0])} every {sched['every']}")
    return True


# ── running one ─────────────────────────────────────────────────────────────
def run(wid, deliver, now=None):
    """The clock calls this at the watch's time. The question goes to the session as a
    review-only relay tagged with the watch, and `absorb` reads the answer when it comes."""
    now = now or time.time()
    w = get(wid)
    if not w or w["state"] != "active":
        return
    reg = bridge_registry.sessions()
    pool = [s for s in reg["sessions"] if relay._label(s) == w["target"]] if reg["available"] else []
    if len(pool) != 1:
        deliver(w["chat_id"], w["door"], f"Watch #{wid} ({w['source']}) could not run: {w['target']} is not "
                f"registered with the bridge now. Nothing was sent; it will try again next time.")
        _set(wid, note=f"skipped {clock._when(now)}: target not registered")
        return
    since = clock._when(w["last_ok"]) if w["last_ok"] else "any time"
    text = (f"{w['question']}\n\nOnly items since {since}. Read only; send nothing and change nothing.\n"
            f"{SHAPE}")
    _set(wid, last_run=now)                       # the attempt; last_ok moves only in `absorb`
    told = relay.dispatch(w["chat_id"], w["door"], pool[0], text, "review-only",
                          purpose=f"watch:{wid}:{now}")   # the run's own time rides with the relay
    deliver(w["chat_id"], w["door"], f"Watch #{wid} ({w['source']}): {told}")


def absorb(r, state, result):
    """Read a finished watch relay's answer into tasks. Returns what to tell the person."""
    parts = r["purpose"].split(":")
    wid = int(parts[1])
    ran = float(parts[2]) if len(parts) > 2 else r["ts"]
    w = get(wid) or {"source": "watch"}
    if state != "completed":
        return (f"Watch #{wid} ({w['source']}): the session FAILED to answer — {(result or 'no reason')[-800:]}"
                f" The next run asks again from the same point.")
    added, seen, bad = [], 0, []
    for line in (result or "").splitlines():
        if not line.strip() or _NOTHING.match(line):
            continue
        m = _ITEM.match(line)
        if not m:
            bad.append(line.strip())
            continue
        try:                                      # one bad line must not lose the others
            title = m.group("title").strip()
            link = (m.group("link") or "").strip()
            link = None if link in ("", "-") else link
            why = (m.group("why") or "").strip() or None
            due_text = (m.group("due") or "").strip()
            due = todo.parse_due(due_text) if due_text and due_text != "-" else None
            tid, new = todo.add(title, source=w["source"], link=link, why=why, due=due, chat_id=r["chat_id"])
        except Exception as e:
            log(f"watch #{wid}: could not keep a line ({type(e).__name__}: {e}): {line.strip()[:120]}")
            bad.append(line.strip())
            continue
        if new:
            added.append((tid, title))
        else:
            seen += 1
    _set(wid, last_ok=ran)                       # every item kept or shown: the next run asks from this send
    head = f"Watch #{wid} ({w['source']}): "
    if not added and not seen and not bad:
        return head + "nothing new."
    parts = []
    if added:
        parts.append(f"{len(added)} new task(s):\n" + "\n".join(f"  #{t} {title}" for t, title in added))
    if seen:
        parts.append(f"{seen} already on your list")
    if bad:
        parts.append("could not read these lines, so they are not tasks:\n" + "\n".join(f"  {b}" for b in bad[:5]))
    return head + "; ".join(parts) + "\nSay 'my tasks' to see the list."
