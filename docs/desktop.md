# Local desktop and voice

The optional desktop launcher opens the same local Python HUD in an installed Edge
or Chrome app window. It does not start an AI agent, copy a sign-in token, install a
browser or change provider settings. Current app-mode discovery supports Windows.

From a checkout:

```sh
python -m ethan.desktop --check
python -m ethan.desktop
```

The installed command is `ethan-desktop`. Start `ethan-service` first, or explicitly
use `ethan-desktop --start-service`. The launcher reuses a reachable service instead
of starting another one. Its window and the backend have independent lifetimes;
closing the window does not stop the backend. `--url` accepts only an HTTP origin on
`127.0.0.1` or `localhost`, without a path, credentials or query parameters.

## Local speech

Windows local dictation uses the installed `System.Speech` recognizer through Windows
PowerShell. No cloud speech fallback is used. `--check` enumerates capabilities and
checks service reachability; it never opens the microphone or browser. A missing or
inaccessible recognizer is shown as unavailable, not as listening. The host capability
probe found an en-US recognizer; hardware capture has not yet been manually verified.

The microphone controls start muted. Unmute deliberately in the HUD first; start opens the default microphone,
stop finishes the local transcript, and cancel or mute discards the capture. Capture
is bounded to 30 seconds. Text stays in a preview and must be sent separately; speech
never submits a chat message or approves an action. No audio file is written by Ethan.

For optional global push-to-talk while this launcher remains running:

```sh
ethan-desktop --global-ptt
```

After unmuting in the HUD, hold Ctrl+Alt+Space to capture; release to finish a preview. The same local HUD voice
controls are used. If another application owns the shortcut, the launcher reports
that and leaves the microphone button available. Ctrl+C unregisters the shortcut
and cancels a capture still owned by the shortcut. This uses one registered hotkey,
not a keyboard recorder. The HUD shows the actual local speech state.

Optional wake listening uses the same installed local recognizer. After deliberately
unmuting, explicitly enable it to listen for "hey Ethan" for at most 60 seconds.
The microphone is on during that window; no audio file or cloud request is made.
A recognized wake phrase begins one dictation of at most 30 seconds, then turns off
and leaves a preview. It never sends text or approves an action. Re-enabling requires
another explicit action; it does not rearm after capture, timeout or service restart.
Cancel, mute or disable tears down the owned listener and discards its preview.
Stop while waiting for the wake phrase disables listening; stop during dictation
finishes the preview. An absent local recognizer remains unavailable.

The HUD exposes explicit enable/disable wake controls through
`voice.command("wake-enable")` and `voice.command("wake-disable")`.
Status reports `wake_enabled` and the `wake-listening` state. Microphone, wake phrase,
hotkey and browser behaviour still need manual verification on the target desktop;
passing fake-process tests and enumerating installed components do not establish
those live behaviours. No hardware capture was performed during implementation.
