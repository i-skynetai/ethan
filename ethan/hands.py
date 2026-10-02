"""Hands run through core. Ethan chooses; core enforces; the hand works.

Ethan used to start `claude`, `codex` or `kimi` itself — `Popen` with no `env=`,
so a hand inherited every variable Ethan holds: the Telegram token, the OpenAI
key, every knowledge base's PAT. And it got no policy, no tool allowlist and no
git block. Both findings came from one review (2026-09-14).

Now Ethan builds **one command, `sky build`**, and gives it an explicit,
allowlisted environment carrying **exactly one secret**: the PAT of the
knowledge base this task resolves to. Core then does what core does — builds
the hand's own environment, applies the policy, proves the git block, starts the
hand under its watchdogs, records the run and the bill. Ethan keeps a hard cap
on `sky build` itself as a safety net, and streams its output to a per-run log
so the console can still watch.

Ethan *proposes* the knowledge base (`--kb`) and the hand (`--hand`). Core may
refuse either — a KB across a privacy boundary, a hand that cannot hold the role
— and the refusal comes back as a result, not a crash, because `sky build --json`
prints one JSON line last whatever happened. That line is the contract between
the two programs; nothing here parses core's prose.

The contract with the router is unchanged: `run(hand, brief, repo, review=False,
task_id=None)` returns `{"ok", "out", "run_id"}`. Two optional arguments are
new — `kb` and `kind` — and three keys are added to the result: `sky_run_id`,
`sky_dir` and `usage`.
"""
import itertools, json, os, shutil, subprocess, threading, time
from .util import cfg, log, ROOT
from . import store
from .kb import kb_map_path          # imported by name: `kb` is a parameter here

RUNS_DIR = os.path.join(ROOT, "state", "runs")

#: What `sky build` may inherit from Ethan. Listed, not filtered: a filter has
#: to be updated every time a new secret appears in Ethan's environment, and
#: nobody remembers to.
ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "SHELL")

#: Ethan's task kinds, to the four roles core knows. Anything unrecognised is a
#: reviewer — read-only — because the safe default is the one that cannot edit.
ROLE_FOR_KIND = {
    "build": "developer", "implement": "developer", "fix": "developer", "code": "developer",
    "review": "reviewer",
    "design": "architect", "architecture": "architect", "analyse": "architect",
    "analyze": "architect", "spec": "architect",
    "security": "security", "secure": "security",
}

_RUN_SEQ = itertools.count(1)


