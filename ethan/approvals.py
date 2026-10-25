"""Approvals — the yes before an act the policy marks *ask*.

When a door's build level, or the relay_implementation action, is *ask*, Ethan does
not act. It records exactly what it would do, tells the person, and waits:

  Approval #7 needed — start codex as reviewer in /w/shop for: review SHOP-7.
  Reply 'approve 7' or 'deny 7' here within 10 minutes. Nothing happens until then.

Only "approve <id>" or "deny <id>" counts — never a bare yes, so a word in passing or
a transcribed voice line cannot confirm anything. The answer must come through the
same door and the same conversation that asked; a scheduled run can never answer.
Consuming an approval is one atomic update, so a second approve does nothing. At the
moment of execution the CURRENT policy is checked again, and the act is bound to the
exact payload that was shown (hashed), not to a re-reading of the ask. Nothing that
was pending when Ethan last started is ever executed: ask again. Every decision and
its reason is a row in the ledger.

Until the console has a token (EH-042), a yes through the console or the CLI is as
trustworthy as the loopback interface: any local process can POST to /api/ask as the
console door. Telegram approvals rest on its allow-list of user ids.
"""
import hashlib
import json
import re
import time
from . import store
from .util import cfg, log

#: Approvals from before this process started are never executed.
BOOT = time.time()
_ANSWER = re.compile(r"^\s*(approve|deny)\s+#?(\d+)\s*[.!]?\s*$", re.I)
COLS = "id,ts,chat_id,door,kind,payload,digest,state,expires,decided,note,summary"

#: kind -> fn(payload, chat_id, door, reply) -> outcome text. Registered by the module
#: that knows how to do the act (router for builds, relay for relays).
EXECUTORS = {}
#: kind -> fn(payload, why). Called when an approval is denied or expires.
CANCELLERS = {}


def ttl():
    return int((cfg("ethan.json").get("approvals") or {}).get("ttl_sec", 600))


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ── the ledger ──────────────────────────────────────────────────────────────
def _ensure():
    with store._LOCK:
        d = store.db()
        d.execute("""CREATE TABLE IF NOT EXISTS approvals(
            id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, door TEXT, kind TEXT, payload TEXT,
            digest TEXT, state TEXT, expires REAL, decided REAL, note TEXT, summary TEXT)""")
        d.commit()
        return d


def list_pending(chat_id, door):
    """For a display: the approvals still answerable from this conversation and door,
    oldest first, with id, kind, summary, created, expires and state only — never the
    brief, the payload or anything from an account. Read-only."""
    return [{"id": r["id"], "kind": r["kind"], "summary": r["summary"] or "", "created": r["ts"],
             "expires": r["expires"], "state": r["state"]}
            for r in pending(chat_id) if r["door"] == door]


def _rows(where="1=1", args=()):
    with store._LOCK:
        rows = _ensure().execute(f"SELECT {COLS} FROM approvals WHERE {where} ORDER BY id", args).fetchall()
    return [dict(zip(COLS.split(","), r)) for r in rows]


def get(aid):
    rows = _rows("id=?", (aid,))
    return rows[0] if rows else None


def _transition(aid, from_state, to_state, note):
    """Move one approval from one state to another, atomically. False when another
    thread got there first: the caller then neither cancels nor reports its own verdict."""
    with store._LOCK:
        d = _ensure()
        cur = d.execute("UPDATE approvals SET state=?, decided=?, note=? WHERE id=? AND state=?",
                        (to_state, time.time(), note, aid, from_state))
        d.commit()
        return cur.rowcount == 1


def _note(aid, note):
    """Record the outcome on an approval that is already approved."""
    with store._LOCK:
        d = _ensure()
        d.execute("UPDATE approvals SET note=? WHERE id=? AND state='approved'", (note, aid))
        d.commit()


def _expire(row, why):
    """Pending → expired, and the act cancelled, only if nobody approved it meanwhile."""
    if _transition(row["id"], "pending", "expired", why):
        _cancel(row, why)
        return True
    return False


def _deny(row, reply):
    """Pending → denied, and the act cancelled, only if nobody approved it meanwhile."""
    aid = row["id"]
    if _transition(aid, "pending", "denied", "denied by the person"):
        _cancel(row, "denied")
        reply(f"Approval #{aid} denied. Nothing was done.")
        return True
    now_row = get(aid)
    reply(f"Approval #{aid} was already {now_row['state']} a moment ago, so your deny changed nothing.")
    return False


