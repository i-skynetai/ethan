"""Shared helpers: .env loading, logging, HTTP."""
import json, os, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def state_dir():
    """Where the ledger and run logs live. `ETHAN_STATE_DIR` moves it — the demo
    points it at a temporary folder so it never touches a real ledger."""
    return os.environ.get("ETHAN_STATE_DIR") or os.path.join(ROOT, "state")


#: When a list, log lines are collected here instead of printed. The demo uses it
#: to show the route and the launch in its own words.
sink = None


def log(msg):
    if sink is not None:
        sink.append(msg)
        return
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%SZ')}] {msg}", flush=True)


def load_env():
    """Load KEY=VALUE lines from .env without overriding real env vars."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        lines = list(fh)
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.split("#")[0].strip()
        if v and k not in os.environ:
            os.environ[k] = v


def cfg(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as f:
        return json.load(f)


def http_json(url, method="GET", body=None, headers=None, timeout=90):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))
