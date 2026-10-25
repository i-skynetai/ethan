# EH-075 — Ethan control center design and extension contract

**Owner:** coordinating Codex session. **Date:** 2026-10-25.
**Status:** implemented HUD and persisted dynamic layout editor; final security integration verification ongoing.
This is a functional personal assistant, not a product landing page. It describes
the actual first implementation separately from extension boundaries and remaining QA.

## Reference and evidence

The original three Library images could not be materialized on Windows: the official
helper requires `os.setxattr`. No original-image visual verification is claimed here.
The maintainer approved the parent-inspected reference brief and the public visual
reference at <https://jarvis-agent.tech>. The latter was inspected directly in silent
mode: dark navy background, cyan-white luminous core, rings/ticks, thin framing,
technical labels and restrained amber accents. No branding, assets, sales copy,
revenue figures or fictional agent activity were copied.

The base HUD has been rendered in the local browser at desktop and 390×844 sizes.
The captured preview uses an isolated QA ledger/config, so its empty registry does
not contradict the separately verified real existing-session bridge roundtrip.

## Product hierarchy

1. **Persistent status bar:** Ethan identity, service connection, settings. A connected
   Python service does not imply that any provider is authenticated or available.
2. **Workspace heading:** welcoming title, short orientation, local clock. No simulated
   telemetry, health percentages, revenue or completion metrics.
3. **Core and priority cards:** agent network at left, core in the center, tasks and
   reminders at right on a wide desktop. Pending approvals are visibly amber.
4. **Conversation:** shared `console` conversation, explicit command composer,
   accepted/error feedback, shortcut requests and bounded history.
5. **Activity/results:** actual run and relay states, timestamps and recorded output.
6. **Control panel:** connection capabilities, project continuity, local voice,
   display/motion, typed layout editor, privacy/permission limitations.

The main viewport prioritizes the core and actionable cards. Longer conversation,
registry lists and results scroll inside their panels. The document may scroll for
secondary information; no panel hides important content merely to fit a screenshot.

## Visual tokens

| Token | Value | Use |
|---|---|---|
| Background | `#050b12` | Nearly black navy canvas |
| Surface | `#0a1420` | Card/dialog base; subtle navy gradient |
| Border | `#183443` | Fine one-pixel structure |
| Primary cyan | `#6ce9ff` | State labels, focus, active ring, principal action |
| Main text | `#d8edf3` | Headings and readable content |
| Secondary | `#819ba8` | Timestamps, provenance, explanatory labels |
| Amber | `#efbd75` | Pending approval and attention; not every action |
| Failure | `#ff9093` | Error states when needed |
| Mono | Consolas / SFMono-Regular / monospace | Technical labels and timestamps |
| Body | Segoe UI / system-ui / sans-serif | Conversation and decisions |

Wide viewport outer padding is 32px, reduced to 20px and then 14px. Grid gap is
18px, 14px on phones. Cards use 6px radii and 1px borders; dialogs use 8px radii.
Panel headers are 54px high. Body content is 12–14px; technical labels are 8–10px
and supplementary only. Primary headings are 22–27px. Content text is never replaced
by tiny decorative telemetry. Focus rings are 2px cyan with a 4px offset.

## Core construction and state machine

The core is original CSS artwork: radial navy/blue sphere, cyan-white nucleus,
three illuminated filaments, two tilted orbital ellipses, concentric rings, ticks
and crosshair marks. It is decorative (`aria-hidden`) beside an explicit text state.
No microphone amplitude or model activity is fabricated. Idle orbital motion is
ambient decoration and does not imply work.

| State | Authoritative trigger | Visual/text behavior | Exit |
|---|---|---|---|
| Connecting | First successful state fetch not received | Dim core, connecting label | First response or connection failure |
| Offline | State request fails or times out | Dim core, stale-data banner, reconnect text | Successful state fetch |
| Ready | Service idle, no active ask/task/approval/voice | Slow ambient rings, ready text | Observed work or deliberate voice action |
| Handling | Backend handling count, or local speech finalization | Pulsing nucleus, handling text | Backend/voice state update |
| Working | Backend pending task list | Pulsing nucleus, progress text | Completed/failed/interrupted task state |
| Waiting for approval | Current scoped pending approvals | Amber ring accents, explicit review instruction | Approval disappears/changes |
| Listening | Local helper explicitly reports listening | Cyan/green glow, release-to-preview text | Stop/cancel/error/30s limit |
| Speaking | Local browser speech start event | Faster pulse, speaking label | End/error/cancel event |

