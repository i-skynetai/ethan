"""Ethan entrypoint. `./run.sh` to start; `./run.sh --selftest` to check wiring."""
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
        if not os.environ.get(b["pat_env"]):
            log(f"kb {name}: SKIP ({b['pat_env']} not in .env)")
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
    threading.Thread(target=door_console.run, daemon=True).start()
    door_telegram.run()
    log("telegram door is not running — holding open for the console door")
    while True:                  # nothing to block on; sleep rather than spin
        time.sleep(3600)


if __name__ == "__main__":
    main()
