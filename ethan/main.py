"""Ethan entrypoint. `./run.sh` to start; `--selftest` checks wiring; `--demo` runs one task with no key."""
import os
import sys
import time
import threading
from . import kb, store
from .util import load_env, log
from . import door_console, door_telegram

def selftest():
    load_env()
    log("selftest: config + wiring")
    bmap = kb.kb_map()
    log(f"kbs: {', '.join(bmap)}")
    store.db(); log("task store: ok")
    for name, b in bmap.items():
        if b.get("folder"):
            log(f"kb {name}: local folder, no token needed")
        elif not os.environ.get(b.get("pat_env", "")):
            log(f"kb {name}: SKIP ({b.get('pat_env')} not in .env)")
            continue
        try:
            hits = kb.search(name, "test", k=1)
            log(f"kb {name}: reachable ({len(hits)} hit)")
        except Exception as e:
            log(f"kb {name}: FAILED — {e}")
    log("llm: " + ("key present" if os.environ.get("OPENAI_API_KEY") else "OPENAI_API_KEY missing — fill .env"))
    log("telegram: " + ("token present" if os.environ.get("TELEGRAM_BOT_TOKEN") else "token missing — fill .env"))
    log("selftest done")


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--demo" in sys.argv:
        from . import demo
        sys.exit(demo.main())
    load_env()
    log("Ethan online — Skynet, component one")
    reaped = store.reap_orphans()
    if reaped:
        log(f"reaped {reaped} orphaned running row(s) from the previous process")
    # Every door is thin: it turns input into router.handle() and renders replies.
    # The console runs in a daemon thread and Telegram holds the main thread — but
    # Telegram is optional, and it RETURNS immediately when no token is configured.
    # Returning from here ends main(), which kills the daemon thread with it, so a
    # user who wanted the console alone used to get a process that exited at once.
    # The port is bound here, not in the thread: a port already in use used to kill
    # the thread silently and leave a process holding open for a door that was gone.
    try:
        console = door_console.open_server()
    except OSError as e:
        console = None
        log(f"console door cannot open: {e}. Set ETHAN_CONSOLE_PORT to a free port.")
    if console:
        threading.Thread(target=console.serve_forever, daemon=True).start()
    door_telegram.run()
    if console is None:
        log("no door is open — stopping")
        sys.exit(1)
    log("telegram door is not running — holding open for the console door")
    while True:                  # nothing to block on; sleep rather than spin
        time.sleep(3600)


if __name__ == "__main__":
    main()
