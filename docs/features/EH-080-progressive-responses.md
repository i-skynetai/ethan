# EH-080 — Progressive response lifecycle

**Status:** In progress · **Owner:** coordinator (HTTP/HUD), codex-ethan (ledger/tests), Claude (existing router/relay seams) · **Issue:** local implementation, no publication

## What is missing today

The HUD polls ordinary replies every two seconds. An accepted HTTP request has no
durable client request identity, resumable response event cursor or explicit stop
tracking action. The existing session bridge exposes state transitions and one final
result, not answer-text deltas. A delivery channel is not an answer stream.

## What done looks like

- Repeated identical request identity dispatches at most once; changed payload conflicts.
- Reconnect reads ordered events without another dispatch or provider selection change.
- Cancellation before claim prevents execution. After dispatch, limitations are explicit.
- Cancelled/interrupted/error states cannot be revived by a late final response.
- Provider/project/privacy/chat/door scope stays bound to the original request.
- Raw provider chunks and detected credentials never enter public events.
- HUD distinguishes receiving, buffered, waiting for final, stopped tracking and terminal
  errors; no fabricated token animation, fake percentages or invented reasoning.
- Legacy console/CLI API behavior remains compatible.

These criteria complete response-lifecycle infrastructure, **not** true live answer
text for the selected Claude/Codex sessions. That requirement stays open until upstream
answer events and an explicitly reviewed incremental output policy both exist.

## Design

Reuse the canonical SQLite database for request identity, immutable input digest and
bounded sequenced events. Never create another scheduler or memory engine. A request
is claimed atomically once. Event polling is read-only with a bounded cursor; timeout
or reconnect never dispatches. Client persists only random request IDs, not prompts,
tokens or results. Fixed console scope is used by the HUD endpoints; backend helper
still checks explicit chat/door binding. Original scope validation and routing remain.

New POST /api/requests accepts request_id and the existing explicit request inputs.
GET /api/requests?request_id=...&after=... returns request state and events. POST
/api/requests/cancel stops local tracking/cooperative work where supported. All pass
existing Host, Origin, framing and optional authentication checks. Legacy /api/ask
remains available. Unknown or cross-scope identities do not disclose request contents.

The HUD displays the current request ID, observed state, delivery capability and stop
semantics. Final text remains safely rendered through text nodes in the conversation.
An uncertain POST retains its identity and draft: check the same request, never silently
resend with a new identity. Reload restores tracking IDs and reads from sequence zero;
per-request sequence filtering makes replay idempotent. Forgetting access clears local
tracking references and stale in-flight responses cannot repopulate them.

## Capability matrix

| Path | Upstream capability | Public text delivery | Stop semantics |
| --- | --- | --- | --- |
| Selected existing Claude/Codex bridge | Status plus completed result | Final-only, no live text deltas | Stop local tracking; no bridge remote-abort API |
| Existing configured API path | Current Ethan adapter returns a completed response; upstream SSE is not integrated | Whole-answer guarded final only; no live text deltas | No active provider-request abort is implemented; stopping local tracking does not stop remote work |
| Deterministic local command | One or several completed messages | Immediate checked messages | Before dispatch prevents action; does not undo completed effects |

API SSE parsing, bounded upstream buffering and cooperative transport cancellation are planned, not implemented. The lifecycle endpoints remain readiness-gated while router/relay hooks are pending; the current HUD uses the established reply path.

Do not auto-switch a selected session to an API-key provider. No API key is introduced,
no subscription voice entitlement assumed, and no live model calls are part of offline QA.

## True live-text design decision still required

Whole-answer withholding and irreversible early text release cannot both be guaranteed:
a credential appearing late means earlier displayed text cannot be taken back. Current
policy keeps the whole-answer gate. A future incremental mode needs explicit approval
for a narrower guarantee, along with a provider adapter supplying actual answer deltas.

Candidate design for review: buffer incomplete lexical units and lines with a strict
size/time limit, retain a rolling overlap covering every known credential prefix,
withhold private-key blocks from BEGIN through END, inspect every boundary split and
release only checked segments. If incomplete prefix/oversized token/unknown event cannot
be classified, remain buffered or fail closed. Keep provisional text visually marked;
detected credential terminates further output with a safe notice. Earlier released clean
segments cannot be retracted from the reader; arbitrary/novel secrets remain outside
pattern detection. Never describe this as equivalent to whole-answer withholding.

Before enabling: split-pattern property tests for every detector, multi-line keys,
Unicode and malformed UTF-8, reconnect replay, cancellation races, partial transport
failure, redacted diagnostics and explicit owner policy choice. Provider reasoning
events stay excluded; display answer text and observable status only.

## What it does not do

No charts, debug/context screens, context engines, graph, new harness integration,
provider installation or session creation. No live authentication activation, microphone
capture, credential grants, publication, commit or push. Streaming status does not mean
streaming answer text, and stopping tracking does not claim an agent has stopped.

## How it is measured

Offline synthetic provider and bridge fixtures, actual local HTTP with temporary ledger,
fresh-process restart checks, delayed response/cancel races and deterministic browser
replay tests. UI QA covers both themes and reconnect, with synthetic preview labelled.
Live provider validation requires separate authorization for exact target and payload.
Verification results will be recorded after the integrated checks, not inferred from
the prior visual-revision suite.

## 26 October 2026 implementation checkpoint

Implemented and tested: bounded canonical request/event tables, atomic one-winner claim,
input-bound idempotency, cursor replay, scoped lookup, local stop-tracking, late-result
protection, old-process interruption and fast final-before-binding backfill. HTTP and HUD
integration are behind the router's RESPONSE_EVENTS_SUPPORTED readiness marker. When
absent, the new POST refuses with 503 and the HUD selects the established reply path
before dispatch; it does not retry an uncertain request or switch providers.

Current full aggregate: 353 tests, OK with 2 skipped, 21.666 seconds. CI Ruff passes;
documentation checker 24 pass / 0 warn / 0 fail; whitespace clean. Both themes were
visually checked with the honest unavailable-tracking label and deterministic help
through the unchanged reply path. No external agent or API calls were used.

Pending integration: Claude retains router/relay ownership. Requested hook implementation
or explicit stopped-file handoff has not yet been confirmed. No readiness marker has
been enabled. Therefore selected-session end-to-end lifecycle tracking is not yet
verified, and the user-requested real progressive answer text is still unimplemented.
No generic API SSE parser was added in this slice; that path was deferred to keep the
focus on the user's existing Claude/Codex sessions.

Read-only upstream feasibility: [Codex app-server](https://learn.chatgpt.com/docs/app-server)
documents item/agentMessage/delta for the owning app-server turn stream.
[Claude headless](https://code.claude.com/docs/en/headless) and its
[CLI reference](https://code.claude.com/docs/en/cli-reference) document partial messages
with print mode and stream-json. Installed CLI help agrees. This does not establish
a supported read-only attachment to the answer stream of an arbitrary running inbox
session. No private session logs were read and no headless resume/control proxy was used.

Smallest future adapter: an opt-in feed owned by the existing provider session publishes
sanitized, sequenced events bound to the bridge message ID. It needs an explicit event
contract and an approved incremental output policy; whole-answer withholding remains
unchanged today. Actual public live_text_deltas remains false on all current paths.

Final independent review fixed late acceptance/cancellation and uncertainty-before-fallback races. Deferred-response Node regressions pass. A clearly labelled offline UI fixture verified accepted/running/completed states, reload of the same request identity, and stopped tracking in dark/light themes. This is synthetic UI evidence, not live session integration.
