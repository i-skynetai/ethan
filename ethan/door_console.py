"""Console door — a local web page that is both a window and a door.

Window: live task ledger, which hand is running right now, and the running hand's
        output tailed as it is produced.
Door:   the ask box goes through router.handle(), exactly the path Telegram uses.

Stdlib only. Replies are pulled (the page polls) rather than pushed, which is the
only difference from Telegram; router.handle() does not know or care.
"""
import json, os, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import clock, kb, harvest, router, status, store, bridge_registry
from .util import cfg, log

CHAT = "console"
STARTED = time.time()
_ACTIVE = 0
_ACTIVITY_LOCK = threading.Lock()


_CHAT_OK = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _chat_id(raw):
    """Any caller may name its own conversation, so a CLI or another service gets
    its own reply queue instead of stealing the console's."""
    raw = (raw or "").strip() or CHAT
    return raw if _CHAT_OK.match(raw) else CHAT


#: The doors that speak through this server. `bin/ethan` says it is the CLI, so its
#: asks are recorded and policed as the CLI's, not the console page's. Any other
#: name a caller sends is ignored: a door's privacy classes cannot be claimed.
DOORS = ("console", "cli")


def _door(raw):
    return raw if raw in DOORS else CHAT


def _ask(text, chat=CHAT, cwd=None, door=CHAT, chat_provider_ref=None):
    """Run one ask in the background; replies land in the pull queue.

    The ask is stored by router.handle, not here: storing it twice used to put it
    in front of the model twice."""
    global _ACTIVE
    with _ACTIVITY_LOCK:
        _ACTIVE += 1
    store.note_desktop()                          # you are at the laptop: reach.away() reads this
    def reply(msg):
        store.add_reply(chat, msg)
    try:
        ask = text.strip().lower().rstrip("?.!")
        if ask in ("help", "what can you do", "what can you do for me", "show connected agents", "show my agents", "status"):
            store.remember(chat, "user", text)
            if ask in ("show connected agents", "show my agents"):
                registry = bridge_registry.sessions()
                reply(registry["note"] + "\n\n" + "\n".join(f"{s['agent'].title()}: {s['name']}" for s in registry["sessions"]))
            elif ask == "status":
                reply(status.text())
            else:
                reply("I'm Ethan. I help keep context, requests and coding agents organised. You choose the outcome; I help coordinate the work.\n\nTry ‘show connected agents’ or ‘status’—no model key needed. I can pass an ask to a registered Claude or Codex session that is already running: ‘ask the claude session <name> to …’. My general conversation still needs a router key, and new build tasks with the local-folder KB may still fail (roadmap EH-060).")
            return
        options = {"door": door, "cwd": cwd}
        if chat_provider_ref:
            options["chat_provider_ref"] = chat_provider_ref
        router.handle(chat, text, reply, **options)
    except Exception as e:                      # never let a bad ask kill the door
        store.add_reply(chat, f"error: {e}")
        log(f"console ask failed: {e}")
    finally:
        with _ACTIVITY_LOCK:
            _ACTIVE -= 1


def _pending_approvals():
    from . import approvals
    return approvals.list_pending(CHAT, CHAT)


def _state():
    bmap = kb.kb_map()
    pending = store.pending()
    with _ACTIVITY_LOCK:
        active = _ACTIVE
    return {
        "up_since": STARTED,
        "uptime_sec": int(time.time() - STARTED),
        "kbs": [{"name": n, "purpose": b.get("purpose", ""), "privacy": b.get("privacy", "?"),
                    "write": bool(b.get("write")), "repo": b.get("repo", ""),
                    "tenant": b.get("tenant_code", "")} for n, b in bmap.items()],
        "hands": list(cfg("ethan.json")["hands"]),
        "tasks": store.recent_tasks(40),
        "runs": store.recent_runs(30),
        "pending": pending,
        "relays": store.recent_relays(20),
        "scheduled": clock.scheduled(),
        "presence": "working" if pending else "handling" if active else "ready",
        "setup": {"router_key": bool(os.environ.get("OPENAI_API_KEY")),
                  "local_kb": any(b.get("folder") for b in bmap.values()),
                  "bridge": bool(os.environ.get("ETHAN_BRIDGE_DIR"))},
        "approvals_supported": True,
        "approvals": _pending_approvals(),
    }