Precedence is explicit: offline service is never described as connected; speech
feedback may reflect local playback independently. During online use, actual voice
capture/playback takes precedence over task animation, then pending approval, then
backend work, then idle. Text always names the source state. Unknown states must not
be presented as successful completion. Motion preference and OS reduced-motion both
disable animations without removing text information.

## Widget registry and data contracts

First dynamic version has six approved widget types, at most one instance each.
Adding means configuring a known renderer, not creating executable code.

| Type / stable ID | Data binding | Actions | Constraints |
|---|---|---|---|
| `core` | Backend presence + local voice/speech events | Deliberate PTT, mute, cancel | Mandatory, fixed title/size; before conversation |
| `conversation` | Shared conversation/reply endpoints | Draft/send; shortcuts | Mandatory, bounded display; explicit submission |
| `agents` | Read-only bridge registry | Draft a handoff in composer | Registered ≠ live; no automatic dispatch |
| `tasks` | Canonical task ledger + scheduled list | View recorded task result | No client-generated running states |
| `approvals` | Scoped safe summary list | Draft exact approval or deny | Never exposes payload/brief/credential fields |
| `activity` | Run and relay ledger | View log/result | Queued/acknowledged/completed remain distinct |

Every binding is fixed in reviewed code. Users/models cannot supply endpoint URLs,
SQL, expressions, scripts, event handlers, templates, HTML or alternate permission
scopes in a layout. Widget data retains original record IDs, timestamps and source
type. The layout cannot grant access to another project, door or conversation.

### Version 1 layout schema

```json
{
  "version": 1,
  "widgets": [
    {"id":"agents","type":"agents","width":1,"title":"Agent network"},
    {"id":"core","type":"core","width":2,"title":"Ethan / Core"},
    {"id":"tasks","type":"tasks","width":1,"title":"Tasks & reminders"},
    {"id":"conversation","type":"conversation","width":2,"title":"Conversation"},
    {"id":"approvals","type":"approvals","width":1,"title":"Your approval"},
    {"id":"activity","type":"activity","width":2,"title":"Activity & results"}
  ]
}
```

The implementation registry's defaults are authoritative for mandatory widths/titles.
Validation rejects unknown fields/types, duplicates, non-integer or boolean widths,
widths outside 1/2, overlong titles, markup/URLs and missing mandatory widgets.
Titles are plain text and capped at 64 characters. No arbitrary coordinates in v1.
Order is array order and width is a bounded column span. On narrow screens width
collapses to one column; core/conversation remain usable and precede secondary work.

### Mutation lifecycle

1. An editor change or supported natural-language rule produces a candidate config.
2. Server validates it and stores a 10-minute preview bound to chat, door, current
   revision and exact config. Current layout is unchanged.
3. UI shows the change list and candidate, then requires **Apply preview**. A chat
   request uses explicit `apply dashboard <preview-id>` instead.
4. Apply atomically checks TTL, scope, revision and single consumption, then appends a
   new current revision. Concurrent/stale edits fail visibly and require a new preview.
5. Reset previews the registry default. Rollback restores a previously validated
   revision as a new revision; it does not erase history.
6. Unknown/corrupt saved schema falls back to validated defaults with an explicit
   recovery notice; unknown code is never executed. Future migrations must be explicit,
   tested version-to-version transforms and retain the prior revision for rollback.

Supported first rules include `hide tasks`, `show activity`, `move agents before
tasks`, and `reset dashboard`. They only create previews. General model-generated
layout interpretation is not required for these rules and is not claimed. Future
interpretation must output this same bounded schema and pass the same validator.

## Interaction details

**Conversation:** Enter submits, Shift+Enter inserts a line, IME composition does not
submit. Send is disabled while that request is in flight. On network failure the draft
is preserved and no automatic retry occurs. Accepted means only accepted by the
coordinator. Replies arrive from the existing ledger. Reload restores the canonical
conversation instead of starting another session. Shortcut buttons issue harmless
status/help requests; a handoff button only drafts the target and leaves submission
to the person. Result dialogs render text, never agent-provided HTML.

**Approvals:** show ID, kind, safe summary and expiry, scoped to `console` chat/door.
Review & approve puts `approve N` in the composer for an explicit Send; Deny sends
`deny N`. Neither a bare yes nor a returned agent instruction grants permission.
Backend checks exact payload/target, current policy, expiry, scope, one-time consumption
and restart handling. The layout itself cannot alter approval policy. Local process
authentication is an acknowledged remaining boundary, not solved by Host validation.

