"""SQLite task store + per-chat conversation memory."""
import atexit, os, shutil, sqlite3, threading, time
from .util import state_dir, log

_LOCK = threading.RLock()                     # re-entrant: a writer may call a reader
_DB = None


# v0.2 renamed the tenant layer from "brain" to "kb": a KB tenant is a KB, and
# "brain" now means the whole assembly. The CREATE TABLEs below already say `kb`,
# so a database written by v0.1 needs its columns and its stored KB names brought
# forward. Idempotent — it checks the current columns and does nothing when done.
_KB_RENAMES = {"kb-product": "main_kb", "client-kb": "client_kb",
               "office-local": "office_kb", "personal-local": "personal_kb"}


def _migrate_brain_to_kb(d, path):
    todo = [t for t in ("tasks", "harvests")
            if d.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()
            and "brain" in [r[1] for r in d.execute(f"PRAGMA table_info({t})")]]
    if not todo:
        return
    backup = path + ".pre-kb-rename"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    for t in todo:
        d.execute(f"ALTER TABLE {t} RENAME COLUMN brain TO kb")
        for old, new in _KB_RENAMES.items():
            d.execute(f"UPDATE {t} SET kb=? WHERE kb=?", (new, old))
    d.commit()
    log(f"migrated {', '.join(todo)}: column brain -> kb, KB names renamed. "
        f"Pre-migration copy: {backup}")


def db():
    global _DB
    if _DB is None:
        os.makedirs(state_dir(), exist_ok=True)
        path = os.path.join(state_dir(), "ethan.db")
        _DB = sqlite3.connect(path, check_same_thread=False)
        atexit.register(_DB.close)
        _migrate_brain_to_kb(_DB, path)
        _DB.execute("""CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, kind TEXT, kb TEXT,
            hand TEXT, ask TEXT, state TEXT, result TEXT)""")
        # the door an ask came through — added in 0.1.0, so an older database gains it here
        if "door" not in [r[1] for r in _DB.execute("PRAGMA table_info(tasks)")]:
            _DB.execute("ALTER TABLE tasks ADD COLUMN door TEXT")
        _DB.execute("""CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, role TEXT, text TEXT)""")
        # one row per hand invocation — what the console shows as a "session"
        _DB.execute("""CREATE TABLE IF NOT EXISTS runs(
            id INTEGER PRIMARY KEY, ts REAL, task_id INTEGER, hand TEXT, repo TEXT,
            log TEXT, state TEXT, ended REAL)""")
        # replies waiting to be picked up by a pull-based door (the console)
        _DB.execute("""CREATE TABLE IF NOT EXISTS replies(
            id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, text TEXT)""")
        # audit trail for close-out writes: who decided, where it went, or why not
        _DB.execute("""CREATE TABLE IF NOT EXISTS harvests(
            id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, hand TEXT, kb TEXT,
            filename TEXT, why TEXT, state TEXT)""")
        # asks passed to a running session through the message bridge (relay.py).
        # Written before the bridge is called, so a crash cannot lose what was sent.
        _DB.execute("""CREATE TABLE IF NOT EXISTS relays(
            id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, door TEXT, ask TEXT, mode TEXT,
            candidates TEXT, target TEXT, target_ref TEXT, bridge_key TEXT, message_id TEXT,
            state TEXT, note TEXT, result TEXT, updated REAL, purpose TEXT)""")
        _DB.commit()
    return _DB


def reap_orphans():
    """A killed Ethan leaves tasks/runs stuck at 'running' forever, which would
    block the close-out gate. Nothing can still be running at startup, so mark
    them interrupted. Returns how many were reaped."""
    with _LOCK:
        d = db()
        n = d.execute("SELECT COUNT(*) FROM tasks WHERE state='running'").fetchone()[0]
        n += d.execute("SELECT COUNT(*) FROM runs WHERE state='running'").fetchone()[0]
        d.execute("UPDATE tasks SET state='interrupted' WHERE state='running'")
        d.execute("UPDATE runs SET state='interrupted', ended=? WHERE state='running'", (time.time(),))
        d.commit()
        return n


