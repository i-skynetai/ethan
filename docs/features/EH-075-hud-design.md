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

See the updated evidence boundaries and future roadmap below for current limitations.

## Immersive visual revision — 25 October 2026

Implemented presentation: continuous navy canvas; 330px core/rings at wide desktop,
compact technical heading and edge panels; conversation/control dock below the core.
No synthetic telemetry. Existing state, approvals, voice preview, settings and layout
validation remain authoritative. Default composition receives the immersive arrangement;
custom order/width/hide configurations retain the generic responsive renderer. Mobile
stacks core then conversation before supporting panels. Reduced-motion rules remain.
The new reference JPEGs could not be materialized locally because the supported Windows
Library helper fails at os.setxattr. This revision follows parent-inspected references
and the approved brief, not a claimed local pixel comparison.

## Future interaction roadmap — planned, not implemented

The following are design commitments for review, not active controls or capability claims.
Ethan coordinates; agents reason using separately supplied tools. No new context engine,
graph, harness, connector installation or permission grant is part of this roadmap work.

| Phase | Screen / capability | Acceptance and release gate |
| --- | --- | --- |
| F1 | Streaming conversation | Ordered persisted event IDs, incremental visible answer text when provider actually supplies it, reconnect cursor and deduplication; queued/waiting state otherwise. Interrupted drafts remain visibly incomplete. No simulated typing as evidence of provider streaming. |
| F1 | Conversation navigation | Expand dock into readable transcript; search/filter by task and scope, jump to original source event, pin results and copy safe text. Preserve draft and scroll position; unread count instead of forced autoscroll when reading older content. |
| F2 | Task / evidence inspector | Select agent/task to see requested goal, public plan, executor, observed tools/actions, approvals, timestamps, outcomes, failures and verification evidence. Distinguish planned action from executed action and reported claim from verified result. |
| F2 | Context inspector | Exact selected project/privacy/provider scope, included coordination records and source pointers, excluded legacy/unscoped context explanation, freshness/conflicts and bounded handoff preview. Edit via explicit draft/review; never recover historical permissions as authorization. |
| F3 | On-demand statistics / charts | Agent proposes registered chart instances with typed data references, provenance, units, time range and freshness. User previews before pinning. Unknown data renders unavailable, never zero or fabricated values. No new connector access through a widget. |
| F3 | Debug workspace | Correlated request/task/relay/event timeline, redacted errors, timeout/retry history, policy evaluation explanation and verification failures. Copy sanitized diagnostic bundle preview; no raw environment variables, credentials or unrestricted logs. |
| F4 | Saved workspaces / comparison | Versioned named layouts scoped to project/privacy; preview/diff/rollback; side-by-side result evidence; keyboard navigation, mobile drill-in, screen reader table equivalents and performance budgets verified. |

### Streaming contract and interaction details

Future events: conversation_id, task_id, message_id, event_id, sequence, timestamp,
source, scope, kind and bounded payload. Kinds include accepted, queued, started,
answer_delta, tool_requested, tool_result, approval_requested, completed, interrupted
and error. Persist sequence/cursor, deduplicate replay, reconcile terminal states from
canonical ledger. Transport cancellation is not execution cancellation: show stop-requested
until executor acknowledges. Retry is a new explicit action linked to the original,
never resend automatically after uncertain delivery. Approval remains exact-action bound.
Reconnect tests must cover partial text, duplicate/out-of-order events, stale token epoch,
service restart, missing provider streaming, and no duplicate execution.

Dock: live answer region with polite batched accessibility announcements; Pause following,
Jump to latest, Expand transcript and task-linked result navigation. Escape closes an
expanded view without cancelling tasks; separate labelled stop action when supported.
Do not animate or announce every token. Voice transcripts stay editable previews and
never auto-send; spoken output remains opt-in and stops on owner command.

### Agent-requested data visualization contract