def _log_path(hand):
    os.makedirs(RUNS_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(RUNS_DIR, f"{stamp}-{hand}-{os.getpid()}-{next(_RUN_SEQ):04d}.log")


def role_for(kind=None, review=False):
    """The role core is asked for. `review=True` wins, for the old call shape."""
    if review:
        return "reviewer"
    return ROLE_FOR_KIND.get((kind or "").lower(), "reviewer")


def sky_bin(conf):
    """Where `sky` is: configured, then `$SKY_BIN`, then on PATH. None if nowhere."""
    configured = (conf.get("sky") or {}).get("bin") or os.environ.get("SKY_BIN")
    if configured:
        path = os.path.expanduser(configured)
        return path if os.path.isfile(path) and os.access(path, os.X_OK) else None
    return shutil.which("sky")


def build_command(conf, *, role, hand, brief, kb=None):
    """The one command Ethan runs. Core's global options go before `build`."""
    sky = conf.get("sky") or {}
    cmd = [sky_bin(conf) or "sky", "--kb-map", kb_map_path()]
    if sky.get("policy"):
        cmd += ["--policy", os.path.expanduser(sky["policy"])]
    if kb:
        cmd += ["--kb", kb]
    cmd += ["build", "--role", role, "--hand", hand, "--json", "--task", brief]
    return cmd


def build_env(conf, kb_entry=None):
    """What `sky build` gets, and nothing else.

    The allowlist, plus exactly one secret — the PAT variable the chosen
    knowledge base names in the map — plus core's own configuration. Every other
    token Ethan holds stays behind. Core then builds the *hand's* environment
    from its own allowlist, so the hand is two explicit lists away from Ethan's
    secrets rather than zero.
    """
    env = {k: os.environ[k] for k in ENV_ALLOWLIST if k in os.environ}
    sky = conf.get("sky") or {}
    env["SKY_STATE_DIR"] = os.path.expanduser(sky.get("state_dir")
                                              or os.path.join(ROOT, "state", "sky"))
    if sky.get("policy"):
        env["SKY_POLICY"] = os.path.expanduser(sky["policy"])
    elif os.environ.get("SKY_POLICY"):
        env["SKY_POLICY"] = os.environ["SKY_POLICY"]
    if sky.get("agent_id"):
        env["SKY_AGENT_ID"] = sky["agent_id"]
    if kb_entry:
        pat_env = kb_entry.get("pat_env")
        if pat_env and os.environ.get(pat_env):
            env[pat_env] = os.environ[pat_env]
    return env


def parse_result(text):
    """Core's one JSON line, scanned from the end. None if it never came."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("sky") == "build":
            return obj
    return None


def _stop(p):
    """Ask, then insist. Core has children of its own, so kill the group."""
    for step in ("terminate", "kill"):
        if p.poll() is not None:
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(p.pid), 15 if step == "terminate" else 9)
            else:
                getattr(p, step)()
        except Exception:
            try:
                getattr(p, step)()
            except Exception:
                pass
        try:
            p.wait(timeout=5)
            return
        except Exception:
            continue


def run(hand, brief_text, repo=None, review=False, task_id=None, kb=None, kind=None):
    conf = cfg("ethan.json")
    role = role_for(kind, review)

    kb_entry = None
    if kb:
        from .kb import kb_map
        kb_entry = kb_map().get(kb)
        if kb_entry is None:
            return {"ok": False, "out": f"unknown kb '{kb}' — not in config/kb-map.json"}

    if sky_bin(conf) is None:
        return {"ok": False, "out": ("sky is not installed. Put core's `bin/sky` on PATH, or set "
                                     "sky.bin in config/ethan.json, or export SKY_BIN.")}

    wd = os.path.expanduser(repo) if repo else None
    if wd and not os.path.isdir(wd):
        return {"ok": False, "out": f"repo dir not found: {wd}"}

    cmd = build_command(conf, role=role, hand=hand, brief=brief_text, kb=kb)
    env = build_env(conf, kb_entry)
    # Core enforces the hand's caps itself. This is only a net under core: a bit
    # longer than its hard cap, so it fires only if core itself has hung.
    cap = int(conf.get("hand_timeout_sec", 1800)) + 120

    path = _log_path(hand)
    run_id = store.start_run(task_id, hand, wd, path)
    log(f"hand:{hand} as {role} via sky build in {wd or '(no repo)'} (run #{run_id})")

    tail = []
    try:
        lf = open(path, "w", buffering=1)
    except Exception as e:
        store.end_run(run_id, "failed")
        return {"ok": False, "out": f"cannot open run log: {e}", "run_id": run_id}

    try:
        lf.write(f"# hand={hand} role={role} kb={kb or '-'} repo={wd or '-'} task={task_id}\n")
        lf.write(f"# command: {' '.join(cmd[:-1])} <brief>\n")
        lf.write(f"# environment: {len(env)} variables — "
                 f"{', '.join(k for k in env if k != 'PATH')}\n")
        p = subprocess.Popen(
            cmd, cwd=wd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True, bufsize=1,
            start_new_session=True)
    except FileNotFoundError:
        lf.close(); store.end_run(run_id, "failed")
        return {"ok": False, "out": "sky could not be started", "run_id": run_id}
    except Exception as e:
        lf.close(); store.end_run(run_id, "failed")
        return {"ok": False, "out": f"sky error: {e}", "run_id": run_id}

    def pump():
        try:
            for line in p.stdout:
                lf.write(line)
                tail.append(line)
                if len(tail) > 4000:
                    del tail[:2000]
        except Exception:
            pass

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()

    started, verdict = time.time(), None
    while True:
        try:
            p.wait(timeout=2)
            break
        except subprocess.TimeoutExpired:
            pass
        if time.time() - started > cap:
            verdict = f"sky build ran past {cap}s — core itself appears hung"
            log(f"hand:{hand} run #{run_id} — {verdict}")
            _stop(p)
            break

    reader.join(timeout=5)
    text = "".join(tail)
    summary = parse_result(text) or {}
    sky_run_id, sky_dir = summary.get("run_id"), summary.get("directory")
    if sky_run_id:
        lf.write(f"# sky run {sky_run_id} → {sky_dir}\n")
    lf.close()

    out = (summary.get("result_text") or summary.get("reason") or text.strip())[-16000:]
    base = {"run_id": run_id, "sky_run_id": sky_run_id, "sky_dir": sky_dir,
            "outcome": summary.get("outcome"), "usage": summary.get("usage")}
    if verdict:
        store.end_run(run_id, "timeout")
        return {**base, "ok": False, "out": (out + "\n\n" if out else "") + verdict}
    ok = bool(summary.get("ok")) if summary else p.returncode == 0
    store.end_run(run_id, "done" if ok else "failed")
    return {**base, "ok": ok, "out": out}
