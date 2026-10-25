"""Resolve an explicitly selected existing session; never dispatch or authenticate."""
import re
from . import bridge_registry


class SelectionError(ValueError):
    pass


def resolve(ref):
    """Return minimal target fields from the current registry, or refuse.

    Registration is not proof of a live listener. The caller must use the normal
    relay policy/send/follow path and report queued or unavailable honestly.
    """
    if not isinstance(ref, str) or not re.fullmatch(r"(?:claude|codex):[A-Za-z0-9_-]{1,128}", ref):
        raise SelectionError("Choose an explicit registered Claude or Codex session reference.")
    agent, native_id = ref.split(":", 1)
    registry = bridge_registry.sessions()
    if not registry.get("available"):
        raise SelectionError("The session registry is unavailable; nothing was selected.")
    matches = [row for row in registry.get("sessions", [])
               if isinstance(row, dict) and row.get("agent") == agent
               and row.get("native_id") == native_id]
    if len(matches) != 1:
        raise SelectionError("That session reference is missing or ambiguous; select again.")
    name = matches[0].get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 200 or any(ord(c) < 32 for c in name):
        raise SelectionError("That session has invalid display metadata; select again.")
    return {"agent": agent, "native_id": native_id, "name": name}