def _tail(path, offset):
    """Return bytes appended since `offset` — how the page follows a live hand."""
    if not path or not os.path.exists(path):
        return {"offset": offset, "text": "", "eof": True}
    size = os.path.getsize(path)
    if offset > size:                            # file replaced/truncated
        offset = 0
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read(200_000)
    return {"offset": offset + len(chunk), "text": chunk.decode("utf-8", "replace"),
            "eof": False}


#: The largest POST body read. An ask or an ingest request is a few hundred bytes.
MAX_BODY = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):                   # keep Ethan's own log clean
        pass

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else body.encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True


    def _trusted_host(self):
        # Loopback binding alone does not prevent a hostile hostname resolving
        # to localhost. Check the authority before returning even the HTML.
        hosts = self.headers.get_all("Host", [])
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed.update(("127.0.0.1", "localhost"))
        if len(hosts) != 1 or hosts[0].lower() not in allowed:
            self.close_connection = True
            self._send(403, json.dumps({"error": "untrusted console host"}))
            return False
        return True

    def do_GET(self):
        if not self._trusted_host():
            return
        u = urlparse(self.path)
        q = parse_qs(u.query, keep_blank_values=True)
        for name in ("after", "id", "run", "offset"):
            if name in q and (len(q[name]) != 1 or not q[name][0].isascii()
                              or not q[name][0].isdigit() or len(q[name][0]) > 18):
                return self._send(400, json.dumps({"error": f"invalid {name}"}))
        try:
            if u.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if u.path in ("/assets/hud.css", "/assets/hud.js", "/assets/voice_queue.js", "/assets/layout.js"):
                name = u.path.rsplit("/", 1)[1]
                with open(os.path.join(WEB, name), "rb") as asset:
                    return self._send(200, asset.read(), "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8")
            if u.path == "/api/layout":
                from . import layouts
                return self._send(200, json.dumps({**layouts.current(), "registry": layouts.registry()}))
            if u.path == "/api/voice/status":
                from . import voice
                return self._send(200, json.dumps(voice.status()))
            if u.path == "/api/state":
                return self._send(200, json.dumps(_state()))
            if u.path == "/api/agents":
                return self._send(200, json.dumps(bridge_registry.sessions()))
            if u.path == "/api/conversation":
                return self._send(200, json.dumps(store.conversation(_chat_id(q.get("chat", [CHAT])[0]))))
            if u.path == "/api/replies":
                after = int(q.get("after", ["0"])[0])
                chat = _chat_id(q.get("chat", [CHAT])[0])
                return self._send(200, json.dumps(
                    {"chat": chat, "replies": store.replies_since(chat, after),
                     "pending": len(store.pending(chat))}))
            if u.path == "/api/task":
                t = store.task(int(q.get("id", ["0"])[0]))
                return self._send(200, json.dumps(t or {}))
            if u.path == "/api/log":
                runs = {r["id"]: r for r in store.recent_runs(200)}
                r = runs.get(int(q.get("run", ["0"])[0]))
                off = int(q.get("offset", ["0"])[0])
                if not r:
                    return self._send(404, json.dumps({"error": "no such run"}))
                out = _tail(r["log"], off)
                out["state"] = r["state"]
                return self._send(200, json.dumps(out))
            return self._send(404, json.dumps({"error": "not found"}))
        except Exception:
            return self._send(500, json.dumps({"error": "The local service could not complete this request."}))

    def _refuse_post(self):
        """Why this POST must not run, or None.

        The console has no sign-in, so it must not do what any web page asks. A
        cross-site `text/plain` POST is a "simple request" that browsers send without
        asking first — but it always carries an `Origin`, and it cannot claim to be
        JSON. So: a foreign `Origin` is refused, and so is any body that is not JSON.
        `bin/ethan` and curl send no `Origin`, and the page's own sends its own.
        """
        if self.headers.get_all("Transfer-Encoding"):
            return 400, "transfer encoding is not supported"
        if len(self.headers.get_all("Content-Length", [])) != 1:
            return 400, "send one Content-Length"
        if len(self.headers.get_all("Origin", [])) > 1:
            return 403, "send at most one Origin"
        origin = self.headers.get("Origin")
        port = self.server.server_address[1]
        if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return 403, f"origin {origin} may not use this console"
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return 415, "send Content-Type: application/json"
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return 400, "bad Content-Length"
        if n < 0 or n > MAX_BODY:
            return 413, f"body over {MAX_BODY} bytes"
        return None

    def do_POST(self):
        if not self._trusted_host():
            return
        upath = urlparse(self.path).path
        refused = self._refuse_post()
        if refused:
            self.close_connection = True         # the body was not read; do not reuse
            return self._send(refused[0], json.dumps({"error": refused[1]}))
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("expected an object")
            for key in ("text", "chat", "cwd", "door", "path", "doc_type", "chat_provider_ref"):
                if key in payload and payload[key] is not None and not isinstance(payload[key], str):
                    raise ValueError(f"{key} must be a string")
        except (ValueError, UnicodeError):
            return self._send(400, json.dumps({"error": "send a JSON object with string fields"}))
        if upath in ("/api/layout/preview", "/api/layout/apply", "/api/layout/rollback"):
            from . import layouts
            try:
                if upath.endswith("/preview"):
                    if set(payload) != {"layout"}:
                        raise ValueError("send only layout")
                    result = layouts.preview(payload["layout"], CHAT, CHAT)
                elif upath.endswith("/apply"):
                    if set(payload) != {"preview_id"} or not isinstance(payload["preview_id"], str):
                        raise ValueError("send only preview_id")
                    result = layouts.apply_preview(payload["preview_id"], CHAT, CHAT)
                else:
                    if set(payload) != {"expected_revision"}:
                        raise ValueError("send only expected_revision")
                    result = layouts.rollback(payload["expected_revision"])
                return self._send(200, json.dumps(result))
            except (ValueError, TypeError):
                return self._send(400, json.dumps({"error": "Invalid, expired, or stale layout change. Reload the current layout and create a fresh preview."}))
        if upath in {"/api/voice/" + action for action in ("start", "stop", "cancel", "mute", "unmute", "wake-enable", "wake-disable")}:
            from . import voice
            try:
                return self._send(200, json.dumps(voice.command(upath.rsplit("/", 1)[1])))
            except (OSError, RuntimeError, ValueError):
                return self._send(503, json.dumps({"error": "Local voice command failed. Check local speech support."}))
        if upath == "/api/ingest":
            pl = payload
            chat = _chat_id(pl.get("chat"))
            status, info = harvest.ingest_document(
                pl.get("path") or "", pl.get("doc_type") or "other",
                _door(pl.get("door")), chat, cwd=pl.get("cwd"))
            if status != "written":
                return self._send(400, json.dumps({"status": status, "error": info}))
            # report the async job's outcome through the caller's reply queue
            threading.Thread(target=harvest.wait_job, daemon=True,
                             args=(info["kb"], info["job_id"],
                                   lambda t, c=chat: store.add_reply(c, t))).start()
            return self._send(200, json.dumps({"status": status, **info}))
        if upath != "/api/ask":
            return self._send(404, json.dumps({"error": "not found"}))
        try:
            text = (payload.get("text") or "").strip()
            chat = _chat_id(payload.get("chat"))
            door = _door(payload.get("door"))
            cwd = payload.get("cwd") or None
            if cwd and not os.path.isdir(os.path.expanduser(cwd)):
                cwd = None                      # a bad path must not strand the hand
        except Exception:
            text, chat, cwd, door = "", CHAT, None, CHAT
        if not text:
            return self._send(400, json.dumps({"error": "empty ask"}))
        provider_ref = payload.get("chat_provider_ref")
        if provider_ref:
            import inspect
            from . import providers
            try:
                providers.resolve(provider_ref)
            except ValueError:
                return self._send(400, json.dumps({"error": "Selected session is unavailable or ambiguous. Choose a current registered session."}))
            if "chat_provider_ref" not in inspect.signature(router.handle).parameters:
                return self._send(503, json.dumps({"error": "Selected-session chat integration is not available in this running service yet."}))
        args = (text, chat, cwd, door, provider_ref) if provider_ref else (text, chat, cwd, door)
        threading.Thread(target=_ask, args=args, daemon=True).start()
        return self._send(200, json.dumps({"ok": True, "chat": chat, "cwd": cwd, "door": door}))


def open_server(port=None):
    """Bind the port now, so a port already in use fails here, loudly, and not
    inside a thread nobody is watching."""
    port = port if port is not None else int(os.environ.get("ETHAN_CONSOLE_PORT", "8787"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    log(f"console door open: http://127.0.0.1:{srv.server_address[1]}")
    return srv


def run(port=None):
    open_server(port).serve_forever()


WEB = os.path.join(os.path.dirname(__file__), "web")
with open(os.path.join(WEB, "index.html"), encoding="utf-8") as _page:
    PAGE = _page.read()
