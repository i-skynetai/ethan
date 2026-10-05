"""Who Ethan is when it acts.

Ethan acts as itself, never as you and never as another agent. It uses only accounts
that are its own: the message bridge knows it as the app `ethan`, the harness as the
agent id `ethan`, Telegram as its own bot. Every message it sends, every brief it hands
to a hand and every line it puts on your phone says that Ethan did it, for whom, and
through which door. The name and the owner come from `config/ethan.json`
(`identity.name`, `identity.owner`); `ETHAN_OWNER` in the environment wins.
"""
import os
from .util import cfg


def _conf():
    return cfg("ethan.json").get("identity", {})


def name():
    return _conf().get("name") or "Ethan"


def owner():
    """Whom Ethan works for, as written; never a guess from the machine's user name."""
    return os.environ.get("ETHAN_OWNER") or _conf().get("owner") or "the person who runs it"


def sky_agent_id():
    """How the harness records Ethan's launches. Its own id, not a person's."""
    return _conf().get("agent_id") or "ethan"


def stamp(door):
    """The line that goes with everything Ethan passes on."""
    return f"{name()}, for {owner()}, via the {door} door"
