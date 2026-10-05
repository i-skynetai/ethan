"""The rules, read in one place.

`config/policy.json` says what each door may do and which actions are allowed, need
the person's word in the ask itself, or are never done. Every module that enforces a
rule asks this module; nothing else reads the file. An installed copy that still has
the older `doors.json` is read through the same functions, with the shipped actions.

Fail closed: an unknown door may do nothing, and an unknown action is `never`.
"""
from .util import DEFAULTS, cfg, config_dir, log
import json
import os

#: What the shipped policy allows. An action missing from the file gets `never`.
ACTIONS = ("remind", "read_ledger", "relay_review_only", "relay_implementation", "watch",
           "phone", "file_to_kb", "send_in_your_name", "push_or_merge", "start_or_resume_a_session")
LEVELS = ("allow", "ask", "never")

_LEGACY_WARNED = []


def _shipped():
    """The policy as shipped in `ethan/defaults/policy.json`, as a fresh dict."""
    with open(os.path.join(DEFAULTS, "policy.json"), encoding="utf-8") as f:
        p = json.load(f)
    return {"doors": {k: dict(v) for k, v in p["doors"].items() if not k.startswith("_")},
            "actions": {k: v for k, v in p["actions"].items() if not k.startswith("_")}}


def load():
    """The policy as a dict with `doors` and `actions`."""
    if os.path.isfile(os.path.join(config_dir(), "policy.json")):
        p = cfg("policy.json")
    else:                                         # a config folder from before 0.3.0
        legacy = cfg("doors.json")
        if not _LEGACY_WARNED:
            log("No policy.json — reading doors from doors.json over the shipped policy. "
                "Copy ethan/defaults/policy.json into your config folder.")
            _LEGACY_WARNED.append(True)
        p = _shipped()                            # the shipped actions, every one of them
        for name, d in legacy.items():            # and the person's doors over the shipped doors
            if not name.startswith("_"):
                p["doors"][name] = {**p["doors"].get(name, {}), **d}
    return {"doors": {k: v for k, v in p.get("doors", {}).items() if not k.startswith("_")},
            "actions": {k: v for k, v in p.get("actions", {}).items() if not k.startswith("_")}}


def doors():
    return load()["doors"]


def door(name):
    """A door's rules, or None for a door the policy does not know."""
    return doors().get(name)


def may_file(door_name, privacy_class):
    """Whether this door may file into a KB of this class, and the classes it may."""
    d = door(door_name)
    allowed = (d or {}).get("classes") or []
    return (d is not None and privacy_class in allowed), allowed


def may_relay(door_name):
    return bool((door(door_name) or {}).get("relay"))


def may_build(door_name):
    """Starting a hand needs a person at a door. The clock, for one, may not."""
    d = door(door_name)
    return bool(d) and bool(d.get("build", True))


def action(name):
    """allow, ask or never. Unknown actions, and values that are not a level, are never."""
    level = load()["actions"].get(name, "never")
    return level if level in LEVELS else "never"


def allowed(name):
    """True unless the policy says never. For acts that cannot be asked for more
    explicitly than by asking — a reminder, a status, a review-only relay, a watch, the
    phone, filing to a KB — allow and ask mean the same thing. Only
    `relay_implementation` reads *ask* differently (see `relay._mode`).

    Where each is enforced: remind → clock.take and clock.tick; read_ledger →
    status.text; relay_review_only → relay._relay; relay_implementation → relay._mode;
    watch → watch.take and watch.run; phone → reach.tell; file_to_kb → harvest.apply
    and harvest.ingest. send_in_your_name, push_or_merge and start_or_resume_a_session
    have no code path at all; tests/test_policy.py checks that stays true."""
    return action(name) != "never"


def refusal(name, what):
    return f"The policy says {what} (actions.{name} is never in config/policy.json)."
