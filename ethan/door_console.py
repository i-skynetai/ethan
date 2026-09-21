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

from . import kb, harvest, router, store
from .util import cfg, log

CHAT = "console"
STARTED = time.time()


_CHAT_OK = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _chat_id(raw):
    """Any caller may name its own conversation, so a CLI or another service gets
    its own reply queue instead of stealing the console's."""
    raw = (raw or "").strip() or CHAT
    return raw if _CHAT_OK.match(raw) else CHAT


def _ask(text, chat=CHAT, cwd=None):
    """Run one ask in the background; replies land in the pull queue."""
    store.remember(chat, "user", text)
    def reply(msg):
        store.add_reply(chat, msg)
    try:
        router.handle(chat, text, reply, door=CHAT, cwd=cwd)
    except Exception as e:                      # never let a bad ask kill the door
        store.add_reply(chat, f"error: {e}")
        log(f"console ask failed: {e}")


def _state():
    bmap = kb.kb_map()
    return {
        "up_since": STARTED,
        "uptime_sec": int(time.time() - STARTED),
        "kbs": [{"name": n, "purpose": b.get("purpose", ""), "privacy": b.get("privacy", "?"),
                    "write": bool(b.get("write")), "repo": b.get("repo", ""),
                    "tenant": b.get("tenant_code", "")} for n, b in bmap.items()],
        "hands": list(cfg("ethan.json")["hands"]),
        "tasks": store.recent_tasks(40),
        "runs": store.recent_runs(30),
        "pending": store.pending(),
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

    def do_POST(self):
        upath = urlparse(self.path).path
        if upath == "/api/ingest":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                pl = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, json.dumps({"error": "bad json"}))
            chat = _chat_id(pl.get("chat"))
            status, info = harvest.ingest_document(
                pl.get("path") or "", pl.get("doc_type") or "other",
                CHAT, chat, cwd=pl.get("cwd"))
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
            cwd = payload.get("cwd") or None
            if cwd and not os.path.isdir(os.path.expanduser(cwd)):
                cwd = None                      # a bad path must not strand the hand
        except Exception:
            text, chat, cwd = "", CHAT, None
        if not text:
            return self._send(400, json.dumps({"error": "empty ask"}))
        threading.Thread(target=_ask, args=(text, chat, cwd), daemon=True).start()
        return self._send(200, json.dumps({"ok": True, "chat": chat, "cwd": cwd}))


def run(port=None):
    port = port or int(os.environ.get("ETHAN_CONSOLE_PORT", "8787"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    log(f"console door open: http://127.0.0.1:{port}")
    srv.serve_forever()


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Skynet · Ethan</title>
<style>
:root{--bg:#0d1117;--pan:#161b22;--ln:#30363d;--fg:#e6edf3;--dim:#8b949e;
      --run:#d29922;--ok:#3fb950;--bad:#f85149;--acc:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
header{padding:10px 16px;border-bottom:1px solid var(--ln);display:flex;gap:14px;align-items:center}
h1{font-size:14px;margin:0;letter-spacing:.5px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--ok);display:inline-block}
.wrap{display:grid;grid-template-columns:minmax(320px,1fr) minmax(0,1.4fr);gap:14px;padding:14px}
.card{background:var(--pan);border:1px solid var(--ln);border-radius:6px;overflow:hidden}
.card h2{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);
         margin:0;padding:8px 12px;border-bottom:1px solid var(--ln)}
.body{padding:10px 12px;max-height:44vh;overflow:auto}
.row{padding:6px 8px;border-radius:4px;cursor:pointer;display:flex;gap:8px;align-items:baseline}
.row:hover{background:#1f2630}
.row.sel{background:#1f2937;outline:1px solid var(--acc)}
.tag{font-size:10px;padding:1px 6px;border-radius:9px;border:1px solid var(--ln);color:var(--dim);white-space:nowrap}
.running{color:var(--run)} .done{color:var(--ok)} .failed,.timeout{color:var(--bad)}
.ask{flex:1;min-width:0} .mut{color:var(--dim)}
pre{margin:0;padding:10px 12px;white-space:pre-wrap;word-break:break-word;
    max-height:52vh;overflow:auto;font-size:12px}
form{display:flex;gap:8px;padding:10px 14px;border-top:1px solid var(--ln)}
input{flex:1;background:#0d1117;border:1px solid var(--ln);color:var(--fg);
      padding:8px 10px;border-radius:5px;font:inherit}
button{background:var(--acc);border:0;color:#0d1117;padding:8px 16px;border-radius:5px;
       font:inherit;font-weight:600;cursor:pointer}
.feed div{padding:5px 0;border-bottom:1px solid #21262d;white-space:pre-wrap;word-break:break-word}
.blank{color:var(--dim);padding:6px 8px}
</style></head><body>
<header><span class="dot"></span><h1>SKYNET · ETHAN</h1>
  <span class="mut" id="up"></span><span class="mut" id="counts"></span></header>

<div class="wrap">
  <div>
    <div class="card"><h2>Sessions — click to follow</h2><div class="body" id="runs"></div></div>
    <div class="card" style="margin-top:14px"><h2>Tasks</h2><div class="body" id="tasks"></div></div>
    <div class="card" style="margin-top:14px"><h2>KBs &amp; hands</h2><div class="body" id="kbs"></div></div>
  </div>
  <div>
    <div class="card"><h2 id="logh">Output</h2><pre id="log">Pick a session on the left to follow it live.</pre></div>
    <div class="card" style="margin-top:14px"><h2>Ethan</h2>
      <div class="body feed" id="feed"></div>
      <form id="f"><input id="q" placeholder="Ask Ethan…  (same kb as Telegram)" autocomplete="off"><button>Send</button></form>
    </div>
  </div>
</div>

<script>
let sel=null, off=0, afterReply=0, selKind='run';
const $=i=>document.getElementById(i);
const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const ago=t=>{const s=Math.max(0,Date.now()/1000-t);
  return s<60?Math.floor(s)+'s':s<3600?Math.floor(s/60)+'m':Math.floor(s/3600)+'h';};

async function state(){
  const s=await (await fetch('/api/state')).json();
  $('up').textContent='up '+Math.floor(s.uptime_sec/60)+'m';
  $('counts').textContent=s.pending.length?('· '+s.pending.length+' running'):'· idle';

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
    const d=document.createElement('div'); d.textContent=m.text; $('feed').prepend(d);
  }
}

$('f').onsubmit=async e=>{
  e.preventDefault();
  const t=$('q').value.trim(); if(!t) return;
  $('q').value='';
  const d=document.createElement('div'); d.innerHTML='<span class="mut">you ›</span> '+esc(t);
  $('feed').prepend(d);
  await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
                          body:JSON.stringify({text:t})});
};

state(); replies();
setInterval(state,2000); setInterval(tick,1500); setInterval(replies,1500);
</script></body></html>
"""
