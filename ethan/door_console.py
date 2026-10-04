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


def _ask(text, chat=CHAT, cwd=None, door=CHAT):
    """Run one ask in the background; replies land in the pull queue.

    The ask is stored by router.handle, not here: storing it twice used to put it
    in front of the model twice."""
    global _ACTIVE
    with _ACTIVITY_LOCK:
        _ACTIVE += 1
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
        router.handle(chat, text, reply, door=door, cwd=cwd)
    except Exception as e:                      # never let a bad ask kill the door
        store.add_reply(chat, f"error: {e}")
        log(f"console ask failed: {e}")
    finally:
        with _ACTIVITY_LOCK:
            _ACTIVE -= 1


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
                  "local_kb": any(b.get("folder") for b in bmap.values())},
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
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
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
        except Exception as e:
            return self._send(500, json.dumps({"error": str(e)}))

    def _refuse_post(self):
        """Why this POST must not run, or None.

        The console has no sign-in, so it must not do what any web page asks. A
        cross-site `text/plain` POST is a "simple request" that browsers send without
        asking first — but it always carries an `Origin`, and it cannot claim to be
        JSON. So: a foreign `Origin` is refused, and so is any body that is not JSON.
        `bin/ethan` and curl send no `Origin`, and the page's own sends its own.
        """
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
        upath = urlparse(self.path).path
        refused = self._refuse_post()
        if refused:
            self.close_connection = True         # the body was not read; do not reuse
            return self._send(refused[0], json.dumps({"error": refused[1]}))
        if upath == "/api/ingest":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                pl = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, json.dumps({"error": "bad json"}))
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
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
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
        threading.Thread(target=_ask, args=(text, chat, cwd, door), daemon=True).start()
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


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Skynet · Ethan</title>
<style>
:root{color-scheme:light;--bg:#f7f6f2;--surface:#ffffff;--line:#30334216;--fg:#30313f;--dim:#737483;--mint:#427c69;--lav:#d8d0ef;--bad:#ae4857;--ok:#427c69;--acc:#9685ba;--ln:var(--line)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;overflow-x:hidden}[hidden]{display:none!important}button,input,textarea{font:inherit}button{cursor:pointer}button:disabled{opacity:.45;cursor:wait}button:focus-visible,textarea:focus-visible,summary:focus-visible{outline:2px solid var(--mint);outline-offset:5px}button{color:inherit}header{position:absolute;inset:0 0 auto;z-index:2;padding:26px 32px;display:flex;align-items:center;gap:10px}header h1{margin:0;font-size:16px;font-weight:500;letter-spacing:-.5px}.dot{width:5px;height:5px;background:var(--mint);border-radius:50%;box-shadow:0 0 12px #b5f3da66}#presence{margin-left:auto;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:var(--dim)}#up,#counts{display:none}
.presence-scene{min-height:100svh;position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:90px 24px 95px;background:radial-gradient(ellipse at 35% 35%,#d5caec55,transparent 45%),radial-gradient(ellipse at 65% 52%,#cce2d655,transparent 40%),var(--bg)}.scene-label{font-size:9px;letter-spacing:3.2px;color:#767184;margin:0 0 32px}.character{width:240px;height:240px;position:relative;background:transparent;border:0;padding:0;border-radius:50%;isolation:isolate;transition:transform .35s}.character:hover{transform:translateY(-4px)}.halo{position:absolute;inset:6px;border:1px solid #a396bd45;border-radius:50%;box-shadow:0 0 70px #ab99cd22,inset 0 0 45px #ab99cd0c}.orbit{position:absolute;inset:22px;border:1px solid #a396bd29;border-radius:50%;transform:rotate(-35deg) scaleX(1.17);pointer-events:none}.orbit:after{content:'';position:absolute;top:13px;left:42px;width:5px;height:5px;background:var(--mint);border-radius:50%;box-shadow:0 0 16px #89bba666}.mask{position:absolute;inset:46px 48px;background:radial-gradient(ellipse at 35% 20%,#ffffffbb,transparent 65%),linear-gradient(150deg,#fdfdfb,#e4e1ec 55%,#dadce4);border:1px solid #b5accc66;border-radius:45% 45% 47% 47%;box-shadow:inset 2px 3px 8px #fff9,inset -5px -9px 18px #77708418,0 24px 50px #77708420;display:flex;align-items:center;justify-content:center}.visor{width:78%;height:37px;background:linear-gradient(180deg,#cdd4d7,#bbc8cb);border:1px solid #9caeb755;border-radius:22px;display:flex;align-items:center;justify-content:space-evenly;box-shadow:inset 0 4px 10px #77708420}.visor i{width:26px;height:3px;border-radius:5px;background:#355b60;box-shadow:0 0 13px #70a6a733}.mouth{position:absolute;bottom:27px;width:18px;height:2px;border-radius:2px;background:#9392a2}.character.busy .halo{animation:breathe 2s ease-in-out infinite}.character.busy .visor i{background:#6f5c94;box-shadow:0 0 15px #b8a6fb66}@keyframes breathe{50%{box-shadow:0 0 75px #baa7fc55;transform:scale(1.04)}}.scene-title{font-size:clamp(25px,3vw,36px);font-weight:350;letter-spacing:-1.2px;line-height:1.2;margin:30px 0 10px}.scene-caption{font-size:13px;color:var(--dim);margin:0 0 28px;max-width:330px;text-align:center}.summon-label{background:#ffffff88;border:1px solid #b4a9ca55;border-radius:28px;font-size:12px;font-weight:400;padding:12px 20px;transition:border-color .2s,background .2s}.summon-label:hover{background:#ded5ef77;border-color:#b4a9ca99}.summon-label span{padding-left:25px;color:var(--mint)}.scene-actions{position:absolute;bottom:28px;display:flex;gap:12px;padding:6px;border:1px solid #a6a1b333;background:#ffffff88;border-radius:24px}.scene-actions button{padding:8px 16px;border:0;background:transparent;color:#777084;font-size:11px;border-radius:20px}.scene-actions button:hover{background:#ded5ef44;color:var(--fg)}#unread{color:var(--mint)}
.update-card{position:fixed;bottom:90px;left:50%;transform:translateX(-50%);width:min(440px,calc(100vw - 40px));z-index:3;background:#fffffff0;backdrop-filter:blur(24px);border:1px solid #c1b2d755;border-radius:18px;padding:17px 22px;color:#44404f;font-size:12px;font-weight:400;box-shadow:0 15px 60px #7770841a;text-align:left;line-height:1.7}.workspace{position:fixed;inset:0;background:#eae6ee70;backdrop-filter:blur(18px);z-index:5}.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;overflow:hidden}.conversation{position:absolute;left:50%;top:8vh;bottom:8vh;transform:translateX(-50%);width:min(660px,calc(100vw - 32px));display:flex;flex-direction:column;background:linear-gradient(145deg,#fffffffa,#f5f2f9fa);border-color:#b9aec944;border-radius:26px;box-shadow:0 35px 100px #77708420}.intro{padding:32px 30px 14px}.eyebrow{font-size:9px;letter-spacing:2px;color:var(--mint)}.intro h2{font-size:24px;font-weight:400;letter-spacing:-.7px;margin:10px 0 8px}.intro p{font-size:12px;color:var(--dim);margin:0}.notice{font-size:10px;color:#787182;line-height:1.6;margin:0 30px 12px;padding-left:12px;border-left:1px solid #aea0c266}.feed{flex:1;min-height:0;overflow:auto;padding:0 30px;scrollbar-width:thin;scrollbar-color:#b6afc5 transparent}.feed>div{white-space:pre-wrap;word-break:break-word;font-size:13px;line-height:1.75;padding:16px 0;border-bottom:1px solid #ded5ef44}.feed .user{margin:12px 0 12px 40px;padding:13px 17px;background:#ece5f780;border:1px solid #c3b6db33;border-radius:15px}.speaker{display:block;font-size:9px;letter-spacing:1.4px;text-transform:uppercase;color:var(--mint);margin-bottom:5px}.user .speaker{color:#bfb6f6}form{display:flex;align-items:flex-end;gap:9px;margin:12px 20px 0;padding:10px;border:1px solid #b4a9ca55;border-radius:18px;background:#ffffffaa}textarea{width:100%;min-width:0;flex:1;resize:none;border:0;background:transparent;color:var(--fg);font-size:13px;padding:7px;outline:none!important}textarea::placeholder{color:#85818f}form button{border:0;background:var(--lav);color:#4d3f69;font-size:11px;padding:11px 15px;border-radius:12px;white-space:nowrap}.footnote{font-size:9px;color:#837b90;margin:10px 30px 16px}.close-panel{position:absolute;top:14px;right:16px;z-index:1;background:#ffffff88;border:1px solid #a6a1b333;border-radius:50%;width:30px;height:30px;color:#787182;font-size:21px;font-weight:300;line-height:1;padding:0}#context-panel{position:absolute;right:20px;top:24px;bottom:24px;width:min(420px,calc(100vw - 40px));padding:48px 18px 18px;background:#faf8fff5;border:1px solid #b9aec944;border-radius:24px;overflow:auto;scrollbar-width:thin}#context-panel .card{margin-bottom:14px;background:#ffffff88}.card h2,summary{font-size:12px;font-weight:500;letter-spacing:0;padding:14px;margin:0;border-bottom:1px solid var(--line);color:#625872}summary{cursor:pointer}.section-note{font-size:11px;color:var(--dim);padding:0 14px;line-height:1.7}.agent{padding:12px 14px;border-bottom:1px solid var(--line);word-break:break-word;font-size:12px}.agent small{display:block;color:var(--dim);font-size:10px;margin-top:4px}.body{padding:8px;max-height:35vh;overflow:auto}.row{display:flex;gap:8px;align-items:baseline;padding:9px;border-radius:8px;cursor:pointer;font-size:11px}.row:hover,.row.sel{background:#e9e2f777}.ask{flex:1;min-width:0}.mut,.blank{color:var(--dim)}.tag{font-size:9px;padding:1px 5px;border:1px solid var(--line);border-radius:7px;white-space:nowrap}.failed,.timeout{color:var(--bad)}.done{color:var(--mint)}.running{color:var(--lav)}pre{padding:14px;margin:0;white-space:pre-wrap;word-break:break-word;max-height:35vh;overflow:auto;font-size:10px;color:#756a87}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
@media(max-height:700px){.presence-scene{padding-top:70px;padding-bottom:90px}.scene-label{margin-bottom:18px}.character{width:185px;height:185px}.mask{inset:35px 38px}.scene-title{margin-top:22px}.scene-caption{margin-bottom:23px}.conversation{top:4vh;bottom:4vh}.intro{padding-top:24px}.intro p,.footnote{display:none}}
@media(max-width:450px){header{padding:23px 25px}.intro{padding-left:22px;padding-right:38px}.notice{margin-left:22px;margin-right:22px}.feed{padding:0 22px}form{margin:10px 12px 12px}form button{font-size:0;width:36px;height:36px;padding:0}form button:after{content:'↑';font-size:18px}.scene-label{letter-spacing:2.5px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}
</style></head><body>
<header><span class="dot" id="presence-orb" aria-hidden="true"></span><h1>Ethan</h1><span id="presence" role="status">Ready</span>
  <span class="mut" id="up"></span><span class="mut" id="counts"></span></header>

<section class="presence-scene" aria-label="Ethan presence">
  <div class="scene-label">YOUR PERSONAL COMPANION</div>
  <button class="character" id="summon" aria-label="Speak with Ethan" aria-haspopup="dialog"><span class="halo"></span><span class="mask"><span class="visor"><i></i><i></i></span><span class="mouth"></span></span><span class="orbit"></span></button>
  <h2 class="scene-title">Here, with you.</h2>
  <p class="scene-caption" id="scene-caption">I’m here when you need me.</p>
  <button class="summon-label" id="begin">Bring me in <span>↗</span></button>
  <nav class="scene-actions" aria-label="Ethan tools"><button id="updates-button">Updates <span id="unread"></span></button><button id="context-button">Agents &amp; context</button></nav>
  <button id="update-card" class="update-card" hidden aria-live="polite"></button>
</section>
<main class="workspace" hidden>
  <section class="conversation card" id="conversation-panel" role="dialog" aria-label="Conversation with Ethan" hidden><button class="close-panel" id="close-chat" aria-label="Close conversation">×</button>
    <div class="intro"><span class="eyebrow">YOUR PERSONAL ASSISTANT</span><h2>I’m here. What’s on your mind?</h2><p>I help you bring context and coding agents together. Tell me the outcome you need.</p></div>
    <div class="notice" id="setup">Checking local setup…</div>
    <div class="feed" id="feed" aria-live="polite"></div>
    <form id="f"><label for="q" class="sr-only">Message Ethan</label><textarea id="q" rows="3" placeholder="Tell Ethan what you need…" required></textarea><button>Send message</button></form>
    <p class="footnote">Requests use the configured router and Harness. Sending a message does not contact a registered bridge session.</p>
  </section>
  <aside id="context-panel" role="dialog" aria-label="Agents and context" hidden><button class="close-panel" id="close-context" aria-label="Close agents and context">×</button>
    <div class="card"><h2>Connected agents</h2><p class="section-note" id="agent-note">Reading the local registry…</p><div class="body" id="agents"></div></div>
    <div class="card"><h2>Current work</h2><div class="body" id="tasks"></div></div>
    <details class="card"><summary>Context and memory</summary><div class="body" id="kbs"></div></details>
    <details class="card"><summary>Past runs and technical details</summary><div class="body" id="runs"></div><h2 id="logh">Run output</h2><pre id="log">Select a past run or task to inspect its output.</pre></details>
  </aside>
</main>

<script>
let sel=null, off=0, afterReply=0, selKind='run', unread=0;
function openPanel(which){document.querySelector('.workspace').hidden=false;$('conversation-panel').hidden=which!=='conversation';$('context-panel').hidden=which!=='context';if(which==='conversation'){unread=0;$('unread').textContent='';$('update-card').hidden=true;$('q').focus();}}
function closePanels(){document.querySelector('.workspace').hidden=true;$('conversation-panel').hidden=true;$('context-panel').hidden=true;$('summon').focus();}
const $=i=>document.getElementById(i);
const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function bubble(text,role){const d=document.createElement('div');d.className=role;const label=document.createElement('span');label.className='speaker';label.textContent=role==='user'?'You':'Ethan';d.append(label,document.createTextNode(text));$('feed').append(d);$('feed').scrollTop=$('feed').scrollHeight;}
const ago=t=>{const s=Math.max(0,Date.now()/1000-t);
  return s<60?Math.floor(s)+'s':s<3600?Math.floor(s/60)+'m':Math.floor(s/3600)+'h';};

async function state(){
  const s=await (await fetch('/api/state')).json();
  $('up').textContent='up '+Math.floor(s.uptime_sec/60)+'m';
  const labels={ready:'Ready',handling:'Handling your request',working:'Working'};
  $('presence').textContent=labels[s.presence]||'Ready';
  $('presence-orb').classList.toggle('active',s.presence!=='ready');
  $('summon').classList.toggle('busy',s.presence!=='ready');
  $('scene-caption').textContent=s.presence==='working'?'Work is in progress. Open updates for the details.':s.presence==='handling'?'I’m handling your request.':'I’m here when you need me.';
  $('counts').textContent=s.pending.length?('· '+s.pending.length+' active tasks'):'';
  const needs=[];
  if(!s.setup.router_key) needs.push('General conversation needs a router model key.');
  if(s.setup.local_kb) needs.push('Local-folder knowledge bases cannot yet launch real tasks through Harness.');
  needs.push('Registered bridge sessions are visible; messaging is not connected.');
  $('setup').textContent=needs.join(' ');

  $('runs').innerHTML = s.runs.length ? s.runs.map(r=>
    `<div class="row ${sel===r.id&&selKind==='run'?'sel':''}" onclick="pick(${r.id},'run')">
       <span class="tag ${r.state}">${r.state}</span>
       <span class="ask"><b>${esc(r.hand)}</b> <span class="mut">${esc((r.repo||'').split('/').pop())}</span></span>
       <span class="mut">${ago(r.ts)}</span></div>`).join('')
    : '<div class="blank">No hand has run yet.</div>';

  $('tasks').innerHTML = s.tasks.length ? s.tasks.map(t=>
    `<div class="row ${sel===t.id&&selKind==='task'?'sel':''}" onclick="pick(${t.id},'task')">
       <span class="tag ${t.state}">${t.state}</span>
       <span class="ask">#${t.id} <span class="mut">${esc(t.kind)}·${esc(t.hand)}</span> ${esc((t.ask||'').slice(0,70))}</span>
       <span class="mut">${ago(t.ts)}</span></div>`).join('')
    : '<div class="blank">No tasks yet.</div>';

  $('kbs').innerHTML = s.kbs.map(b=>
    `<div class="row"><span class="tag">${b.privacy}</span>
      <span class="ask"><b>${esc(b.name)}</b> <span class="mut">${esc(b.purpose.slice(0,60))}</span></span>
      <span class="tag">${b.write?'rw':'ro'}</span></div>`).join('')
    + `<div class="row"><span class="ask mut">hands: ${s.hands.join(', ')}</span></div>`;
}

function pick(id,kind){ sel=id; selKind=kind; off=0; $('log').textContent=''; tick(); state(); }

async function tick(){
  if(sel===null) return;
  if(selKind==='task'){
    const t=await (await fetch('/api/task?id='+sel)).json();
    $('logh').textContent='Task #'+sel+' · '+(t.state||'?');
    $('log').textContent=(t.ask?'ASK:\n'+t.ask+'\n\n':'')+(t.result||'(no output yet)');
    return;
  }
  const r=await (await fetch('/api/log?run='+sel+'&offset='+off)).json();
  if(r.error) return;
  off=r.offset;
  $('logh').textContent='Session run #'+sel+' · '+r.state;
  if(r.text){ $('log').textContent+=r.text; $('log').scrollTop=$('log').scrollHeight; }
}

async function replies(){
  const r=await (await fetch('/api/replies?after='+afterReply)).json();
  for(const m of r.replies){
    afterReply=m.id;
    bubble(m.text,'assistant');
    if($('conversation-panel').hidden){unread++;$('unread').textContent='· '+unread;$('update-card').textContent='Ethan · '+m.text.slice(0,160);$('update-card').hidden=false;}
  }
}

$('f').onsubmit=async e=>{
  e.preventDefault();
  const t=$('q').value.trim(); if(!t) return;
  $('q').value='';
  bubble(t,'user');
  const button=$('f').querySelector('button');button.disabled=true;
  try{const res=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});if(!res.ok)throw new Error('Request refused ('+res.status+')');}catch(e){bubble(e.message,'assistant');}finally{button.disabled=false;}
};

async function agents(){try{const a=await(await fetch('/api/agents')).json();$('agent-note').textContent=a.note;$('agents').replaceChildren();for(const agent of ['claude','codex']){const title=document.createElement('h2');title.textContent=agent==='claude'?'Claude':'Codex';$('agents').append(title);const rows=a.sessions.filter(s=>s.agent===agent);if(!rows.length){const empty=document.createElement('p');empty.className='section-note';empty.textContent='No registered sessions';$('agents').append(empty);}for(const s of rows){const d=document.createElement('div');d.className='agent';const name=document.createElement('strong');name.textContent=s.name;const project=document.createElement('small');project.textContent=s.project;const status=document.createElement('small');status.textContent='Last recorded: '+s.status+' · '+(s.last_seen?ago(s.last_seen)+' ago':'not checked');d.append(name,project,status);$('agents').append(d);}}}catch(e){$('agent-note').textContent='Agent registry unavailable.';}}
async function startConversation(){const history=await(await fetch('/api/conversation')).json();afterReply=history.after;for(const m of history.messages)bubble(m.text,m.role);replies();setInterval(replies,1500);}
$('summon').onclick=$('begin').onclick=()=>openPanel('conversation');
$('updates-button').onclick=$('update-card').onclick=()=>openPanel('conversation');
$('context-button').onclick=()=>openPanel('context');
$('close-chat').onclick=$('close-context').onclick=closePanels;
document.addEventListener('keydown',e=>{if(e.key==='Escape')closePanels();});
state(); startConversation(); agents(); setInterval(agents,15000);
setInterval(state,2000); setInterval(tick,1500);
</script></body></html>
"""
