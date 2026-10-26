# Local security review — 2026-10-25

This is a source review and isolated regression-test record for the working tree,
not an external penetration test or a release certification. No live credentials,
microphone recording or external implementation actions were used in these checks.

## Findings and resolutions

- Implementation relays could bypass confirmation through direct dispatch or
  recovery. The shared send boundary now requires the matching approval. Recovery
  refuses an implementation row without it.
- A pending decision could be overwritten by a late denial or expiry. Conditional
  database transitions now allow only one decision to consume a pending approval.
- Mutable relay text or a changed destination could differ from what was approved.
  Execution and recovery check the approval's bound conversation, door, text, mode
  and target. A note saying "approved" is not proof.
- Unsupported policy actions treated `ask` as permission. They now refuse explicitly
  until a confirmation path exists. Shipped build doors ask; explicit `allow` is a
  separate configuration choice.
- Credential rejection in a context command occurred after conversation storage.
  The router now refuses recognized patterns before storage, prompting, rule hooks,
  approval creation or dispatch, including scheduled asks. Independent ingress and
  output tests passed together and in the full integrated suite.
- Raw hand output, ledger results and diagnostic logging were unguarded. The shared
  output gate now withholds an entire detected output with an explicit marker;
  the hand stream suppresses multiline and incomplete private-key blocks before
  logs or result tails. Defensive ledger gates and diagnostic stream protection
  cover recognized patterns. Eight isolated fake-output tests pass, including clean
  output preservation. Router and relay gates now run before further processing,
  watch absorption and delivery. Model replies, error replies and structured routing
  output have corresponding gates and regression tests. Detection remains limited
  to the recognized patterns.
- Layout changes now use a scoped, expiring preview and an explicit apply against
  the current revision. Unknown bindings and executable fields, stale revisions,
  replay, foreign origins and invalid hosts are refused. Layout changes never
  grant execution rights.
- Voice controls are serialized so release cannot overtake start. Voice starts
  muted, produces a transcript preview and never submits or approves an ask itself.

## Evidence

`tests/test_approvals.py` exercises same-conversation/door decisions, expiry,
restart, replay, policy changes, decision races and bound relay snapshots/targets.
`tests/test_policy.py` checks unsupported `ask` values fail closed.
`tests/test_context.py` and `tests/test_context_seam.py` check scoped coordination,
restart retention and context bound into the approved brief.

`tests/test_layout_http.py` exercises the actual loopback HTTP server: preview,
apply, reload and rollback; bypass attempts; scope, expiry, replay and revision
checks; and Host/Origin rejection, with dispatch mocked and asserted unused.
Its three tests and the Node voice-queue wrapper passed together. The wrapper
skips explicitly when Node is absent. The integrated snapshot passed 295 tests with
2 skipped, the documented CI lint selector, and 24 documentation checks.

## Remaining boundaries

- Loopback binding and browser Host/Origin checks do not authenticate another local
  process. Local-process authentication remains separate unfinished work.
- The ledger is mutable SQLite, not a tamper-proof audit log. A digest binds the
  approved payload; it does not protect against someone rewriting the database.
- Stored/retrieved reference text and voice transcripts cannot authorize actions.
  Current policy and a matching explicit approval govern execution.
- Coordination records are compact source pointers and work state, not an ingestion,
  retrieval, vector or graph engine. Missing context is not inferred.
- Existing-session hand-offs use agent-bridge and the providers' existing sessions;
  no provider credentials are copied into Ethan. A bridge round trip was checked
  against an existing session; a new provider sign-in adapter was not implemented.
- Secret detection covers recognized patterns; it cannot prove arbitrary text has
  no secret. No claim of universal credential detection is made.
- Microphone hardware behavior and wake-word recognition remain unverified. The
  opt-in local wake module has fake-process lifecycle tests, not microphone tests;
  it is off by default and does not rearm. A distributable desktop build and an
  external security assessment also remain unverified. An isolated wheel/sdist build,
  wheel install and packaged asset checks were subsequently verified by the
  coordinating session; this does not verify microphone hardware behavior.

## Integration ownership

The backend owner explicitly confirmed a stopped-file handoff on 2026-10-25 for
the output helper, hand runner, diagnostic logger and ledger gates. Codex implemented
those files and their isolated tests. The backend owner retains router and relay
changes for ingress refusal, selected-session conversation and processing/delivery
gates. Their integration tests and the combined suite pass; no
overlapping edits or forced session resume were made.

Explicit existing-session selection has a tested pure resolver and console validation:
invalid references refuse, and a missing router hook returns HTTP 503. Argument
forwarding is tested with a stub. This is not a completed general-chat round trip:
the real router hook now dispatches selected conversation through the review-only
relay gate without a model key; its offline seam tests pass. A live general-chat
answer was subsequently verified using one approved harmless request through the
existing Claude session and the real relay follower back to the originating console.
Scoped context continuity has separate offline restart/router tests; that live
request did not test scoped context. No new session,
provider authentication or credential copying is implied by selection.