def add_task(chat_id, kind, kb, hand, ask, door=None):
    with _LOCK:
        cur = db().execute("INSERT INTO tasks(ts,chat_id,kind,kb,hand,ask,state,door) VALUES(?,?,?,?,?,?,?,?)",
                           (time.time(), str(chat_id), kind, kb, hand, ask, "running", door))
        db().commit()
        return cur.lastrowid


def finish_task(task_id, state, result):
    with _LOCK:
        db().execute("UPDATE tasks SET state=?, result=? WHERE id=?", (state, result[:20000], task_id))
        db().commit()


def remember(chat_id, role, text):
    with _LOCK:
        db().execute("INSERT INTO messages(ts,chat_id,role,text) VALUES(?,?,?,?)",
                     (time.time(), str(chat_id), role, text[:4000]))
        db().commit()


def recent(chat_id, n=8):
    rows = db().execute("SELECT role,text FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                        (str(chat_id), n)).fetchall()
    return [{"role": r, "content": t} for r, t in reversed(rows)]


def conversation(chat_id):
    """Console history combines user turns with the replies actually shown."""
    with _LOCK:
        d = db()
        rows = d.execute("SELECT ts,role,text FROM messages WHERE chat_id=? AND role='user' UNION ALL SELECT ts,'assistant',text FROM replies WHERE chat_id=? ORDER BY ts", (str(chat_id), str(chat_id))).fetchall()
        after = d.execute("SELECT COALESCE(MAX(id),0) FROM replies WHERE chat_id=?", (str(chat_id),)).fetchone()[0]
    return {"messages": [{"role": role, "text": text} for _, role, text in rows[-100:]], "after": after}


def last_result(chat_id):
    """Most recent completed task output for this chat — what a follow-up refers to."""
    row = db().execute(
        "SELECT result FROM tasks WHERE chat_id=? AND state='done' AND result IS NOT NULL "
        "ORDER BY id DESC LIMIT 1", (str(chat_id),)).fetchone()
    return row[0] if row else None


# ── hand runs (what the console calls a session) ────────────────────────────
def start_run(task_id, hand, repo, log_path):
    with _LOCK:
        cur = db().execute("INSERT INTO runs(ts,task_id,hand,repo,log,state) VALUES(?,?,?,?,?,?)",
                           (time.time(), task_id, hand, repo or "", log_path, "running"))
        db().commit()
        return cur.lastrowid


def end_run(run_id, state):
    with _LOCK:
        db().execute("UPDATE runs SET state=?, ended=? WHERE id=?", (state, time.time(), run_id))
        db().commit()


def recent_runs(n=30):
    cols = "id,ts,task_id,hand,repo,log,state,ended"
    rows = db().execute(f"SELECT {cols} FROM runs ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(zip(cols.split(","), r)) for r in rows]


def recent_tasks(n=40):
    cols = "id,ts,chat_id,kind,kb,hand,ask,state,door"
    rows = db().execute(f"SELECT {cols} FROM tasks ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(zip(cols.split(","), r)) for r in rows]


def task(task_id):
    cols = "id,ts,chat_id,kind,kb,hand,ask,state,result"
    row = db().execute(f"SELECT {cols} FROM tasks WHERE id=?", (task_id,)).fetchone()
    return dict(zip(cols.split(","), row)) if row else None


def pending(chat_id=None):
    """Unfinished work — the close-out gate reads this."""
    q = "SELECT id,kind,hand,ask FROM tasks WHERE state='running'"
    args = ()
    if chat_id is not None:
        q += " AND chat_id=?"; args = (str(chat_id),)
    return [dict(zip(("id", "kind", "hand", "ask"), r)) for r in db().execute(q, args).fetchall()]


# ── close-out audit ─────────────────────────────────────────────────────────
def add_harvest(chat_id, hand, kb, filename, why, state):
    with _LOCK:
        db().execute("INSERT INTO harvests(ts,chat_id,hand,kb,filename,why,state) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (time.time(), str(chat_id), hand, kb, filename, why[:1000], state))
        db().commit()


def recent_harvests(n=25):
    cols = "id,ts,chat_id,hand,kb,filename,why,state"
    rows = db().execute(f"SELECT {cols} FROM harvests ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(zip(cols.split(","), r)) for r in rows]


# ── pull-based replies (the console polls; Telegram pushes) ─────────────────
def add_reply(chat_id, text):
    with _LOCK:
        db().execute("INSERT INTO replies(ts,chat_id,text) VALUES(?,?,?)",
                     (time.time(), str(chat_id), text))
        db().commit()


def replies_since(chat_id, after_id=0):
    rows = db().execute("SELECT id,ts,text FROM replies WHERE chat_id=? AND id>? ORDER BY id",
                        (str(chat_id), after_id)).fetchall()
    return [{"id": i, "ts": t, "text": x} for i, t, x in rows]


# ── presence: when you last typed at the laptop ─────────────────────────────
def note_desktop():
    """The console and the CLI call this on every ask. Telegram does not."""
    with _LOCK:
        d = db()
        d.execute("CREATE TABLE IF NOT EXISTS presence(key TEXT PRIMARY KEY, value REAL)")
        d.execute("INSERT INTO presence(key,value) VALUES('desktop',?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (time.time(),))
        d.commit()


def last_desktop():
    with _LOCK:
        d = db()
        d.execute("CREATE TABLE IF NOT EXISTS presence(key TEXT PRIMARY KEY, value REAL)")
        row = d.execute("SELECT value FROM presence WHERE key='desktop'").fetchone()
    return row[0] if row else None


# ── relays to running sessions ──────────────────────────────────────────────
_RELAY_COLS = ("id,ts,chat_id,door,ask,mode,candidates,target,target_ref,bridge_key,message_id,"
               "state,note,result,updated,purpose")


def add_relay(chat_id, door, ask, mode, candidates=None, purpose=None):
    """A relay starts as a question ("which session?") when there are candidates to
    choose from, and as an unsent row otherwise."""
    import json
    with _LOCK:
        now = time.time()
        cur = db().execute(
            "INSERT INTO relays(ts,chat_id,door,ask,mode,candidates,state,updated,purpose) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (now, str(chat_id), door, ask, mode, json.dumps(candidates) if candidates else None,
             "needs-target" if candidates else "new", now, purpose))
        db().commit()
        return cur.lastrowid


_RELAY_FIELDS = {"state", "target", "target_ref", "bridge_key", "message_id", "note", "result", "purpose", "mode"}


def update_relay(relay_id, **fields):
    bad = set(fields) - _RELAY_FIELDS
    if bad:
        raise ValueError(f"not a relay field: {sorted(bad)}")
    with _LOCK:
        sets = ", ".join(f"{k}=?" for k in fields)
        db().execute(f"UPDATE relays SET {sets}, updated=? WHERE id=?",
                     (*fields.values(), time.time(), relay_id))
        db().commit()


def relay(relay_id):
    with _LOCK:
        row = db().execute(f"SELECT {_RELAY_COLS} FROM relays WHERE id=?", (relay_id,)).fetchone()
    return dict(zip(_RELAY_COLS.split(","), row)) if row else None


def open_question(chat_id):
    """The relay still waiting for "which session?" in this conversation, if any."""
    row = db().execute(f"SELECT {_RELAY_COLS} FROM relays WHERE chat_id=? AND state='needs-target' "
                       "ORDER BY id DESC LIMIT 1", (str(chat_id),)).fetchone()
    return dict(zip(_RELAY_COLS.split(","), row)) if row else None


#: Bridge states in which the target has not answered yet, plus Ethan's own "sending".
RELAY_OPEN = ("sending", "queued", "delivered", "acknowledged")


def open_relays(chat_id=None):
    q = f"SELECT {_RELAY_COLS} FROM relays WHERE state IN ({','.join('?' * len(RELAY_OPEN))})"
    args = RELAY_OPEN
    if chat_id is not None:
        q += " AND chat_id=?"; args = (*RELAY_OPEN, str(chat_id))
    with _LOCK:
        rows = db().execute(q + " ORDER BY id", args).fetchall()
    return [dict(zip(_RELAY_COLS.split(","), r)) for r in rows]


def recent_relays(n=20):
    with _LOCK:
        rows = db().execute(f"SELECT {_RELAY_COLS} FROM relays ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(zip(_RELAY_COLS.split(","), r)) for r in rows]