Extend the existing registry only through reviewed code: approved initial future types
could be metric, table, line, bar, timeline and evidence-list. Agent proposals are data,
not executable code. A v2 proposal would declare widget_type, schema_version, instance_id,
title, data_ref, source_refs, scope, units, range, generated_at, stale_after and refresh
policy. Validate fixed fields/types/limits, known binding ID and read permission before
rendering; never accept SQL, URLs, JS, HTML or arbitrary query expressions as bindings.
Each data_ref resolves through an existing authorized bounded server adapter; apply privacy
filters before aggregation. Restrict rows/series/points, time range and refresh frequency.
No cross-project aggregation by default. Include empty/error/partial/stale/conflict states.
Chart/table views must expose original sources and accessible values; generated labels
are untrusted text. New executable widget or connector needs isolated implementation,
tests/review and explicit approval for expanded capabilities.

Examples: "Show this project's task completion trend" proposes a dated ledger-backed
chart; "Compare these two results" proposes evidence rows with result references;
"Show cost" reports unavailable unless an authorized provider supplies actual usage.
Temporary views expire or are dismissed without changing the saved layout. Pinning uses
validated preview/apply with revision checks. Schema migration retains prior valid version;
unknown future types render a safe unsupported placeholder, not dynamic code loading.

### Transparency, correction and confidence

Show observable plan/status, tool actions, cited evidence, assumptions, concise decision
summaries and verification failures. Do not expose or promise private chain of thought,
invent a thinking transcript, or infer correctness from animation. Status labels are
observations: queued, working, awaiting approval, blocked, interrupted, verified or failed.
"Verified" names the check and scope; agent self-report is labelled separately.
Owner can flag an incorrect assumption, attach correction/source, request recheck and
approve/reject the exact next action. Corrections append attributable revisions; they
do not erase prior audit evidence or silently dispatch a retry. No invented confidence
percentages. Unknown/unverified evidence remains explicit.

### Additional recommended phases and constraints

After F1–F2, prioritize notification triage (quiet hours, acknowledged alerts), safe
interruption/resume, searchable decision/result history and exportable sanitized evidence.
Then consider resource budgets only from measured sources, workspace presets and read-only
comparison panels. Defer ambient always-on voice, remote hosting and autonomous connector
installation. Every phase requires scope isolation, provenance, stale/offline/restart
tests, keyboard-only operation, 200% zoom, reduced motion and small-screen QA. Streaming
and debug views must use existing coordination events, not a parallel scheduler or database.

### Updated evidence boundaries

Before this visual revision: 333 tests passed (2 skipped), lint and docs passed for the
integrated auth preparation snapshot. Scoped continuity and existing-session nonce reply
were verified separately; neither proves live token streaming. Packaging was verified in
an isolated environment before auth preparation. Optional authentication is prepared,
disabled in this preview and not activated. Physical microphone/speaker/hotkey/wake QA
remains unperformed. The preview has isolated state and no configured agent registry.


### Light theme and translucent surface revision

Implemented: explicit top-bar Light theme / Dark theme toggle, saved only in the existing
versioned browser display preference. Missing/unknown theme falls back dark; reset returns
dark. Light theme uses a pale blue canvas, dark navy labels and teal/amber actions; the
core remains luminous. Translucent panels use bounded blur with an opaque-enough gradient
fallback. There are no new data bindings or microphone actions. Settings, dialogs,
forms, errors and approval surfaces are themed too. Theme changes never change scope,
policy, layout revision, provider, microphone state or access token.

Final visual revision verification (2026-10-25): full aggregate suite ran 333 tests in
24.159 seconds, OK with 2 skipped. Both themes inspected, mobile overflow absent,
theme reload persistence and reduced motion verified. No new hardware audio or
live-agent integration was exercised.

Streaming work moved into the scoped [EH-080 implementation](EH-080-progressive-responses.md) on 26 October 2026. Request lifecycle infrastructure is tested; existing-session hooks and real progressive answer text remain incomplete. Other F1-F4 features stay planned.
