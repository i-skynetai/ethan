"""Typed visual layouts and explicit previews in the canonical Ethan ledger.

Only registered cards and plain display configuration are accepted. A layout is
never code, a data source, a connector, an agent command or an action permission.
"""
import copy
import json
import re
import time
import uuid

from . import store

TTL = 600
_REGISTRY = [
    {"type": "agents", "title": "Agent network", "width": 1, "mandatory": False},
    {"type": "core", "title": "Ethan / Core", "width": 2, "mandatory": True},
    {"type": "tasks", "title": "Tasks & reminders", "width": 1, "mandatory": False},
    {"type": "conversation", "title": "Conversation", "width": 2, "mandatory": True},
    {"type": "approvals", "title": "Your approval", "width": 1, "mandatory": False},
    {"type": "activity", "title": "Activity & results", "width": 1, "mandatory": False},
]


class LayoutError(ValueError):
    pass


def registry():
    return copy.deepcopy(_REGISTRY)


def default():
    return {"version": 1, "widgets": [{"id": w["type"], "type": w["type"],
                                      "width": w["width"], "title": w["title"]} for w in _REGISTRY]}


def validate(layout):
    if not isinstance(layout, dict) or set(layout) != {"version", "widgets"} \
            or type(layout["version"]) is not int or layout["version"] != 1:
        raise LayoutError("layout must have only version=1 and widgets")
    widgets = layout["widgets"]
    if not isinstance(widgets, list) or not 2 <= len(widgets) <= len(_REGISTRY):
        raise LayoutError("layout requires two to six registered cards")
    known = {w["type"]: w for w in _REGISTRY}
    seen, result = set(), []
    for w in widgets:
        if not isinstance(w, dict) or set(w) != {"id", "type", "width", "title"}:
            raise LayoutError("card accepts only id, type, width and title")
        kind = w["type"]
        if not isinstance(kind, str) or kind not in known or w["id"] != kind or kind in seen:
            raise LayoutError("unknown, duplicate or unstable card identity")
        if type(w["width"]) is not int or w["width"] not in (1, 2):
            raise LayoutError("width must be one or two columns")
        title = w["title"]
        if not isinstance(title, str) or not title.strip() or len(title) > 64 \
                or any(ord(c) < 32 or c in "<>" for c in title) or "://" in title or "javascript:" in title.lower():
            raise LayoutError("title must be plain text of one to 64 characters")
        if known[kind]["mandatory"] and (title != known[kind]["title"] or w["width"] != known[kind]["width"]):
            raise LayoutError("core and conversation configuration is fixed")
        seen.add(kind)
        result.append({"id": kind, "type": kind, "width": w["width"], "title": title.strip()})
    if not {"core", "conversation"}.issubset(seen):
        raise LayoutError("core and conversation cannot be hidden or removed")
    order = [w["type"] for w in result]
    if order.index("core") > order.index("conversation"):
        raise LayoutError("core must remain before conversation")
    return {"version": 1, "widgets": result}


def _ensure():
    d = store.db()
    d.execute("CREATE TABLE IF NOT EXISTS hud_layouts(revision INTEGER PRIMARY KEY,ts REAL,layout TEXT,previous INTEGER)")
    d.execute("""CREATE TABLE IF NOT EXISTS hud_layout_previews(
        id TEXT PRIMARY KEY,ts REAL,chat_id TEXT,door TEXT,revision INTEGER,layout TEXT,expires REAL,state TEXT)""")
    d.execute("INSERT OR IGNORE INTO hud_layouts VALUES(0,?,?,NULL)",
              (time.time(), json.dumps(default(), sort_keys=True)))
    d.commit()
    return d


def _head(d):
    revision, raw = d.execute("SELECT revision,layout FROM hud_layouts ORDER BY revision DESC LIMIT 1").fetchone()
    try:
        layout = validate(json.loads(raw))
        recovered = False
    except (ValueError, TypeError):
        layout, recovered = default(), True
    return {"revision": revision, "layout": layout, "recovered": recovered}


def current():
    with store._LOCK:
        return _head(_ensure())


def _revision(value):
    if type(value) is not int or value < 0:
        raise LayoutError("expected_revision must be a nonnegative integer")


def diff(before, after):
    a = {w["id"]: w for w in before["widgets"]}
    b = {w["id"]: w for w in after["widgets"]}
    return {"added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
            "changed": [key for key in sorted(a.keys() & b.keys()) if a[key] != b[key]],
            "order_before": list(a), "order_after": list(b)}


