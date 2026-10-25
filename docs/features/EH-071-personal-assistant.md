# EH-071 — Personal assistant continuation

**Status:** In review — implemented slices and remaining gates recorded below · **Owner:** Codex (ethan), 2026-10-25 · **Issue:** not opened

## What is missing today

The current README reports a fake-hand demonstration, not a verified live provider
roundtrip. An entry in the bridge registry proves registration, not that a session can
answer. The repository has policy and relay controls, but a durable approval lifecycle
still needs an audit and agreement with the backend owner (EH-040/EH-067).

The starting checkout was clean at `7de6b05` on `main`. No service listener was found
on the configured default console port during the initial inspection. Installed CLI
help was inspected without reading credentials: Claude Code 2.1.302 offers print,
structured/streaming output, resume and permission modes; Codex CLI
0.163.0-alpha.11 offers exec, resume, queue and an experimental app-server with stdio
and local socket transports. These observations do not establish authentication,
account access, model access or a successful live exchange.

Original Library images could not be materialised after a bounded retry: the official
helper uses `os.setxattr`, unavailable on this Windows runtime. No final Library files
exist. The reference gate is now satisfied by an authorised public substitute inspected
by the coordinator: cyan/white energy core, orbit ticks, dark navy HUD and mono labels.
Do not claim original Library pixel review. HUD implementation is authorised from that
substitute brief.

## What done looks like

- Each visible core/provider state is derived from an observed event and timestamp:
  unavailable, registered, checking, reachable, queued, working, waiting for approval,
  completed or failed. Stale data never appears as live availability.
- A harmless authorised ask reaches an existing chosen provider session, returns to
  the originating conversation and records its real outcome; interruption, restart,
  provider refusal and timeout have deterministic close-outs without duplicate sends.
- An action requiring approval cannot execute before a matching approval, or after
  rejection, expiry, cancellation, policy change or payload change. Restart does not
  broaden permission. Scheduling and every alternative entry path meet the same gate.
- Tasks, approvals, activity, chat and settings use one shared visual system after
  references can be reviewed. Widgets remain keyboard accessible and their validated
  layout survives restart; corrupt or obsolete layouts recover safely.
- Desktop and voice paths obey exactly the same backend policy and approval rules.
  Microphone use is visible, cancellable and off by default; wake-word use is optional.

## Design

Final scope, 2026-10-25: build Ethan only. Ethan coordinates compact goals,
constraints, decisions, next steps, ownership, status and result source pointers in
its existing SQLite ledger. Claude/Codex own reasoning and separately supplied scoped
knowledge tools. No new context/retrieval/graph engine, document ingestion, or new
Harness integration/dependency setup is part of this implementation. Existing
`sky build` compatibility remains; absence is reported as unavailable, never bypassed.
Wake-word support is optional and deferred; no hardware capture occurs without a
deliberate user test. Voice and desktop use the same console chat and router.

Keep the Python service authoritative for tasks, policy, approvals and activity.
Do not substitute a second backend or copy provider credential stores. Reuse official
installed provider tooling and existing sign-in only; capability support must be
verified against installed versions. No login/logout, credential changes, account
provisioning, purchases, deployments or publishing are part of this work.

### Ownership and sequence

| Phase | Roadmap | Owner / date | Work and completion gate |
|---|---|---|---|
| 0: boundaries and agreement | EH-071/072 | Plan: Codex (ethan); console: Codex (coordinator), 2026-10-25 | Coordinator touches only `ethan/door_console.py` and `tests/test_console_boundary.py`: reject non-loopback Host and invalid body/offset shapes. Codex (ethan) independently reviews. Obtain an actual Claude response and agree backend files before concurrent implementation. |
| 1: approval audit and contract | EH-073, EH-040/067 | Claude (ethan), 2026-10-25 | Audit complete; backend-only ownership accepted, with console/CLI default `ask` reiterated after a counter-proposal. Implement exact payload binding, source conversation/door, expiry, atomic single consumption and current-policy recheck. Add failing regression cases before fixes; no UI edits. |
| 2: progressive integration proof | EH-074 | Unassigned, 2026-10-25 | First read-only capability discovery; harmless coordination roundtrips through existing sessions are authorised now. Verify one ask, its answer and ledger entry; exercise failure/restart; repeat with the other provider. Preserve existing-session rules and `sky build` launch boundary. No new session launch is implied by discovery. Additional paid services and account/credential changes need separate consent. |
| 3: shared HUD and saved layouts | EH-075 | Codex (coordinator), 2026-10-25 | Authorised substitute reference inspected. Share navy/cyan tokens across task/approval/activity/chat/settings surfaces. Drive core animation from real state. Validate saved preferences; widget layout persistence remains a later gate. |
| 4: desktop | EH-076 | Codex (ethan), 2026-10-25 | Thin installed Edge/Chrome app window shares the Python service. Local packaging/build is authorised. Verify start, reconnect, close/reopen and crash recovery, with truthful process state and no unintended extra service. Installs with unexpected permissions/dependencies, signing and distribution need separate consent; hosting stays deferred. |
| 5: local voice and PTT | EH-077 | Codex (ethan), 2026-10-25 | Installed Windows local recognizer verified by enumeration. Implement deliberate push-to-talk, transcript preview, cancellation and mute. No raw audio persistence by default. Voice cannot answer an approval implicitly. Manual hardware capture remains to verify. |
| 6: optional wake word | EH-077 | Unassigned; depends on PTT, 2026-10-25 | Explicit opt-in after PTT works. Verify visible listening state, immediate disable, false-wake cancellation and no action from background audio. Document local resource use and retention from measurement. |

