# Routing

How a task chooses a knowledge base — and why it is two stages.

## Hints first

Each knowledge base declares hints:

```json
"hints": ["PROJ-", "billing", "invoice"]
```

A task naming `PROJ-412` (or `proj-412` — case does not matter) matches. When one KB
matches and the ask starts with a word that names the work — `review`, `audit`, `fix`,
`implement`, `build`, `add`, `refactor`, `write`, `update`, `change` — no model is
called. It is free, deterministic, and explainable. An ask that names two hands or says
"then" sounds like a chain, so it goes to the model.

## The small model second

When hints cannot decide — two KBs match, none do, or the kind of work is unclear — a
small model decides. It sees:

- each knowledge base's `purpose` string — only the matching ones, when two matched
- the ask
- whether an earlier result exists in this conversation, as yes or no

Nothing else. Not the conversation, not earlier output, not the repository, not your
files. When one KB matched but the kind was unclear, the model picks the kind and the
hinted KB stands.

**It uses its own credential**, separate from the tokens the hand will use. The router
is the component most exposed to arbitrary text, so it is the one that should hold the
least.

## Writing a good `purpose`

This is the whole routing signal. Be specific.

| Poor | Good |
|---|---|
| "work" | "the billing platform: invoices, payment providers, dunning, refunds" |
| "notes" | "personal notes, reading, and anything that must not leave this laptop" |
| "client" | "the ITSM product: incident, problem and service-desk practices" |

## When nothing matches

The task gets **no** knowledge base and a message saying so. It still runs, with no KB
context, and nothing is filed anywhere at close-out.

It does not fall back to a default. A repository under a client knowledge base never
falls back to a work one — answering from the wrong knowledge base is worse than
answering from none, and much harder to notice.

## Passing an ask to a running session

"Ask the codex session codex-ethan to review the tests" is not new work for a hand.
It is for a coding session that is already open. Before any routing, Ethan checks
whether the ask opens with *ask*, *tell*, *send … to* or a similar verb, and names a
session: the word "session" or a registered session's name, in the part that says who
the ask is for. If it does, the ask is relayed through a local message bridge
(`agent-bridge`), with no model call. It never becomes a build, so it never starts a
new session.

A name that matches no registered session matches nothing: "ask the claude session
foobar to …" sends nothing rather than picking another session.

- **One target.** Ethan matches the bridge's registered sessions by name, then by
  agent (`claude`, `codex`), then by the caller's folder. If that leaves one session,
  the ask goes to it. If it leaves none, nothing is sent. If it leaves several, Ethan
  lists them and asks which one; the next answer (a number, a name or "cancel")
  decides.
- **Review-only by default.** The receiving session is told not to change files,
  unless the ask says *implement*, *implementation mode* or *own it*.
- **Honest state.** The reply gives the bridge's message id and what its state
  means: *queued* has not been read, *delivered* is not done. Each relay is a row in
  the ledger.
- **Doors.** Only doors with `"relay": true` in `config/policy.json` may relay. As
  shipped, that is the console and the CLI. Telegram is not, because it is reachable
  from a phone.

**Following it to the end.** Ethan checks every open relay against the bridge every
`relay_poll_sec` seconds (30 by default, in `config/ethan.json`), and first thing after
it starts. Each change of state is told to the conversation that asked, in plain words;
a completed relay delivers the session's answer there, and a failed one says why. The
intent and the bridge's dedupe key are saved before the bridge is called, so a crash
between the send and saving the message id is recovered by sending the same key again:
the bridge refuses the duplicate and names the message it already has. Nothing is sent
twice. While a relay is unanswered, the close-out line says so instead of "nothing
pending".

## Reminders and checks on Ethan's own clock

Ethan acts when a door asks. The clock is the one exception, and a narrow one.
"Remind me at 15:00 to send the report" and "every weekday at 09:00, what is running?"
are read by a rule, with no model call, and stored in the ledger. At the time, a
reminder is put into the conversation that set it; a scheduled ask is run through the
`clock` door, which may remind and read — a question, a status ask, a review-only
relay — and nothing more. The router refuses the clock a build, a review or a chain,
and the clock files nothing into any knowledge base. A reminder that came due while
Ethan was stopped is told as missed, with its time, not run late without a word; a
recurring one moves on to its next time. "My reminders" lists them; "cancel reminder
#3" drops one. The times Ethan reads are listed in `ethan/clock.py`. Anything else gets
a plain "I could not find a time", not a guess.

