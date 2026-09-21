"""Shared helpers: .env loading, logging, HTTP."""
import json, os, sys, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%SZ')}] {msg}", flush=True)


def load_env():
    """Load KEY=VALUE lines from .env without overriding real env vars."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
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
    with open(os.path.join(ROOT, "config", name)) as f:
        return json.load(f)


def http_json(url, method="GET", body=None, headers=None, timeout=90):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))
