"""Bounded request replay in the existing ledger; never dispatches provider work.

Current adapters deliver guarded final replies, not text deltas. Cancellation stops
local waiting; a bound relay remains authoritative and may finish independently.
"""
from contextlib import contextmanager
import hashlib
import json
import os
import re
import threading
import time
import uuid

from . import context, redact, selected_chat, store

MAX_EVENTS = 128
MAX_TEXT = 32000
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
_INSTANCE = uuid.uuid4().hex
_ACTIVE = threading.local()
_COLS = "id,chat,door,digest,instance,state,created,updated,seq,scope,capabilities"


class RequestError(ValueError):
    pass


class Conflict(RequestError):
    pass


class NotFound(RequestError):
    pass


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise RequestError("request_id must be 32 lowercase hexadecimal characters")


def _ensure():
    d = store.db()
    d.execute("""CREATE TABLE IF NOT EXISTS conversation_requests(
        id TEXT PRIMARY KEY, chat TEXT, door TEXT, digest TEXT, instance TEXT,
        state TEXT, created REAL, updated REAL, seq INTEGER, scope TEXT, capabilities TEXT)""")
    d.execute("""CREATE TABLE IF NOT EXISTS conversation_events(
        request_id TEXT, seq INTEGER, kind TEXT, ts REAL, text TEXT,
        PRIMARY KEY(request_id,seq))""")
    d.execute("""CREATE TABLE IF NOT EXISTS conversation_request_relays(
        relay_id INTEGER PRIMARY KEY, request_id TEXT, notified_state TEXT)""")
    d.commit()
    return d


def _row(d, request_id):
    row = d.execute(f"SELECT {_COLS} FROM conversation_requests WHERE id=?", (request_id,)).fetchone()
    if row is None:
        raise NotFound("No request in this conversation and door")
    return dict(zip(_COLS.split(","), row))


def _public(d, row):
    result = {key: row[key] for key in ("id", "chat", "door", "state", "created", "updated")}
    result.update(scope=json.loads(row["scope"]), capabilities=json.loads(row["capabilities"]), after=row["seq"])
    bound = d.execute("SELECT relay_id FROM conversation_request_relays WHERE request_id=? ORDER BY relay_id",
                      (row["id"],)).fetchall()
    if bound:
        result["relay_id"] = bound[0][0]
    return result


def _scoped(d, request_id, chat, door):
    row = _row(d, request_id)
    if row["chat"] != str(chat) or row["door"] != door:
        raise NotFound("No request in this conversation and door")
    return row


def _append(d, request_id, kind, text, terminal=False):
    # A write acquires SQLite's writer lock before reading the next sequence, so
    # independent processes cannot choose the same cursor.
    d.execute("UPDATE conversation_requests SET updated=updated WHERE id=?", (request_id,))
    row = _row(d, request_id)
    if row["state"] in TERMINAL and not terminal:
        return False
    cap = MAX_EVENTS if terminal else MAX_EVENTS-2
    if row["seq"] >= cap:
        return False
    now = time.time()
    seq = row["seq"]+1
    d.execute("UPDATE conversation_requests SET seq=?,updated=? WHERE id=?", (seq, now, request_id))
    d.execute("INSERT INTO conversation_events(request_id,seq,kind,ts,text) VALUES(?,?,?,?,?)",
              (request_id, seq, kind, now, text))
    return True


def _end(d, request_id, state, text):
    cur = d.execute("UPDATE conversation_requests SET state=?,updated=? WHERE id=? "
                    "AND state NOT IN ('completed','failed','cancelled','interrupted')",
                    (state, time.time(), request_id))
    if cur.rowcount:
        safe, _ = redact.gate_output(str(text))
        kind = {"failed": "error", "cancelled": "cancelled", "interrupted": "interrupted"}.get(state, "status")
        _append(d, request_id, kind, safe[:4000], terminal=True)
    d.commit()
    return bool(cur.rowcount)


