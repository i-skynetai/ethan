"""Read an optional local agent-bridge registry without modifying or waking it."""
from contextlib import closing
import os
import sqlite3
from pathlib import Path


def sessions():
    path = Path(os.environ.get("ETHAN_BRIDGE_DB", str(Path.home() / ".agent-bridge" / "bridge.db")))
    if not path.is_file():
        return {"available": False, "sessions": [], "note": "Agent-bridge is not configured on this laptop."}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM sessions ORDER BY agent, name").fetchall()
        return {"available": True, "sessions": [dict(r) for r in rows],
                "note": "Registered sessions; last recorded status is not proof that a session is running."}
    except sqlite3.Error:
        return {"available": False, "sessions": [], "note": "The agent-bridge registry could not be read."}
