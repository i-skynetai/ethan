"""Shared helpers: .env loading, logging, HTTP."""
import json, os, shutil, sys, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "defaults")


def _checkout():
    """True when Ethan runs from its own checkout, which carries `config/`. An
    installed copy (`pip install .`) sits in site-packages and does not."""
    return os.path.isdir(os.path.join(ROOT, "config"))


def _user_dir(kind):
    """The person's own folder for config or data, by the platform's convention."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA" if kind == "config" else "LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ethan")
    env = "XDG_CONFIG_HOME" if kind == "config" else "XDG_DATA_HOME"
    fallback = "~/.config" if kind == "config" else "~/.local/share"
    return os.path.join(os.environ.get(env) or os.path.expanduser(fallback), "ethan")


def config_dir():
    """Where `policy.json`, `ethan.json` and the KB map live. `ETHAN_CONFIG_DIR` wins;
    a checkout uses its own `config/`; an installed copy uses the user's config folder,
    seeded once from the shipped defaults. A file the person already has is never
    overwritten."""
    where = os.environ.get("ETHAN_CONFIG_DIR") or (os.path.join(ROOT, "config") if _checkout()
                                                   else _user_dir("config"))
    if not os.path.isdir(where) or not os.path.isfile(os.path.join(where, "ethan.json")):
        os.makedirs(where, exist_ok=True)
        for name in os.listdir(DEFAULTS):
            if not os.path.exists(os.path.join(where, name)):
                shutil.copyfile(os.path.join(DEFAULTS, name), os.path.join(where, name))
    return where


def state_dir():
    """Where the ledger and run logs live. `ETHAN_STATE_DIR` moves it — the demo
    points it at a temporary folder so it never touches a real ledger. A checkout
    uses `state/`; an installed copy uses the user's data folder."""
    return (os.environ.get("ETHAN_STATE_DIR")
            or (os.path.join(ROOT, "state") if _checkout() else os.path.join(_user_dir("data"), "state")))


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
    path = os.path.join(ROOT, ".env") if _checkout() else os.path.join(config_dir(), ".env")
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
    with open(os.path.join(config_dir(), name), encoding="utf-8") as f:
        return json.load(f)


def http_json(url, method="GET", body=None, headers=None, timeout=90):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))