## One task list

"Add task: send the report by Friday", "my tasks", "done #3", "snooze task #3 until
tomorrow", "drop task #3" are read by a rule, with no model call. Every task — one you
typed, an action item from a meeting, a mail a watch says you must answer — is a row in
one list with its source and a link back, so "what should I do now?" has one answer,
ordered by what is due and with overdue items flagged. Marking a task done touches
only the list; the source is never changed. A source that reports the same item again
(same link, or same title when there is no link) gets one task, not two. A date Ethan
cannot read is left unset and said so, never guessed.

## Watching a source through a session

"Watch mail through the claude session ethan every weekday at 09:00: what must I reply
to?" sets a watch. At each time, Ethan asks that session the question as a review-only
relay, with "only items since the last run" and a fixed answer shape: one line per
item, title, link, why it matters, due date. The session reads the source through its
own connectors; Ethan holds no credential for it and never sends anything from it.
Each item in the answer becomes a task on the one list, once; `- nothing` is told as
nothing new; lines that do not fit the shape are shown and are not tasks. "My watches"
lists; "stop watch #N" ends one. The design note is
[EH-063](features/EH-063-watch.md).

## Getting hold of you

Whatever Ethan has to tell you — a reminder, a relay's answer, a watch's items — goes
to the conversation that asked; the console and the CLI read it there. It also goes to
your phone, through the Telegram door, when the text says *urgent*, or when you have
not typed anything for `reach.away_after_min` minutes (20 by default) and it is not
`reach.quiet_hours` (22:00 to 07:00 by default). Urgent items ignore quiet hours. Every
attempt is recorded: sent, skipped and why, failed and why. Without a Telegram token
and your user id, Ethan says the phone is not configured and uses the desktop alone. A
call is not built; see [EH-070](../ROADMAP.md#eh-070).

## One policy file

Every rule about what Ethan may do is in `config/policy.json`, and only `ethan/policy.py`
reads it. `doors` says what each way in may do: the privacy classes it may file into,
whether it may relay to a running session, whether it may start a hand. `actions` says
for each kind of act whether it is allowed when asked, done only when the person says
so in the ask itself (*ask*), or never done — as shipped, relaying with implementation
rights is *ask*, and sending in your name, pushing or merging, and starting or resuming
a session are *never*. An unknown door may do nothing and an unknown action is never.
Each action is enforced where it takes effect — a reminder in the clock, a status in the
ledger reader, a relay in the relay, a watch in the watch, the phone in reach, filing in
the close-out — and for every act but `relay_implementation`, *allow* and *ask* mean the
same. The last three are promises Ethan keeps by having no code path for them.
`tests/test_policy.py` tries every *never* and every *ask*, and checks the promises.

## Who Ethan is when it acts

Ethan acts as itself. It uses only its own accounts — the bridge app `ethan`, the
harness agent id `ethan`, its Telegram bot — never yours and never another agent's.
Everything it passes on says so: a relay ends with "Passed on by Ethan, for <owner>, via
the console door", a brief to a hand opens with the same line under *From*, and a phone
message starts with "Ethan:". The owner is `identity.owner` in `config/ethan.json` or
`ETHAN_OWNER`; it is written, never guessed from the machine.

## Privacy classes

Each knowledge base carries a class — `personal`, `work` or `client` — and each door
lists the classes it may file into, in `config/policy.json`. As shipped:

| Door | May file into |
|---|---|
| `telegram-private` | `personal` |
| `console` | `personal`, `work`, `client` |
| `cli` (`bin/ethan`) | `personal`, `work`, `client` |

A door that is not listed may file nowhere. A caller of the console's server can name
itself `console` or `cli`, nothing else, so it cannot claim another door's classes.

This is checked at harvest, not at routing, because the class that matters is the one
in force when something is written.