def _inputs(inputs, text, cwd, provider_ref, privacy):
    if isinstance(inputs, dict):
        if any(v is not None for v in (text, cwd, provider_ref, privacy)):
            raise RequestError("Use either request inputs or explicit text fields")
        if set(inputs)-{"text", "cwd", "chat_provider_ref", "chat_privacy"}:
            raise RequestError("Unknown request inputs")
        data = {key: inputs.get(key) for key in ("text", "cwd", "chat_provider_ref", "chat_privacy")}
    else:
        if inputs is not None:
            if text is not None or not isinstance(inputs, str):
                raise RequestError("The ask must be text")
            text = inputs
        data = {"text": text, "cwd": cwd, "chat_provider_ref": provider_ref, "chat_privacy": privacy}
    ask = data["text"]
    if not isinstance(ask, str) or not ask.strip() or len(ask) > 12000:
        raise RequestError("The ask must contain 1–12000 characters; it was not shortened")
    for key, value in data.items():
        if value is not None and not isinstance(value, str):
            raise RequestError(f"{key} must be text or absent")
    if redact.find(json.dumps(data, ensure_ascii=False)):
        raise RequestError("Recognized credential refused before request persistence")
    project, privacy, provider = data["cwd"], data["chat_privacy"], data["chat_provider_ref"]
    if privacy is not None and privacy not in ("personal", "work", "client"):
        raise RequestError("Unknown project privacy")
    if project is not None and (not project or not os.path.isabs(os.path.expanduser(project))
                                or len(project) > 4096 or any(ord(c) < 32 for c in project)):
        raise RequestError("Choose an absolute project directory")
    if privacy is not None and project is None:
        raise RequestError("Project privacy requires an explicit project directory")
    if provider is not None and not re.fullmatch(r"(?:claude|codex):[A-Za-z0-9_-]{1,128}", provider):
        raise RequestError("Choose an explicit registered session reference")
    return data


