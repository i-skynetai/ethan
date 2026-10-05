"""Getting hold of you — the desktop first, then your phone.

Everything Ethan has to tell you lands in the conversation that asked (the console
or the CLI reads it there). Some things should also reach your phone: anything you
marked urgent, and anything that comes when you are away from the laptop. The phone
route is the Telegram door, when it is configured. A call is not built; that is a
decision still to make (roadmap EH-070), and Ethan never pretends otherwise.

Every attempt — sent, skipped and why, failed and why — is a row in the ledger.
"""
import datetime as dt
import os
import time
from . import identity, policy, store
from .util import cfg, log

COLS = "id,ts,chat_id,route,state,why,text"


def _ensure():
    d = store.db()
    d.execute("""CREATE TABLE IF NOT EXISTS reach(
        id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, route TEXT, state TEXT, why TEXT, text TEXT)""")
    d.commit()
    return d


def _record(chat_id, route, state, why, text):
    with store._LOCK:
        d = _ensure()
        d.execute("INSERT INTO reach(ts,chat_id,route,state,why,text) VALUES(?,?,?,?,?,?)",
                  (time.time(), str(chat_id), route, state, why, text[:2000]))
        d.commit()


def recent(n=20):
    rows = _ensure().execute(f"SELECT {COLS} FROM reach ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(zip(COLS.split(","), r)) for r in rows]


# ── the rules ───────────────────────────────────────────────────────────────
def settings():
    r = cfg("ethan.json").get("reach", {})
    return {"away_after_min": int(r.get("away_after_min", 20)),
            "quiet_hours": r.get("quiet_hours", "22:00-07:00")}


def phone_configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN")) and bool(_phone_ids())


def _phone_ids():
    return [x.strip() for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()]


def last_seen(now=None):
    """When you last typed anything through any door. None when never."""
    row = store.db().execute("SELECT MAX(ts) FROM messages WHERE role='user'").fetchone()
    return row[0] if row and row[0] else None


def away(now=None):
    now = now or time.time()
    seen = last_seen(now)
    return seen is None or (now - seen) > settings()["away_after_min"] * 60


def quiet(now=None):
    """True inside the quiet hours, e.g. '22:00-07:00'. An empty setting means never."""
    span = settings()["quiet_hours"]
    if not span or "-" not in span:
        return False
    start, end = (tuple(int(x) for x in part.split(":")) for part in span.split("-", 1))
    t = dt.datetime.fromtimestamp(now or time.time())
    cur = (t.hour, t.minute)
    return (start <= cur < end) if start <= end else (cur >= start or cur < end)


def is_urgent(text):
    low = text.lower()
    return "urgent" in low or "!!" in low


# ── the act ─────────────────────────────────────────────────────────────────
def tell(chat_id, door, text, urgent=None, now=None):
    """Put `text` where you will see it. The conversation always; the phone when the
    item is urgent, or when you are away and it is not quiet hours. Says what it did."""
    now = now or time.time()
    urgent = is_urgent(text) if urgent is None else urgent
    store.add_reply(chat_id, text)
    _record(chat_id, "conversation", "sent", "always", text)
    if not policy.allowed("phone"):
        _record(chat_id, "phone", "skipped", "policy: actions.phone is never", text)
        return ["conversation"]
    if not phone_configured():
        _record(chat_id, "phone", "skipped", "Telegram is not configured", text)
        return ["conversation"]
    if not urgent and not away(now):
        _record(chat_id, "phone", "skipped", "you were at the laptop", text)
        return ["conversation"]
    if not urgent and quiet(now):
        _record(chat_id, "phone", "skipped", f"quiet hours {settings()['quiet_hours']}", text)
        return ["conversation"]
    from . import door_telegram                   # late: only when the phone is used
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    why = "urgent" if urgent else "you were away"
    try:
        for uid in _phone_ids():
            door_telegram.send(token, uid, f"{identity.name()}: {text}")
    except Exception as e:
        _record(chat_id, "phone", "failed", f"{type(e).__name__}: {e}", text)
        log(f"reach: phone failed — {e}")
        store.add_reply(chat_id, f"(I tried your phone because {why}, and Telegram refused: {e})")
        return ["conversation"]
    _record(chat_id, "phone", "sent", why, text)
    log(f"reach: phone, {why}")
    return ["conversation", "phone"]
