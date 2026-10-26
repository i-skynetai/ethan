# Coordination survives a restart

Ethan coordinates work. Claude and Codex reason over source knowledge through their
own scoped tools. Sky Harness controls execution. There is one path from the shared
console to the router, policy/approval, hand or relay, ledger and close-out; desktop
and voice do not create another agent or memory system.

The existing SQLite ledger stores tasks, results, approvals, relays and coordination
records. A coordination record is a short goal, constraint, decision, owner, status or
result pointer with a source reference. It is not a document copy, embedding, graph
or generated summary of source knowledge. No email/chat archive is ingested.

The `context` module accepts explicit structured commands when its router hook is
enabled. For example, using a project path chosen by the person:

```text
coordinate {"project":"/absolute/project/path","privacy":"work","kind":"goal","name":"review","summary":"Finish the current patch review","source":"docs/plan.md#review","owner":"reviewer"}
show coordination {"project":"/absolute/project/path","privacy":"work"}
```

Kinds are `goal`, `constraint`, `decision`, `next_step`, `ownership`, `status` and `result`. A record
requires a short summary, source pointer and explicit owner.
Use a real absolute project directory on the host; relative paths are refused so a
different working directory after restart cannot change the project's identity.
Updates supersede the
previous record for the same conversation, project, privacy, kind and name, retaining
the old record for audit. Unknown privacy/door values and detected credentials are
refused. Read boundaries use the same door privacy classes as the rest of Ethan.

The bounded context handed to an agent contains coordination and cited source
pointers only. Ethan does not fetch their content here. The chosen KB's privacy
class and exact project/conversation scope constrain which records can be included.
Missing records are reported as missing. Historical permissions are never current
authorization: current policy and a fresh matching approval always take precedence.

Task/relay ledgers remain authoritative for whether work ran. Conversation history
is a bounded display and prompting aid. A restart does not turn a goal, a prior result
or a waiting approval into a new dispatch. Interrupted work requires an explicit
continuation. A bounded, secret-scrubbed handoff audit records action, source chat/door,
target, executor, linked task/relay, timestamps, snapshot digest and result; it does
not itself send, approve or retry. It is ordinary local SQLite evidence, not a
tamper-proof log.

Module tests verify restart retention and isolation without fetching source documents
or launching agents. Router/brief integration and end-to-end interruption tests must
pass before treating the source module as a completed user flow.

## Selected-session conversation

The scoped selected-chat helper uses an explicit absolute project directory, privacy
(`personal`, `work` or `client`), conversation, originating door and selected provider
reference. Both project and privacy absent means the current ask only. Partial or
invalid scope is refused; Ethan never assigns old messages to today's project.

Legacy conversation messages lack this scope and are excluded entirely. New completed
selected-chat turns can be recorded in the same canonical ledger, linked to the exact
relay ID. Only safe completed answers join future references. Repeated recording and
a fast answer arriving before the scope link do not send another ask or duplicate a
turn. A restart retains these scoped records without dispatching anything.

The original ask is kept verbatim in its own section, with a 12,000-character limit
that refuses longer asks rather than shortening them. At most 5,000 additional
characters contain recent completed scoped turns and compact coordination records,
including record IDs, source pointers and timestamps. They are explicitly untrusted
reference, never policy or approval. Recognized credentials are excluded; source
contents are not fetched. History is further isolated by the selected provider.

The helper, router, relay and console seams pass offline integration checks. A fresh
Python process reopens the ledger and routes a new ask carrying only its scoped
references through a fake bridge; repeated follow passes do not send it again.
The existing-session live chat path separately returned the approved test reply.
That live test did not exercise scoped context; no live context-continuity claim is
made from the offline fixtures.
