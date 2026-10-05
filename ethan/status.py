"""The status answer — what is running, what just finished, what is still unanswered.

Read from the ledger, never from a model. The router's `status` kind, the console's
`status` shortcut and `ethan --status` all come here, so there is one answer.
"""
import re
import time
from . import clock, policy, relay, store, todo


def _age(ts):
    mins = int((time.time() - (ts or time.time())) // 60)
    return f"{mins} min" if mins < 120 else f"{mins // 60} h"


_WANTS = re.compile(r"^\s*(?:(?:what(?:'s| is) (?:running|pending|the status|going on))|status|anything pending)\s*\??\s*$", re.I)


def wants(text):
    """The asks that are a status question and nothing else, read by a rule."""
    return bool(_WANTS.match(text))


def text():
    if not policy.allowed("read_ledger"):
        return policy.refusal("read_ledger", "I may not read the ledger back to you")
    if relay.bridge_dir():
        relay.follow()                           # say what is true now, not at the last poll
    running = store.pending()
    done = [t for t in store.recent_tasks(40) if t["state"] != "running"][:5]
    waiting = store.open_relays()
    lines = []
    if running:
        lines.append(f"{len(running)} running:")
        lines += [f"  #{t['id']} {t['kind']}/{t['hand']} — {(t['ask'] or '')[:70]}" for t in running]
    else:
        lines.append("Nothing is running.")
    if waiting:
        lines.append(f"{len(waiting)} relay(s) not yet answered:")
        lines += [f"  relay #{r['id']} to {r['target']} — {r['state']} for {_age(r['updated'])}"
                  for r in waiting]
    tasks = todo.open_tasks()
    if tasks:
        overdue = sum(1 for t in tasks if t["due"] and t["due"] < time.time())
        lines.append(f"{len(tasks)} open task(s)" + (f", {overdue} overdue" if overdue else "")
                     + " — say 'my tasks'.")
    due = clock.scheduled()
    if due:
        lines.append(f"{len(due)} scheduled:")
        lines += [f"  reminder #{r['id']} {clock._when(r['due'])}"
                  f"{' every ' + r['every'] if r['every'] else ''} — {clock.describe(r)[:70]}" for r in due[:5]]
    if done:
        lines.append("Last finished:")
        lines += [f"  #{t['id']} {t['state']} {t['kind']}/{t['hand']} — {(t['ask'] or '')[:70]}"
                  for t in done]
    return "\n".join(lines)
