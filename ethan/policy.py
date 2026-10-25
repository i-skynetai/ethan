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


def build_level(door_name):
    """What a door may do about starting a hand: "allow" (start when asked), "ask"
    (record the act and wait for 'approve N' from the same door and conversation), or
    False. A legacy boolean true reads as "ask": a setting is never silently widened.
    An unknown door is False."""
    d = door(door_name)
    if not d:
        return False
    v = d.get("build", "ask")
    if v is True:
        return "ask"
    return v if v in ("allow", "ask") else False


def may_build(door_name):
    """Whether a door may start a hand at all, with or without a yes first."""
    return build_level(door_name) is not False


def action(name):
    """allow, ask or never. Unknown actions, and values that are not a level, are never."""
    level = load()["actions"].get(name, "never")
    return level if level in LEVELS else "never"


#: The actions that have a confirmation step ("approve N" / "deny N", see approvals.py).
#: Builds are not here: a door's build level carries its own ask path.
SUPPORTS_ASK = {"relay_implementation"}


def allowed(name):
    """True when the policy says allow, or says ask for an action that has a
    confirmation step. An action set to ask that has NO confirmation step is refused,
    not quietly allowed: Ethan would otherwise claim an approval it cannot give.
    `relay_implementation` is the one action that reads ask as a real step.

    Where each is enforced: remind → clock.take and clock.tick; read_ledger →
    status.text; relay_review_only → relay._relay; relay_implementation → relay._mode;
    watch → watch.take and watch.run; phone → reach.tell; file_to_kb → harvest.apply
    and harvest.ingest. send_in_your_name, push_or_merge and start_or_resume_a_session
    have no code path at all; tests/test_policy.py checks that stays true."""
    level = action(name)
    if level == "ask":
        return name in SUPPORTS_ASK
    return level == "allow"


def refusal(name, what):
    if action(name) == "ask" and name not in SUPPORTS_ASK:
        return (f"The policy says actions.{name} is 'ask', and Ethan has no confirmation step for "
                f"{name} yet; set it to allow or never in config/policy.json. Nothing was done.")
    return f"The policy says {what} (actions.{name} is never in config/policy.json)."
