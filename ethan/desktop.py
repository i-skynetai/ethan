"""Thin local desktop launcher; reuses the Python HUD in an installed browser."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def local_url(value):
    u = urlsplit(value)
    try:
        port = u.port if u.port is not None else 80
    except ValueError as e:
        raise ValueError("invalid console port") from e
    if (u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost")
            or u.username or u.password or u.query or u.fragment or u.path not in ("", "/")
            or not 1 <= port <= 65535):
        raise ValueError("desktop requires a local HTTP console origin")
    return f"http://{u.hostname}:{port}/"


def browser_path():
    if sys.platform != "win32":
        return None
    for root, suffix in (("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
                         ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
                         ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
                         ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe")):
        base = os.environ.get(root)
        path = Path(base) / suffix if base else None
        if path and path.is_file():
            return str(path)
    return None


def reachable(url):
    # Local HTTP only; ignore proxy environment variables and never follow redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(url + "api/state", timeout=1) as r:
            return r.status == 200 and isinstance(json.loads(r.read(1048576)), dict)
    except (OSError, ValueError, urllib.error.URLError):
        return False


def voice_command(url, action):
    """Use the HUD's same-origin voice controls; never submit a transcript as an ask."""
    url = local_url(url)
    if action not in ("start", "stop", "cancel", "mute", "unmute"):
        raise ValueError("unknown voice action")
    request = urllib.request.Request(url + "api/voice/" + action, b"{}",
                                     {"Content-Type": "application/json"}, method="POST")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=3) as r:
        return json.loads(r.read(65536))


def global_ptt(url):
    """Opt-in Windows Ctrl+Alt+Space: hold to capture, release to preview only.

    Uses one registered hotkey, not a keyboard recorder. Ctrl+C exits and cancels.
    """
    if sys.platform != "win32":
        raise RuntimeError("Global PTT requires Windows; use the HUD microphone button")
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, 1, 0x0001 | 0x0002 | 0x4000, 0x20):
        raise RuntimeError("Ctrl+Alt+Space is already reserved; use the HUD microphone button")
    msg = wintypes.MSG()
    active = False
    print("Global PTT enabled: hold Ctrl+Alt+Space, release to preview; Ctrl+C exits. No automatic send.")
    try:
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0312 and not active:  # WM_HOTKEY
                    state = voice_command(url, "start")
                    active = state.get("state") in ("starting", "listening")
            if active and not (user32.GetAsyncKeyState(0x20) & 0x8000):
                voice_command(url, "stop")
                active = False
            time.sleep(0.03)
    finally:
        user32.UnregisterHotKey(None, 1)
        if active:
            voice_command(url, "cancel")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open the existing local Ethan HUD as a desktop window")
    parser.add_argument("--url", default="http://127.0.0.1:" + os.environ.get("ETHAN_CONSOLE_PORT", "8787"))
    parser.add_argument("--start-service", action="store_true", help="explicitly start the Python backend if unavailable")
    parser.add_argument("--check", action="store_true", help="report local capabilities without opening a window or microphone")
    parser.add_argument("--global-ptt", action="store_true", help="opt-in Windows Ctrl+Alt+Space hold-to-talk; preview only")
    a = parser.parse_args(argv)
    try:
        url = local_url(a.url)
    except ValueError as e:
        parser.error(str(e))
    browser = browser_path()
    if a.check:
        from . import voice
        print(json.dumps({"browser_available": bool(browser), "service_reachable": reachable(url),
                          "voice": voice.status(),
                          "wake_word": "explicit local opt-in; hey Ethan; 60-second window; hardware unverified"}))
        return 0
    if not browser:
        print("No supported installed Edge/Chrome desktop browser found; no browser was installed.", file=sys.stderr)
        return 1
    if not reachable(url):
        if not a.start_service:
            print("Ethan is not reachable. Start ethan-service, or use --start-service explicitly.", file=sys.stderr)
            return 1
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        service = subprocess.Popen([sys.executable, "-m", "ethan.main"],
                                   env={**os.environ, "ETHAN_CONSOLE_PORT": str(urlsplit(url).port)}, **flags)
        for _ in range(40):
            if reachable(url):
                break
            if service.poll() is not None:
                print("Python service stopped before the console was reachable.", file=sys.stderr)
                return 1
            time.sleep(0.25)
        else:
            service.terminate()
            service.wait(timeout=5)
            print("Python service did not become reachable; stopped the launcher-owned process.", file=sys.stderr)
            return 1
    subprocess.Popen([browser, "--app=" + url, "--no-first-run"], close_fds=True)
    print("Opened local Ethan HUD. The backend remains independent of the browser window.")
    if a.global_ptt:
        try:
            global_ptt(url)
        except KeyboardInterrupt:
            pass
        except (RuntimeError, OSError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
