"""Optional Windows local dictation. Text is preview only: never dispatch an ask.

No microphone is opened by import, status or capability discovery. Capture starts
only after explicit capture or wake opt-in; no cloud recognizer is used.
"""
import atexit
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

_LOCK = threading.RLock()
_CAPS = None
_PROCESS = None
_STATE = {"state": "idle", "muted": True, "wake_enabled": False, "transcript": "", "detail": "Microphone muted; unmute deliberately before capture"}
_HELPER = Path(__file__).with_name("windows_speech.ps1")


def _shutdown():
    # Do not run a capability probe during exit, or touch any other process.
    with _LOCK:
        if _PROCESS is not None:
            try:
                _PROCESS.terminate()
                _PROCESS.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                _PROCESS.kill()


atexit.register(_shutdown)


def _powershell():
    if sys.platform != "win32":
        return None
    path = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return str(path) if path.is_file() else None


def _args(mode):
    exe = _powershell()
    if not exe:
        raise RuntimeError("Windows local speech requires installed Windows PowerShell")
    # Owned code as a single argv item, not a shell or execution-policy override.
    script = _HELPER.read_text(encoding="utf-8")
    return [exe, "-NoProfile", "-NonInteractive", "-Command", "& {\n" + script + "\n} -Mode " + mode]


def _flags():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def capabilities():
    global _CAPS
    with _LOCK:
        if _CAPS is not None:
            return dict(_CAPS)
        if not _powershell():
            _CAPS = {"supported": False, "detail": "Windows local speech is unavailable on this platform"}
        else:
            try:
                p = subprocess.run(_args("capabilities"), capture_output=True, text=True,
                                   encoding="utf-8-sig", timeout=10, **_flags())
                data = json.loads(p.stdout.strip())
                if p.returncode or not isinstance(data, dict):
                    raise ValueError("local speech capability probe failed")
                _CAPS = {"supported": bool(data.get("supported")),
                         "detail": str(data.get("detail", "Local speech probe returned no details"))}
            except (OSError, ValueError, subprocess.TimeoutExpired) as e:
                _CAPS = {"supported": False, "detail": f"Local speech probe failed ({type(e).__name__})"}
        return dict(_CAPS)


def status():
    caps = capabilities()
    with _LOCK:
        return {**_STATE, "supported": caps["supported"],
                **({"state": "unavailable", "detail": caps["detail"]} if not caps["supported"] else {})}


def _read(process):
    global _PROCESS
    try:
        for line in process.stdout:
            try:
                event = json.loads(line.lstrip("\ufeff"))
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            with _LOCK:
                if _PROCESS is not process:
                    return
                if event.get("state") in ("wake-listening", "listening", "transcribing", "idle", "error"):
                    _STATE["state"] = event["state"]
                if isinstance(event.get("transcript"), str):
                    _STATE["transcript"] = event["transcript"][:8000]
                if isinstance(event.get("detail"), str):
                    _STATE["detail"] = event["detail"][:300]
        code = process.wait(timeout=3)
        with _LOCK:
            if _PROCESS is process:
                _PROCESS = None
                _STATE["wake_enabled"] = False
                if _STATE["state"] != "error":
                    _STATE.update(state="error" if code else "idle",
                                  detail="Local speech process failed" if code else "Microphone off; preview only")
    except (OSError, subprocess.TimeoutExpired):
        with _LOCK:
            if _PROCESS is process:
                process.kill()
                process.wait()
                _PROCESS = None
                _STATE["wake_enabled"] = False
                _STATE.update(state="error", detail="Local speech process stopped unexpectedly")
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stdin:
            process.stdin.close()


def command(action):
    """Thread-safe local control. Stop finalises; cancel/mute discard capture."""
    global _PROCESS
    if action not in ("start", "stop", "cancel", "mute", "unmute", "wake-enable", "wake-disable"):
        raise ValueError("unknown voice action")
    caps = capabilities()
    with _LOCK:
        if action == "stop" and _STATE.get("wake_enabled") and _STATE["state"] in ("starting", "wake-listening"):
            action = "wake-disable"
        if action in ("cancel", "mute", "wake-disable"):
            old, _PROCESS = _PROCESS, None
            if old is not None:
                old.terminate()
                try:
                    old.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    old.kill()
                    old.wait()
            _STATE.update(state="idle", wake_enabled=False, transcript="", detail="Microphone off")
            if action == "mute":
                _STATE["muted"] = True
        elif action == "unmute":
            _STATE["muted"] = False
        elif action in ("start", "wake-enable"):
            if not caps["supported"]:
                return status()
            if _STATE["muted"]:
                _STATE["detail"] = "Unmute before starting the microphone"
            elif _PROCESS is None:
                try:
                    waking = action == "wake-enable"
                    _PROCESS = subprocess.Popen(_args("wake" if waking else "capture"), stdin=subprocess.PIPE,
                                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                text=True, encoding="utf-8-sig", **_flags())
                    _STATE.update(state="starting", wake_enabled=waking, transcript="",
                                  detail="Starting local wake listening (60 seconds maximum)" if waking else "Starting local microphone")
                    threading.Thread(target=_read, args=(_PROCESS,), daemon=True).start()
                except (OSError, RuntimeError) as e:
                    _PROCESS = None
                    _STATE["wake_enabled"] = False
                    _STATE.update(state="error", detail=f"Cannot start local speech ({type(e).__name__})")
        elif action == "stop" and _PROCESS is not None:
            try:
                _PROCESS.stdin.write("stop\n")
                _PROCESS.stdin.flush()
                _STATE.update(state="transcribing", detail="Finishing local transcript")
            except (OSError, ValueError):
                _STATE.update(state="error", detail="Local speech process is not accepting input")
        return status()
