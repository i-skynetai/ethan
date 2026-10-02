"""`./run.sh --demo` — one task end to end, with no key, no server and no account.

What is real: the router, the hint rule, the KB search, the brief, the launch through
`sky build`, the close-out policy and the ledger. What is not: the hand. `demo/fake-sky`
stands in for the harness and prints a fixed answer instead of starting an agent.

Everything is copied to a temporary folder first, so the demo never touches your
ledger or the shipped notes, and no model key is visible to it: a model call would
fail, so the demo shows that a hinted ask needs none.
"""
import os, shutil, sys, tempfile
from . import util
from .util import ROOT

ASK = "review SHOP-7: is the refund check in refunds.py right?"


def _route_line(line):
    import ast
    r = ast.literal_eval(line[len("route: "):])
    return f"{r['kind']} · kb {r['kb']} · decided by {r['by']}"


def main():
    work = tempfile.mkdtemp(prefix="ethan-demo-")
    shutil.copytree(os.path.join(ROOT, "demo"), work, dirs_exist_ok=True)
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.update(ETHAN_STATE_DIR=os.path.join(work, "state"),
                      ETHAN_KB_MAP=os.path.join(work, "kb-map.json"),
                      SKY_BIN=os.path.join(work, "fake-sky"))
    from . import router, store                 # after the environment is set

    util.sink = []
    launches = []
    def show_log():                              # the route and each launch, as they happen
        while util.sink:
            line = util.sink.pop(0)
            if line.startswith("route: "):
                print(f"router › {_route_line(line)}")
            elif line.startswith("hand:"):
                launches.append(line)
                why = " — the close-out: what is worth keeping?" if len(launches) > 1 else ""
                print(f"launch › {line.split(' in ')[0]}{why}")

    shown = work.replace(tempfile.gettempdir().rstrip("/"), "$TMPDIR")
    print(f"<demo> is {shown} — a fresh copy of demo/\n")
    print(f"you    › {ASK}")
    replies = []
    def reply(msg):
        show_log()
        replies.append(msg)
        print(f"ethan  › {msg.replace(work, '<demo>')}")
    router.handle("demo", ASK, reply, door="console", cwd=os.path.join(work, "shop"))
    show_log()
    util.sink = None

    t = store.recent_tasks(1)[0]
    print(f"\nledger › task #{t['id']} {t['kind']} · kb {t['kb']} · hand {t['hand']} · {t['state']}")
    kept = sorted(os.listdir(os.path.join(work, "kb")))
    print(f"kb     › {', '.join(kept)}")
    print("model  › none called: no model key is visible to the demo, and the hint decided")
    return 0 if any(r.startswith("Session can close") for r in replies) else 1


if __name__ == "__main__":
    sys.exit(main())
