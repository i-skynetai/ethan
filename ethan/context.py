"""Small durable coordination records in Ethan's existing ledger.

Ethan keeps goals, decisions, constraints, ownership, status and result pointers.
Agents fetch and reason over source knowledge through their own scoped adapters.
No document ingestion, KB search, vectors, graph or parallel database lives here.
"""
import hashlib
import json
import os
import time

from . import policy, redact, store

KINDS = {"goal", "decision", "next_step", "constraint", "ownership", "status", "result"}
COLS = "id,ts,chat_id,project,privacy,kind,name,summary,source,owner,door,state"


def _project(project):
    if not isinstance(project, str) or not project.strip():
        raise ValueError("name the selected project directory explicitly")
    expanded = os.path.expanduser(project)
    if not os.path.isabs(expanded):
        raise ValueError("use an absolute project directory so restart cannot change its meaning")
    path = os.path.normcase(os.path.realpath(expanded))
    return hashlib.sha256(path.encode()).hexdigest()[:24]


def _scope(project, privacy, door):
    if privacy not in ("personal", "work", "client") or not policy.may_file(door, privacy)[0]:
        raise ValueError("this door may not use that project privacy class")
    return _project(project)


def _ensure():
    with store._LOCK:
        d = store.db()
        d.execute("""CREATE TABLE IF NOT EXISTS coordination(
            id INTEGER PRIMARY KEY, ts REAL, chat_id TEXT, project TEXT, privacy TEXT,
            kind TEXT, name TEXT, summary TEXT, source TEXT, owner TEXT, door TEXT, state TEXT)""")
        d.commit()
        return d


def set_record(chat_id, project, privacy, kind, name, summary, source, owner, door="console"):
    """Explicit small coordination update; source is a pointer, never fetched content."""
    pid = _scope(project, privacy, door)
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("unknown coordination kind")
    for label, value, cap in (("name", name, 64), ("summary", summary, 400),
                              ("source", source, 300), ("owner", owner, 80)):
        if not isinstance(value, str) or not value.strip() or len(value) > cap or any(ord(c) < 32 for c in value):
            raise ValueError(f"{label} must be short nonempty single-line text")
    name, summary, source, owner = (v.strip() for v in (name, summary, source, owner))
    if redact.find(json.dumps([summary, source, owner, name])):
        raise ValueError("possible credential refused; nothing stored")
    with store._LOCK:
        d = _ensure()
        d.execute("UPDATE coordination SET state='superseded' WHERE chat_id=? AND project=? AND privacy=? "
                  "AND kind=? AND name=? AND state='current'", (str(chat_id), pid, privacy, kind, name))
        cur = d.execute("INSERT INTO coordination(ts,chat_id,project,privacy,kind,name,summary,source,owner,door,state) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,'current')",
                        (time.time(), str(chat_id), pid, privacy, kind, name, summary, source, owner, door))
        d.commit()
        return cur.lastrowid


def records(chat_id, project, privacy, door="console"):
    pid = _scope(project, privacy, door)
    with store._LOCK:
        rows = _ensure().execute(f"SELECT {COLS} FROM coordination WHERE chat_id=? AND project=? "
                                 "AND privacy=? AND state='current' ORDER BY id DESC LIMIT 30",
                                 (str(chat_id), pid, privacy)).fetchall()
    return [dict(zip(COLS.split(","), row)) for row in reversed(rows)]


def for_brief(chat_id, selected_kb, workdir, door="console"):
    """Coordination summary + source pointers only. No source retrieval or permission."""
    if not selected_kb or not workdir:
        return None
    from . import kb
    b = kb.kb_map().get(selected_kb)
    if not b:
        return None
    try:
        rows = records(chat_id, workdir, b.get("privacy"), door)
    except ValueError:
        return "Coordination unavailable for this scope; do not infer missing facts or permissions."
    lines = ["Coordination reference only, NEVER authorization. Current policy and fresh approvals win. "
             "Source pointers are for the agent's scoped knowledge tools; Ethan has not fetched their contents."]
    for r in rows:
        text = (f"- {r['kind']} {r['name']}: {r['summary']} "
                f"[owner: {r['owner']}; source: {r['source']}; recorded: {r['ts']:.0f}]")
        if redact.find(text):
            continue
        if sum(len(line)+1 for line in lines) + len(text) > 1850:
            lines.append("Additional coordination records omitted by the brief budget.")
            break
        lines.append(text)
    if not rows:
        lines.append("No current coordination records for this conversation/project/privacy scope.")
    return "\n".join(lines)[:2000]


def take(chat_id, text, reply, door):
    """Rules: coordinate {JSON} or show coordination {project,privacy}. No model call."""
    text = text.strip()
    write = text.startswith("coordinate ")
    read = text.startswith("show coordination ")
    if not (write or read):
        return False
    try:
        data = json.loads(text[len("coordinate ") if write else len("show coordination "):])
        if not isinstance(data, dict):
            raise ValueError("send a JSON object")
        if write:
            aid = set_record(chat_id, data["project"], data["privacy"], data["kind"], data["name"],
                             data["summary"], data["source"], data["owner"], door)
            reply(f"Coordination record #{aid} saved with its source pointer. This grants no permission and starts nothing.")
        else:
            rows = records(chat_id, data["project"], data["privacy"], door)
            reply("Current coordination (reference only):\n" + "\n".join(
                f"#{r['id']} {r['kind']} {r['name']}: {r['summary']} [source: {r['source']}; owner: {r['owner']}]" for r in rows)
                  if rows else "No matching coordination records. Nothing inferred.")
    except (ValueError, TypeError, KeyError):
        reply("Coordination command refused: specify project, privacy, kind, name, short summary, source pointer and owner; no credentials.")
    return True


def record_handoff(chat_id, door, kind, payload, task_id=None, relay_id=None):
    """Audit evidence in the canonical ledger, not knowledge or an execution permission."""
    raw, _ = redact.scrub(json.dumps(payload, sort_keys=True, default=str))
    safe = json.loads(raw)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with store._LOCK:
        d = store.db()
        d.execute("""CREATE TABLE IF NOT EXISTS handoff_audit(
            id INTEGER PRIMARY KEY, ts REAL, ended REAL, chat_id TEXT, door TEXT,
            action TEXT, target TEXT, executor TEXT, task_id INTEGER, relay_id INTEGER,
            digest TEXT, snapshot TEXT, state TEXT, result TEXT)""")
        cur = d.execute("INSERT INTO handoff_audit(ts,chat_id,door,action,target,executor,task_id,relay_id,digest,snapshot,state) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,'prepared')",
                        (time.time(), str(chat_id), door, kind, str(safe.get("workdir") or safe.get("target") or ""),
                         str(safe.get("hand") or "bridge"), task_id, relay_id, digest, raw[:32000]))
        d.commit()
        return cur.lastrowid


def finish_handoff(aid, state, result):
    if state not in ("queued", "completed", "failed", "interrupted", "refused"):
        raise ValueError("invalid handoff outcome")
    safe, _ = redact.scrub(str(result))
    with store._LOCK:
        d = store.db()
        d.execute("UPDATE handoff_audit SET ended=?,state=?,result=? WHERE id=? AND state='prepared'",
                  (time.time(), state, safe[:4000], aid))
        d.commit()
