"""ethan — talk to the running Ethan service from any shell, or any Claude/Codex session.

  ethan "review docs/my-design.md with codex"
  ethan --ingest notes.md --type session-context   save a doc into the right kb
  ethan --status
  ethan -q "..."            print only the final reply
  ethan --chat mywork "..."  keep a named conversation (follow-ups work)

Ethan must already be running — it owns the hands and the kbs. This is only a
client: it posts the ask and follows the replies until the work is finished.
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

PORT = os.environ.get("ETHAN_CONSOLE_PORT", "8787")
BASE = f"http://127.0.0.1:{PORT}"
DONE = ("Session can close", "Not closing")     # Ethan's close-out lines


def get(path, timeout=20):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post(path, body, timeout=15):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def last_reply_id(chat):
    """Where this conversation's reply queue ends now. A reused `--chat` keeps its
    history, and the CLI must print only what comes after THIS ask."""
    try:
        return get(f"/api/conversation?chat={chat}", timeout=5).get("after", 0)
    except Exception:
        return 0


def show_status():
    s = get("/api/state")
    hands = ", ".join(s["hands"])
    print(f"Ethan up {s['uptime_sec'] // 60}m · hands: {hands}")
    for b in s["kbs"]:
        mode = "write" if b["write"] else "read"
        print(f"  {b['name']:14} {b['privacy']:8} {mode:6} {b['tenant']}")
    pend = s["pending"]
    print(f"  {len(pend)} running" if pend else "  idle")
    for t in s["tasks"][:5]:
        print(f"    #{t['id']} {t['state']:11} {t['kind']}/{t['hand']}  {(t['ask'] or '')[:56]}")
    for r in s.get("relays", [])[:5]:
        print(f"    relay #{r['id']} {r['state']:11} to {r['target'] or '?'}  {(r['ask'] or '')[:48]}")
    for r in s.get("scheduled", [])[:5]:
        when = time.strftime("%a %H:%M", time.localtime(r["due"]))
        what = f"watch #{r['what']}" if r.get("kind") == "watch" else r["what"]
        print(f"    reminder #{r['id']} {when}{' every ' + r['every'] if r['every'] else '':14}  {what[:48]}")


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--status", "-s", action="store_true")
    ap.add_argument("--ingest", metavar="FILE")
    ap.add_argument("--type", dest="doc_type", default="other",
                    help="doc type: session-context, skill, learning, design-doc, other")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.add_argument("--chat", default=f"cli-{os.getpid()}")
    ap.add_argument("--cwd", default=os.getcwd(),
                help="where the hand should work (defaults to your current directory)")
    ap.add_argument("--idle", type=int, default=int(os.environ.get("ETHAN_IDLE_LIMIT", "20")))
    ap.add_argument("--help", "-h", action="store_true")
    ap.add_argument("ask", nargs="*")
    a = ap.parse_args()

    if a.help or (not a.ask and not a.status and not a.ingest):
        return print(__doc__.strip())          # help needs no service

    try:
        get("/api/state", timeout=4)
    except Exception:
        sys.exit(f"ethan: not running on {BASE}\n  start it: `ethan-service` (or ./run.sh from a checkout)")

    if a.status:
        return show_status()
    if a.ingest:
        path = os.path.realpath(a.ingest)
        after = last_reply_id(a.chat)
        try:
            r = post("/api/ingest", {"path": path, "doc_type": a.doc_type,
                                     "chat": a.chat, "cwd": a.cwd, "door": "cli"})
        except urllib.error.HTTPError as e:
            sys.exit(f"ethan: refused — {json.loads(e.read()).get('error')}")
        print(f"→ {path}\n  kb={r['kb']} tenant={r['tenant']} "
              f"ontology={r['ontology']} job={r['job_id']}")
        while True:                      # wait for the job report
            d = get(f"/api/replies?chat={a.chat}&after={after}")
            for m in d.get("replies", []):
                after = m["id"]; print(" ", m["text"])
                if m["text"].startswith("ingest "):
                    return
            time.sleep(4)
    if a.help or not a.ask:
        return print(__doc__.strip())

    ask = " ".join(a.ask)
    after = last_reply_id(a.chat)
    try:
        r = post("/api/ask", {"text": ask, "chat": a.chat, "cwd": a.cwd, "door": "cli"})
    except urllib.error.HTTPError as e:
        sys.exit(f"ethan: rejected — {e.read().decode()[:200]}")
    if not r.get("ok"):
        sys.exit(f"ethan: rejected — {r}")

    if not a.quiet:
        print(f"→ ethan ({r.get('chat')}): {ask}", flush=True)

    idle, last, answer, failed = 0, "", "", False
    while True:
        try:
            d = get(f"/api/replies?chat={a.chat}&after={after}")
        except Exception:
            time.sleep(3); continue
        msgs = d.get("replies", [])
        if msgs:
            for m in msgs:
                after, last = m["id"], m["text"]
                if not last.startswith(DONE):     # the close-out is not the answer
                    answer = last
                if last.startswith("error:"):
                    failed = True
                if not a.quiet:
                    print(m["text"], flush=True)
            idle = 0
        elif not d.get("pending"):
            idle += 1
        else:
            idle = 0
        if any(k in last for k in DONE) and not d.get("pending"):
            break
        if idle >= a.idle:
            break
        time.sleep(3)

    if a.quiet:
        print(answer or last)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