**Voice:** muted by default in the service. Unmute enables deliberate capture controls;
it does not start recording. Hold pointer or focused-page Ctrl+Space; release finalizes.
Cancel, pointer cancellation, focus loss or page hiding cancel a held capture. Control
requests are serialized so a quick release cannot overtake start. Local recognition is
bounded to 30 seconds. Transcript enters the composer only and needs explicit Send.
Voice cannot auto-approve, auto-send, or auto-enable a capability. Optional global
Ctrl+Alt+Space is a registered shortcut, not a keyboard recorder. Browser speech output
uses only voices marked local; no local voice yields clear text-only fallback. Optional wake is implemented as one explicitly enabled local window: unmute, enable for up to 60 seconds, say hey Ethan, then one dictation of up to 30 seconds. It never rearms or sends automatically. Mute/cancel/disable discard and terminate capture. No microphone hardware verification has been performed.

**Project continuity:** compact goal, decision, constraint, next step, ownership/status
and result source-pointer records share the canonical SQLite ledger. Project path,
privacy class, record kind/name, short summary, source pointer and owner are explicit.
They grant no permission. Source documents and graph retrieval belong to agent tools,
not this HUD. A selected project is passed as the normal work directory through the
existing router. No form silently changes credentials, external connectors or policy.

## Responsive and accessible behavior

| Width | Layout behavior |
|---|---|
| Above 1050px | Four grid units: network 1 / core 2 / tasks 1; conversation spans two units |
| 651–1050px | Two grid units; wide core/conversation span both; compact cards share a row |
| 650px and below | One column; core and conversation first; secondary cards below |

The dynamic renderer preserves validated order/width within each breakpoint, with
mandatory core/conversation precedence. At 390×844 the full page was inspected and
DOM scroll width did not exceed viewport width. Settings and result dialogs use
native dialog focus management, Escape dismissal, visible close buttons and bounded
scrolling. Inputs have labels, buttons have accessible names, conversation is a log,
connection/state text accompanies color, and all editor operations have keyboard
buttons rather than drag-only controls. Semantic headings preserve hierarchy.

## Loading, empty, failure and interruption states

| Situation | Required UI behavior |
|---|---|
| First load | Connecting text; no invented active agents/counters |
| Empty registry | Explicit no registered sessions or configuration note |
| Registered stale session | Last reported state/time; not a live green badge |
| Empty tasks/reminders/results | Guidance plus zero actual records |
| Queued relay | Queued label; no completed checkmark until reply is recorded |
| Backend disconnect | Visible banner, dim core, last sync retained as stale |
| Command rejection | Error feedback, retained draft, no automatic resend |
| Voice unsupported | Disabled capture, precise local-support explanation |
| Voice error/cancel | Microphone state shown; no auto-send or retry |
| No pending approvals | Calm empty state, not a fabricated approval |
| Restarted approval | Backend invalidates it; request fresh approval, no execution |
| Interrupted task | Canonical interrupted state preserved; no implicit relaunch |
| Stale layout revision | Reject apply, reload current state and preview anew |
| Invalid layout persisted | Safe default plus recovery notice, no evaluation |

## Security and extension review gate

HTTP assets are an exact allowlist. Host/Origin/framing/body checks precede effects.
CSP limits script/style/connect sources to self, prevents framing and disables base
URL changes. All dynamic labels/results use text nodes. No eval, Function constructor,
remote script, generated executable widget or arbitrary URL data binding is supported.

New widget **code** is a development task, not a configuration operation. It requires
a declared type and schema, fixed least-privilege binding, provenance/error states,
accessibility/responsive design, tests and independent review. New connector access,
credential grants or external capabilities require explicit human authorization.
Only after review may that code become an approved registry entry. Existing widget
configuration can then be previewed/applied without code generation. This is the
secure path for “add a project summary card”; self-modifying runtime code is deferred.

## Verification and remaining gates

Verified base: rendered desktop/mobile HUD; real status request and reload continuity;
saved display settings; no browser console errors; static asset/CSP/voice endpoint HTTP
tests; delayed voice start/stop/cancel ordering; actual existing Claude relay roundtrip
in an isolated ledger; desktop launcher reaches installed Edge and opens the HUD.

Verified dynamic editor: preview, apply, reload and rollback through real HTTP and rendered UI; invalid bindings, stale/replayed previews and foreign origins refused. Compact context survives a service restart and is recovered through the same console conversation.

Remaining: credential ingress/output withholding review and full integrated
suite after its changes; physical microphone/PTT/speaker and global-hotkey testing;
wake recognition hardware verification; distributable wheel (host lacks setuptools); local API
authentication; new official provider app-server UI adapter beyond existing session
bridge. Do not describe those as complete. The screenshot is a working local preview,
not final acceptance of every subsystem. Update evidence when these gates change.
