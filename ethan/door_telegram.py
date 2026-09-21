"""Telegram door — long polling (outbound only; no open ports). One thread per update."""
import os, threading, urllib.parse
from . import router
from .util import http_json, cfg, log


def _api(token, method, **params):
    q = urllib.parse.urlencode(params)
    return http_json(f"https://api.telegram.org/bot{token}/{method}?{q}", timeout=70)


def send(token, chat_id, text):
    for i in range(0, max(len(text), 1), 3800):        # Telegram 4096-char cap
        _api(token, "sendMessage", chat_id=chat_id, text=text[i:i + 3800])


def run():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log("telegram door: TELEGRAM_BOT_TOKEN not set — door disabled")
        return
    allowed = {x.strip() for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()}
    # A token that is set but does not work — revoked, typo, network down at boot —
    # used to raise out of here, through main(), and take the console door with it.
    # An optional door must not be able to end the service.
    try:
        me = _api(token, "getMe")["result"]["username"]
    except Exception as e:
        log(f"telegram door: cannot start ({type(e).__name__}: {e}) — door disabled")
        return
    log(f"telegram door open: @{me} (allowed ids: {sorted(allowed) or 'NONE YET'})")
    offset = 0
    while True:
        try:
            ups = _api(token, "getUpdates", timeout=cfg("ethan.json").get("poll_timeout_sec", 50),
                       offset=offset)["result"]
        except Exception as e:
            log(f"telegram poll error: {e}")
            continue
        for u in ups:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            text, chat = msg.get("text"), msg.get("chat", {}).get("id")
            uid = str(msg.get("from", {}).get("id", ""))
            if not text or chat is None:
                continue
            if uid not in allowed:
                log(f"unauthorized sender: telegram id {uid}")
                send(token, chat, f"Not authorized. Your Telegram id is {uid} — "
                                  f"add it to TELEGRAM_ALLOWED_USER_IDS in .env and restart me.")
                continue
            threading.Thread(target=router.handle, daemon=True,
                             args=(chat, text, lambda t, c=chat: send(token, c, t),
                                   "telegram-private")).start()