def create(request_id, chat, door, inputs=None, *, text=None, cwd=None, provider_ref=None, privacy=None):
    """Both dict inputs and the previously agreed text/keyword call normalize here."""
    _id(request_id)
    if not isinstance(chat, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", chat):
        raise RequestError("Invalid conversation identity")
    if not isinstance(door, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", door):
        raise RequestError("Invalid originating door")
    data = _inputs(inputs, text, cwd, provider_ref, privacy)
    if data["chat_provider_ref"] is not None:
        selected_chat.scope(chat, data["cwd"], data["chat_privacy"], door, data["chat_provider_ref"])
    scope = {"project_id": context._project(data["cwd"]) if data["cwd"] else None,
             "privacy": data["chat_privacy"], "provider_ref": data["chat_provider_ref"]}
    capabilities = {"provider_transport": "bridge_status_final" if data["chat_provider_ref"] else "configured_router_final",
                    "live_text_deltas": False, "text_delivery": "whole_answer_guarded_final",
                    "cancel_semantics": "stop_waiting_only_remote_work_may_continue"}
    digest = hashlib.sha256(json.dumps([chat, door, data], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with store._LOCK:
        d = _ensure()
        now = time.time()
        cur = d.execute("""INSERT OR IGNORE INTO conversation_requests
            (id,chat,door,digest,instance,state,created,updated,seq,scope,capabilities)
            VALUES(?,?,?,?,?,'accepted',?,?,0,?,?)""",
            (request_id, chat, door, digest, _INSTANCE, now, now, json.dumps(scope), json.dumps(capabilities)))
        row = _row(d, request_id)
        if row["digest"] != digest:
            d.rollback()
            raise Conflict("This request ID already identifies different immutable input")
        if cur.rowcount:
            _append(d, request_id, "status", "Accepted by the local coordinator; provider work has not started.")
        d.commit()
        return {"created": bool(cur.rowcount), "request": _public(d, _row(d, request_id))}


def claim(request_id):
    _id(request_id)
    with store._LOCK:
        d = _ensure()
        _row(d, request_id)
        cur = d.execute("UPDATE conversation_requests SET state='running',updated=? "
                        "WHERE id=? AND state='accepted' AND instance=?", (time.time(), request_id, _INSTANCE))
        if cur.rowcount:
            _append(d, request_id, "status", "Processing through the existing router; no text deltas are available.")
        d.commit()
        return bool(cur.rowcount)


start = claim


def events(request_id, chat, door, after=0, limit=100):
    _id(request_id)
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise RequestError("Invalid event cursor or limit")
    with store._LOCK:
        d = _ensure()
        row = _scoped(d, request_id, chat, door)
        if after > row["seq"]:
            raise RequestError("Event cursor is beyond this request")
        rows = d.execute("SELECT seq,kind,ts,text FROM conversation_events "
                         "WHERE request_id=? AND seq>? ORDER BY seq LIMIT ?", (request_id, after, limit)).fetchall()
        items = [{"request_id": request_id, "seq": seq, "kind": kind, "ts": ts, "text": text}
                 for seq, kind, ts, text in rows]
        return {"request": _public(d, row), "events": items, "after": items[-1]["seq"] if items else after}


def should_deliver(request_id):
    if request_id is None:
        return True
    with store._LOCK:
        return _row(_ensure(), request_id)["state"] not in TERMINAL


def record_reply(request_id, text):
    if not isinstance(text, str):
        raise RequestError("Reply must be text")
    with store._LOCK:
        d = _ensure()
        if _row(d, request_id)["state"] in TERMINAL:
            return False
        safe, kinds = redact.gate_output(text)
        if kinds or len(text) > MAX_TEXT:
            _end(d, request_id, "failed", safe if kinds else "Reply exceeded the bounded output limit; text was withheld.")
            return False
        if not _append(d, request_id, "reply", safe):
            _end(d, request_id, "failed", "Request event limit reached; further replies were withheld.")
            return False
        d.commit()
        return True


def status(request_id, text):
    with store._LOCK:
        d = _ensure()
        if _row(d, request_id)["state"] in TERMINAL:
            return False
        safe, kinds = redact.gate_output(str(text))
        if kinds:
            _end(d, request_id, "failed", safe)
            return False
        result = _append(d, request_id, "status", safe[:1000])
        d.commit()
        return result


def fail(request_id, generic_text):
    with store._LOCK:
        d = _ensure()
        _row(d, request_id)
        _end(d, request_id, "failed", generic_text)
        return _public(d, _row(d, request_id))


def cancel(request_id, chat, door):
    _id(request_id)
    with store._LOCK:
        d = _ensure()
        _scoped(d, request_id, chat, door)
        _end(d, request_id, "cancelled", "Stopped waiting locally. Remote work may continue and its independent relay result remains in the ledger.")
        return _public(d, _row(d, request_id))


def bind_relay(request_id, relay_id):
    if request_id is None:
        return False
    with store._LOCK:
        d = _ensure()
        request = _row(d, request_id)
        relay = store.relay(relay_id)
        expected = json.loads(request["scope"])["provider_ref"]
        if not relay or relay["chat_id"] != request["chat"] or relay["door"] != request["door"]:
            raise RequestError("Relay does not match the originating request scope")
        if not relay.get("message_id") or (expected and relay.get("target_ref") != expected):
            return False
        cur = d.execute("INSERT OR IGNORE INTO conversation_request_relays(relay_id,request_id) VALUES(?,?)",
                        (relay_id, request_id))
        bound = d.execute("SELECT request_id FROM conversation_request_relays WHERE relay_id=?", (relay_id,)).fetchone()[0]
        if bound != request_id:
            d.rollback()
            raise Conflict("Relay is already bound to another request")
        d.commit()
        # The existing follower may have finalized the relay before this request
        # link was attached. Backfill its gated canonical result once, not a send.
        if relay["state"] in ("completed", "failed"):
            finish_relay(relay_id, relay["state"], relay.get("result") or "")
        return bool(cur.rowcount)


def finish(request_id):
    with store._LOCK:
        d = _ensure()
        row = _row(d, request_id)
        if row["state"] in TERMINAL:
            return _public(d, row)
        relays = d.execute("SELECT r.state FROM conversation_request_relays b JOIN relays r ON r.id=b.relay_id "
                           "WHERE b.request_id=?", (request_id,)).fetchall()
        final = {"completed", "failed", "refused", "dropped", "cancelled"}
        if any(state not in final for (state,) in relays):
            d.execute("UPDATE conversation_requests SET state='waiting',updated=? WHERE id=? "
                      "AND state NOT IN ('completed','failed','cancelled','interrupted')", (time.time(), request_id))
            if row["state"] != "waiting":
                _append(d, request_id, "status", "Waiting for the existing relay; queued or delivered is not answered.")
            d.commit()
        else:
            failed = any(state != "completed" for (state,) in relays)
            _end(d, request_id, "failed" if failed else "completed", "Request failed." if failed else "Request processing completed.")
        return _public(d, _row(d, request_id))


def finish_relay(relay_id, state, safe_text):
    """Record a bound relay's actual observed status; never change or cancel it."""
    with store._LOCK:
        d = _ensure()
        binding = d.execute("SELECT request_id,notified_state FROM conversation_request_relays WHERE relay_id=?", (relay_id,)).fetchone()
        if binding is None:
            return True                       # Legacy relay delivery remains independent.
        request_id, previous = binding
        row = _row(d, request_id)
        if row["state"] in TERMINAL or previous == state:
            return False
        relay = store.relay(relay_id)
        if relay is None or relay["state"] != state:
            raise RequestError("Relay event does not match the canonical relay state")
        expected = json.loads(row["scope"])["provider_ref"]
        if (relay["chat_id"] != row["chat"] or relay["door"] != row["door"]
                or (expected and relay.get("target_ref") != expected)):
            raise RequestError("Relay event no longer matches this request scope")
        if state in ("completed", "failed") and (safe_text or "") != (relay.get("result") or ""):
            raise RequestError("Relay event must use the canonical gated result")
        d.execute("UPDATE conversation_request_relays SET notified_state=? WHERE relay_id=?", (state, relay_id))
        safe, kinds = redact.gate_output(safe_text or "")
        if kinds or len(safe) > MAX_TEXT:
            _end(d, request_id, "failed", safe if kinds else "Relay answer exceeded the bounded output limit; text withheld.")
            return False
        if state in ("completed", "failed"):
            if not _append(d, request_id, "final" if state == "completed" else "error", safe):
                _end(d, request_id, "failed", "Request event limit reached; final text remains in the independent relay ledger.")
                return False
        else:
            _append(d, request_id, "status", f"Existing relay is {state}; not an answer.")
        d.commit()
        finish(request_id)
        return True


def startup_recover():
    """Mark old-instance API work interrupted once at startup; never resume it."""
    with store._LOCK:
        d = _ensure()
        rows = d.execute("SELECT id FROM conversation_requests WHERE instance<>? AND state IN ('accepted','running')",
                         (_INSTANCE,)).fetchall()
        for (request_id,) in rows:
            _end(d, request_id, "interrupted", "Service restarted before this request finished; nothing was automatically sent again.")
        return len(rows)


recover = startup_recover


@contextmanager
def active_request(request_id):
    previous = getattr(_ACTIVE, "request_id", None)
    _ACTIVE.request_id = request_id
    try:
        yield request_id
    finally:
        _ACTIVE.request_id = previous


def current_request():
    return getattr(_ACTIVE, "request_id", None)


class Observer:
    def __init__(self, request_id):
        self.id = request_id

    def reply(self, text):
        return record_reply(self.id, text)

    def status(self, text):
        return status(self.id, text)

    def cancelled(self):
        return not should_deliver(self.id)

    def attach_relay(self, relay_id):
        return bind_relay(self.id, relay_id)

    def complete(self):
        return finish(self.id)

    def fail(self, text):
        return fail(self.id, text)