def preview(layout, chat_id="console", door="console"):
    layout = validate(layout)
    if door not in ("console", "cli"):
        raise LayoutError("dashboard changes must come from a desktop door")
    if not isinstance(chat_id, str) or not 1 <= len(chat_id) <= 64:
        raise LayoutError("invalid preview conversation")
    now, pid = time.time(), uuid.uuid4().hex
    with store._LOCK:
        d = _ensure()
        head = _head(d)
        d.execute("INSERT INTO hud_layout_previews VALUES(?,?,?,?,?,?,?,'pending')",
                  (pid, now, chat_id, door, head["revision"], json.dumps(layout, sort_keys=True), now + TTL))
        d.commit()
    return {"preview_id": pid, "expected_revision": head["revision"], "expires": now + TTL,
            "layout": layout, "diff": diff(head["layout"], layout)}


def _write(d, layout, expected_revision):
    head = _head(d)
    if head["revision"] != expected_revision:
        raise LayoutError("dashboard changed; create a fresh preview")
    d.execute("INSERT INTO hud_layouts VALUES(?,?,?,?)",
              (expected_revision + 1, time.time(), json.dumps(layout, sort_keys=True), expected_revision))
    return {"revision": expected_revision + 1, "layout": layout, "recovered": False}


def apply(layout, expected_revision):
    """Explicit API apply of the exact validated layout and previous revision."""
    layout = validate(layout)
    _revision(expected_revision)
    with store._LOCK:
        d = _ensure()
        d.execute("BEGIN IMMEDIATE")
        try:
            result = _write(d, layout, expected_revision)
            d.commit()
            return result
        except Exception:
            d.rollback()
            raise


def apply_preview(preview_id, chat_id="console", door="console"):
    if not isinstance(preview_id, str) or not re.fullmatch(r"[0-9a-f]{32}", preview_id):
        raise LayoutError("invalid dashboard preview ID")
    with store._LOCK:
        d = _ensure()
        d.execute("BEGIN IMMEDIATE")
        try:
            row = d.execute("SELECT revision,layout,expires,state FROM hud_layout_previews "
                            "WHERE id=? AND chat_id=? AND door=?", (preview_id, chat_id, door)).fetchone()
            if not row or row[3] != "pending" or row[2] <= time.time():
                raise LayoutError("preview is unavailable, expired or already used in this conversation")
            layout = validate(json.loads(row[1]))
            result = _write(d, layout, row[0])
            d.execute("UPDATE hud_layout_previews SET state='applied' WHERE id=? AND state='pending'", (preview_id,))
            d.commit()
            return result
        except Exception:
            d.rollback()
            raise


def rollback(expected_revision):
    _revision(expected_revision)
    with store._LOCK:
        d = _ensure()
        d.execute("BEGIN IMMEDIATE")
        try:
            head = _head(d)
            if head["revision"] != expected_revision or expected_revision == 0:
                raise LayoutError("no matching previous dashboard revision")
            row = d.execute("SELECT l.layout FROM hud_layouts h JOIN hud_layouts l ON l.revision=h.previous "
                            "WHERE h.revision=?", (expected_revision,)).fetchone()
            if not row:
                raise LayoutError("previous dashboard revision is unavailable")
            result = _write(d, validate(json.loads(row[0])), expected_revision)
            d.commit()
            return result
        except Exception:
            d.rollback()
            raise


def take(chat_id, text, reply, door):
    """A rule creates a preview. Only an explicit apply command commits it."""
    text = text.strip().lower().rstrip(".!?")
    match = re.fullmatch(r"(hide|show) (agents|tasks|approvals|activity|conversation|core)", text)
    move = re.fullmatch(r"move (agents|tasks|approvals|activity) before (agents|tasks|approvals|activity|conversation|core)", text)
    answer = re.fullmatch(r"apply dashboard ([0-9a-f]{32})", text)
    if not (match or move or answer or text == "reset dashboard"):
        return False
    try:
        if answer:
            result = apply_preview(answer[1], str(chat_id), door)
            reply(f"Dashboard revision {result['revision']} applied. Only visual layout changed.")
            return True
        layout = current()["layout"]
        if text == "reset dashboard":
            layout = default()
        elif match:
            action, kind = match.groups()
            if action == "hide":
                layout["widgets"] = [w for w in layout["widgets"] if w["type"] != kind]
            elif kind not in [w["type"] for w in layout["widgets"]]:
                layout["widgets"].append(next(w for w in default()["widgets"] if w["type"] == kind))
        else:
            kind, before = move.groups()
            widgets = layout["widgets"]
            if kind == before or not {kind, before}.issubset({w["type"] for w in widgets}):
                raise LayoutError("choose two different visible cards")
            moving = next(w for w in widgets if w["type"] == kind)
            widgets.remove(moving)
            widgets.insert(next(i for i, w in enumerate(widgets) if w["type"] == before), moving)
        result = preview(layout, str(chat_id), door)
        reply(f"Dashboard preview {result['preview_id']}: {json.dumps(result['diff'], sort_keys=True)}. "
              f"Nothing changed. Apply with 'apply dashboard {result['preview_id']}' within 10 minutes.")
    except (ValueError, TypeError) as e:
        reply(f"Dashboard change refused: {e}. Nothing changed.")
    return True
