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