Backend contract candidates are an approval ID bound to exact action parameters,
requester/conversation, policy revision and expiry; pending/approved/rejected/expired/
consumed states; atomic consumption and append-only outcome evidence. These are design
candidates for the audit, not a claim of an implemented approval mechanism. A person's
approval cannot override an action currently marked `never`.
Build and implementation relays are the first confirmation paths. Other actions
configured as `ask` must fail closed until their confirmation flow exists, while
shipped `allow` behaviour stays unchanged. Do not claim full policy enforcement
from the first two paths alone.

Provider integration starts with the installed CLI help and the
[official Codex app-server documentation](https://learn.chatgpt.com/docs/app-server).
The [official Claude plan guidance](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
states, in its 2026-10-07 update, that SDK and `claude -p` usage can still draw on
subscription limits. This is provider guidance, not verification of this account's
entitlements or remaining limits.
Protocol, auth and approval support must be verified for the installed binary before
choosing an adapter. No credential-file inspection or token export is needed for this
discovery. UI settings show availability and instructions rather than secret values.
An official app-server integration requires a deliberate adapter decision and must
not bypass the `sky build` launch boundary. Never extract or copy authentication tokens.

### Coordination evidence

The backend owner has responded through the bridge: Claude (ethan) is free and has
made no changes. Its audit identifies immediate hand launch, implementation relay
`ask` treated as wording rather than confirmation, and no durable approval ledger.
It proposes backend-only files and tests, awaiting agreement on per-door build levels,
real relay confirmation, expiry and explicit versus bare `yes`. Ownership is still
accepted for backend-only implementation. The coordinator's concrete decision remains: default consequential
console/CLI build and implementation to `ask`, preserve explicit `allow` without
widening Telegram, ten-minute expiry, explicit `approve <id>` / `deny <id>` only,
atomic single consumption and current-policy recheck. No paid calls are permitted;
a harmless existing-session bridge acknowledgement probe is separately authorised.
Codex (ethan) retains all roadmap/plan edits; the coordinator
retains the two console-boundary files. The audit also flags console authentication
(EH-042) as a dependency: Host validation alone does not authenticate local processes.
No implementation has been authorised by this plan alone. Do not infer availability
or assignment from registration, process existence or acknowledgement.

## What it does not do

The initial plan withheld commits and pushes. The maintainer separately requested
the reviewed project commit and normal push on 2026-10-25. No release tag, deployment,
spending, installs or credential changes are included.
HUD work uses the authorised substitute brief. No changes to existing backend code by the plan
owner. Claude owns only the agreed backend implementation files. No telephony, cloud
voice, unattended external writes or silently approved actions. Existing root rules
on human submission remain binding. New runtime dependencies require a separate design
decision against the project's standard-library constraint.

## How it is measured

Verification so far, 2026-10-25: initial console-boundary patch passed the full 189-test
suite (2 skipped), Ruff and docs checks. Review reproduced blank cursor values being
discarded; after correction all six real local HTTP tests passed. Valid CLI-style
dispatch still works and whitespace checks pass. These are offline boundary checks.

An authorised harmless nonce probe used the real Ethan relay, registry and bridge
with isolated temporary state and a separate probe sender, preserving the live app
registration. Sending succeeded and Ethan recorded `queued`; one follow pass still
observed `queued`, without a result. The existing target session had not read its
inbox. No completed provider roundtrip is claimed, and no session was launched or
forcibly resumed.

Baseline evidence is the recorded git state and installed help, not a live provider
test. Run the documented unit suite, Ruff, keyless demo and shared docs checker for
implementation changes; report skips and live checks separately. Add focused cases for
invalid Host/body/offset, approval replay/expiry/policy changes, duplicate delivery,
restart recovery, unavailable providers, malformed saved layouts and voice cancel.

Record command, installed version, expected/actual outcome and timestamps for each
live probe without prompt secrets or account data. Measure roundtrip latency, timeout
behaviour and desktop/voice resource use only when those paths exist. A fake demo,
working service or registration alone never satisfies the live-roundtrip gate.