def pending(chat_id=None, now=None):
    """Approvals still waiting, in this conversation or all. Ones that timed out are
    marked expired on the way, and their act is cancelled."""
    now = now or time.time()
    rows = _rows("state='pending'" + ("" if chat_id is None else " AND chat_id=?"),
                 () if chat_id is None else (str(chat_id),))
    live = []
    for r in rows:
        if r["expires"] <= now or r["ts"] < BOOT:
            _expire(r, "timed out" if r["ts"] >= BOOT else "created before Ethan last started")
        else:
            live.append(r)
    return live


def _cancel(row, why):
    fn = CANCELLERS.get(row["kind"])
    if fn:
        try:
            fn(json.loads(row["payload"]), why)
        except Exception as e:                    # a cancel must never break the caller
            log(f"approval #{row['id']}: cancel failed: {type(e).__name__}: {e}")


# ── asking ──────────────────────────────────────────────────────────────────
def request(chat_id, door, kind, payload, describe, reply):
    """Record exactly what would be done, tell the person, and do nothing."""
    now = time.time()
    with store._LOCK:
        d = _ensure()
        cur = d.execute("INSERT INTO approvals(ts,chat_id,door,kind,payload,digest,state,expires,summary) "
                        "VALUES(?,?,?,?,?,?,'pending',?,?)",
                        (now, str(chat_id), door, kind, json.dumps(payload, sort_keys=True, default=str),
                         _digest(payload), now + ttl(), describe[:300]))
        d.commit()
        aid = cur.lastrowid
    log(f"approval #{aid} ({kind}) waiting on the {door} door")
    reply(f"Approval #{aid} needed — {describe}. Reply 'approve {aid}' or 'deny {aid}' here within "
          f"{max(1, ttl() // 60)} minutes. Nothing happens until then.")
    return aid


# ── answering ───────────────────────────────────────────────────────────────
def take(chat_id, text, reply, door, scheduled=False, now=None):
    """Handle 'approve N' / 'deny N', and say whether the ask was one."""
    m = _ANSWER.match(text)
    if not m:
        return False
    verb, aid = m.group(1).lower(), int(m.group(2))
    now = now or time.time()
    if scheduled:
        reply("A scheduled run cannot approve or deny anything. Nothing was done.")
        return True
    row = get(aid)
    if not row or row["chat_id"] != str(chat_id) or row["door"] != door:
        # the same words for "no such approval" and "not yours to answer": no probing
        reply(f"There is no approval #{aid} waiting in this conversation through the {door} door. Nothing was done.")
        return True
    if row["state"] != "pending":
        reply(f"Approval #{aid} was already {row['state']}" + (f" ({row['note']})" if row["note"] else "") + ". Nothing was done.")
        return True
    if row["ts"] < BOOT:
        if _expire(row, "created before Ethan last started"):
            reply(f"Approval #{aid} was asked before Ethan last started, so it has lapsed. Ask again. Nothing was done.")
        else:
            reply(f"Approval #{aid} was already {get(aid)['state']}. Nothing was done.")
        return True
    if row["expires"] <= now:
        if _expire(row, "timed out"):
            reply(f"Approval #{aid} timed out. Ask again. Nothing was done.")
        else:
            reply(f"Approval #{aid} was already {get(aid)['state']}. Nothing was done.")
        return True
    if verb == "deny":
        _deny(row, reply)
        return True
    # approve: one atomic consumption; a second approve finds nothing to take
    with store._LOCK:
        d = _ensure()
        cur = d.execute("UPDATE approvals SET state='approved', decided=? WHERE id=? AND state='pending' AND expires>?",
                        (now, aid, now))
        d.commit()
        taken = cur.rowcount == 1
    if not taken:
        reply(f"Approval #{aid} could not be taken: it was decided or timed out a moment ago. Nothing was done.")
        return True
    payload = json.loads(row["payload"])
    if _digest(payload) != row["digest"]:
        _note(aid, "refused: the stored payload no longer matches what was approved")
        reply(f"Approval #{aid}: the stored act no longer matches what you were shown, so nothing was done.")
        return True
    fn = EXECUTORS.get(row["kind"])
    if not fn:
        _note(aid, f"refused: nothing knows how to do a {row['kind']}")
        reply(f"Approval #{aid}: nothing is registered to carry out a {row['kind']}. Nothing was done.")
        return True
    try:
        outcome = fn(payload, chat_id, door, reply, aid=aid)   # rechecks the current policy itself
    except Exception as e:
        _note(aid, f"failed: {type(e).__name__}: {e}")
        reply(f"Approval #{aid}: the act failed — {type(e).__name__}: {e}")
        return True
    _note(aid, outcome or "done")
    return True
