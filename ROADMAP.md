# Roadmap

Every planned feature has an ID, a status and, once someone takes it, an owner. **This
file is the source of truth for what is being worked on.** Pick from here, and update
the row when you start and when you finish — see [Picking a feature](#picking-a-feature).

Words used below: a *door* is a way in (the console, Telegram, the CLI). A *KB* is a
knowledge base. A *hand* is the coding agent that does the work, started through
`sky build`. A *hint* is a keyword a KB claims, so an ask that contains it goes to that
KB. *Harvest* is filing what a run learned back into a KB. The *ledger* is Ethan's
SQLite record of what it did.

## Status

| Status | Means | Who moves it on |
|---|---|---|
| **Proposed** | an idea; the scope is not agreed yet | a maintainer, to Ready or Needs decision |
| **Needs decision** | a design choice must be made first — usually a privacy or policy rule | a maintainer, after discussion on the issue |
| **Ready** | scope and acceptance agreed; anyone may pick it | you, when you claim it |
| **In progress** | claimed — the row names the owner and the date | the owner, when the pull request opens |
| **In review** | a pull request is open | a maintainer, when it merges |
| **Done** | merged; the row names the version | — |

Priority: **P0** a correctness bug, fix first · **P1** the next release · **P2** planned ·
**P3** an idea. Size: **S** about a day · **M** a few days · **L** a week or more, and
worth splitting.

## Picking a feature

1. **Choose a `Ready` row.** New here? Take one marked *good first issue*.
2. **Claim it.** Open an issue with the *Claim a feature* template naming the ID, or
   comment on the feature's issue if one exists. A maintainer confirms within a few days.
3. **Mark it `In progress`** in this file — your handle and the date in the Owner
   column — in your first pull request, or in a one-line pull request of its own.
4. **For an L-sized feature, write a design note first**, from
   [the template](docs/features/TEMPLATE.md), and get it agreed on the issue before the
   code.
5. **Open the pull request.** Set the row to `In review`, and meet the acceptance
   criteria below — each one is a test. [Contributing](CONTRIBUTING.md) has what every
   change needs.
6. **On merge,** the row becomes `Done` with the version.

One feature per person at a time. A claim with no visible progress for 21 days goes back
to `Ready`, so nothing stays blocked by a claim nobody is working on. To propose
something new, open an issue with the *Propose a feature* template; it gets an ID when
accepted.

## Features

### 0.1.0 — correctness

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| EH-001 | [Hints decide without a model call](#eh-001) | router | P0 | M | Done — 0.1.0 | @arupmmi07 |
| EH-002 | [No silent fallback to the first KB](#eh-002) | router | P0 | S | Done — 0.1.0 | @arupmmi07 |
| EH-003 | [The router model sees only the purposes and the ask](#eh-003) | router | P0 | S | Done — 0.1.0 | @arupmmi07 |
| EH-004 | [Chain steps run with the right role](#eh-004) | router | P0 | S | Done — 0.1.0 | @arupmmi07 |
| EH-005 | [The console refuses requests from other web pages](#eh-005) | doors | P0 | S | Done — 0.1.0 | @arupmmi07 |
| EH-006 | [A file is ingested by where it lives](#eh-006) | harvest | P0 | S | Done — 0.1.0 | @arupmmi07 |
| EH-007 | [Doors ship with the privacy wall on](#eh-007) | doors | P0 | M | Done — 0.1.0 | @arupmmi07 |
| EH-008 | [Every ask ends with a close-out line](#eh-008) | doors | P0 | S | Done — 0.1.0 | @arupmmi07 |
| EH-009 | [The ontology validator imports what it uses](#eh-009) — *good first issue* | tools | P0 | S | Done — 0.1.0 | @arupmmi07 |
| EH-010 | [No private names or paths in the repository](#eh-010) | hygiene | P0 | S | Done — 0.1.0 | @arupmmi07 |

### 0.3.0 — a record you can trust

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| EH-020 | [The ledger records door, route and reason for every ask](#eh-020) | ledger | P1 | M | Ready | |
| EH-021 | [Cost and usage per task](#eh-021) | ledger | P1 | S | Ready | |
| EH-022 | [`ethan --dry-run`](#eh-022) | cli | P1 | M | Ready | |
| EH-023 | [Answer "status" asks from the ledger](#eh-023) — *good first issue* | router | P1 | S | Ready | |
| EH-024 | [Tests for the secret patterns](#eh-024) — *good first issue* | trust | P1 | S | Ready | |
| EH-025 | [Tests for routing and the harvest policy](#eh-025) | trust | P1 | M | Ready | |
| EH-026 | [Config holds only what the code reads](#eh-026) — *good first issue* | config | P2 | S | Ready | |
| EH-027 | [Docs and diagrams match the code](#eh-027) | docs | P1 | S | Ready | |
| EH-028 | [Answer "updates" asks](#eh-028) | router | P3 | M | Proposed | |

### 0.4.0 — a brain you configure

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| EH-030 | [Brain configuration, written down](#eh-030) | brain | P1 | M | Needs decision | |
| EH-031 | [One interface for every knowledge base](#eh-031) | kb | P1 | L | Ready | |
| EH-032 | [A local KB that needs no server](#eh-032) | kb | P1 | M | Ready | |
| EH-033 | [Search more than one KB for one ask](#eh-033) | kb | P2 | M | Needs decision | |
| EH-034 | [A router model from any provider, or none](#eh-034) | router | P1 | M | Ready | |
| EH-035 | [Hands come from config, not code](#eh-035) | hands | P1 | S | Ready | |
| EH-036 | [Who answers a question](#eh-036) | router | P2 | M | Needs decision | |

### 0.5.0 — the operator loop

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| EH-040 | [Approvals through the door you used](#eh-040) | loop | P2 | L | Needs decision | |
| EH-041 | [Progress while a run is live](#eh-041) | loop | P2 | M | Proposed | |
| EH-042 | [A console token](#eh-042) | doors | P2 | S | Ready | |
| EH-043 | [Recurring asks](#eh-043) | loop | P3 | L | Needs decision | |
| EH-044 | [Pick up work assigned to you](#eh-044) | loop | P3 | L | Needs decision | |

### 0.6.0 — reach and distribution

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| EH-050 | [`pip install` and an `ethan` command](#eh-050) | distribution | P1 | S | Ready | |
| EH-051 | [CI on macOS and Windows](#eh-051) | distribution | P2 | M | Ready | |
| EH-052 | [A recorded demo in the README](#eh-052) | docs | P1 | S | Ready | |
| EH-053 | [A webhook door](#eh-053) | doors | P2 | M | Proposed | |
| EH-054 | [Voice and image doors](#eh-054) | doors | P3 | L | Proposed | |

## Details

Each entry says what is wrong or missing today, what done looks like, and where in the
code it starts. Every acceptance line is a test.

### Correctness

Most of these put the code back in line with [Routing](docs/routing.md) and
[Architecture](docs/architecture.md), which describe the intended rules.

<a id="eh-001"></a>**EH-001 — Hints decide without a model call.** The docs say a hint
pins the KB with no model call. The router calls the model on every ask, then lets a
hint overwrite its pick, so a hinted ask still needs a model key and still sends the ask
out. A hint also matches only when it is written in lower case: the ask is lower-cased
and the hint is not, so the documented example `PROJ-` never matches. When two KBs'
hints match, the first KB in the file wins without a word; the docs say the model
decides. *Done when:* "review PROJ-412", with a KB whose hint is `PROJ-`, is routed as a
review to that KB with zero model calls, checked with a stub model; `PROJ-` matches
`proj-412` and `PROJ-412`; an ask matching two KBs goes to the model with only those two
as choices; an ask whose kind the keyword rule cannot tell still calls the model, and
the hinted KB wins. *Starts in:* `ethan/router.py` — `_hint_route` and the top of
`handle`.

<a id="eh-002"></a>**EH-002 — No silent fallback to the first KB.** When the model names
a KB that is not in the map, the router quietly uses the first KB in the file. The docs
say the task gets no KB and a message, because answering from the wrong KB is worse than
answering from none. *Done when:* an unknown KB from the model gives a reply saying no
knowledge base matched; nothing is searched, briefed or filed under a KB the router did
not choose; the ledger records no KB for that ask. *Starts in:* `ethan/router.py`,
`handle`, after the model call.

<a id="eh-003"></a>**EH-003 — The router model sees only the purposes and the ask.** The
routing call also carries the last eight messages of the conversation, which include up
to 1,500 characters of each hand's result. The ask itself reaches the model twice — it
is stored, read back, then appended again — and three times from the console, which
stores it once more. The docs say the model sees each KB's purpose and the ask, nothing
else. *Done when:* the routing
call's messages are exactly one system message with the KB purposes and one user message
with the ask, checked by a test with a stub model; follow-up detection gets at most a
yes/no that an earlier result exists, not its text; each ask is stored once, whatever
the door. *Starts in:* `ethan/router.py`, `handle`; `ethan/door_console.py`, `_ask`.

<a id="eh-004"></a>**EH-004 — Chain steps run with the right role.** A chain ("fix it
with claude, then have codex review") starts each step with no task kind, and a missing
kind maps to the read-only reviewer role. So the step meant to fix the code cannot edit
it. The chain's close-out also drops the task ID. *Done when:* each step in the route
carries a kind; with a fake `sky` on `PATH`, a build step runs as `developer` and a
review step as `reviewer`; the harvest after a chain is linked to the last step's task.
*Starts in:* `ethan/router.py` — `ROUTE_SCHEMA` and the chain loop; `hands.role_for`.

<a id="eh-005"></a>**EH-005 — The console refuses requests from other web pages.** The
console listens on `127.0.0.1:8787` with no sign-in. It reads any POST body as JSON,
whatever its content type, and never checks where the request came from. So any web page
open in your browser can start a build or an ingest: a plain-text POST from another site
is a "simple request", which browsers send without asking the server first. *Done
when:* a POST to `/api/ask` or `/api/ingest` whose `Origin` is not the console's own is
refused with 403; a POST without `Content-Type: application/json` is refused with 415;
the console page and `bin/ethan` still work; a test covers each case. *Starts in:*
`ethan/door_console.py`, `Handler.do_POST`.

<a id="eh-006"></a>**EH-006 — A file is ingested by where it lives.** `ethan --ingest`
picks the KB from the directory you run it in, and only falls back to the file's own
folder — though the comment above the code says the file's location decides. So a
private note outside every KB, ingested from inside a work repository, is filed into the
work KB. *Done when:* a file outside every KB's repositories is refused whatever the
working directory; a file inside a KB's repository goes to that KB whatever the working
directory; a test covers both. *Starts in:* `ethan/harvest.py`, `ingest_document`.

<a id="eh-007"></a>**EH-007 — Doors ship with the privacy wall on.** The docs say a
personal door cannot file into a work KB. The check exists, but the shipped
`config/doors.json` lets both the console and Telegram write to every class, so the wall
is off by default. The CLI has no door of its own: it speaks through the console door,
so it cannot be given a class. *Decision needed:* the default classes for each door, and
whether the CLI becomes its own door. *Done when:* the shipped config has at least one
door that refuses a class, and a test proves a harvest through it is refused; the CLI's
asks are recorded under their own door name. *Starts in:* `config/doors.json`,
`harvest.apply`, `door_console._ask`.
*Decided and done, 0.1.0:* Telegram may file only into `personal`; the console and a new
`cli` door may file into every class; each task row records its door.

<a id="eh-008"></a>**EH-008 — Every ask ends with a close-out line.** `bin/ethan` stops
when it sees "Session can close" or "Not closing". Only a successful build, review or
chain prints one. After a question, a chat reply, a follow-up, an error or a failed task,
the CLI waits out its idle limit — 20 polls, three seconds apart — so a question
answered at once takes about a minute to return. On Telegram, an error inside an ask is
never caught, so the person gets no reply at all. *Done when:* every path through
`router.handle` ends with exactly one close-out line, tested per kind; `ethan "a
question"` returns within five seconds of the answer, with a stub model; an exception on
the Telegram door is reported to the sender. *Starts in:* `ethan/router.py`,
`ethan/door_telegram.py`, `bin/ethan`.

<a id="eh-009"></a>**EH-009 — The ontology validator imports what it uses.**
`config/ontologies/validate_ontology.py` has `import os` inside its docstring, so the
import never runs, and the script stops with `NameError: name 'os' is not defined` on
line 10. *Done when:* run with no arguments it prints its usage and exits with code 2;
run without PyYAML installed it names the missing package; a test runs both.

<a id="eh-010"></a>**EH-010 — No private names or paths in the repository.**
`config/ontologies/validate_ontology.py:54` lists names and a code from a private setup.
`tools/make-skill-cards.py` writes into a folder on one person's machine (line 15) and
names tools from a private deployment (line 126). `tools/extract-model.sh` drives one
private server's admin API and container. *Done when:* each file is removed, or takes
its paths and names from arguments or `.env`; a test fails if any tracked file contains
an absolute home-directory path. Whether older commits must be rewritten is a maintainer
decision.
*Done, 0.1.0:* `tools/extract-model.sh` is removed, and
`tests/test_routing.py` fails on any absolute home-folder path in a tracked file.
*Progress, 2026-09-30:* the private names, the code, the tool names and the home-folder
path are gone from every commit — history was rewritten before the first push — and
the validator's word list now holds only generic words; private words belong in your
own copy. *Still open:* `tools/extract-model.sh`, and the test that fails on an
absolute home-directory path.

### A record you can trust

<a id="eh-028"></a>**EH-028 — Answer "updates" asks.** The router can class an ask as
`updates` (recent mail or notifications), and Ethan replies that it cannot answer it
yet. *Decision needed:* which sources, and through which credential. *Done when:* an
`updates` ask lists recent items from one configured source, with no model call beyond
routing, checked with a stub source.

<a id="eh-020"></a>**EH-020 — The ledger records door, route and reason for every
ask.** The README says the ledger keeps every task, door, route decision and outcome.
The `tasks` table has no door and no reason; the route is only printed to the log.
Questions, chat and follow-ups create no row at all. *Done when:* every ask creates one
row with its door, kind, KB, hand, the router's reason, and whether a hint or the model
decided; `ethan --status` shows them; a database from today is migrated in place, the
way `store._migrate_brain_to_kb` already does. *Starts in:* `ethan/store.py`,
`router.handle`.

<a id="eh-021"></a>**EH-021 — Cost and usage per task.** `hands.run` returns the usage
`sky build` reports; nothing stores it. *Done when:* each run row stores tokens and cost
when `sky` reports them; `/api/state` and `ethan --status` show today's total; a test
with a fake `sky` checks the stored numbers. *Starts in:* `ethan/hands.py`, `run`;
`ethan/store.py`.

<a id="eh-022"></a>**EH-022 — `ethan --dry-run`.** There is no way to see what Ethan
would do without doing it, though `sky build` has its own `--dry-run`. *Done when:*
`ethan --dry-run "review README"` prints the kind, KB, hand and role it chose, and the
exact `sky build … --dry-run` command with the brief, and starts no hand; with no `sky`
installed it still prints the command; a test covers both. *Starts in:* `bin/ethan`,
`router.handle`, `hands.build_command`.

<a id="eh-023"></a>**EH-023 — Answer "status" asks from the ledger.** An ask the router
classes as `status` gets a fixed reply pointing at this row, though the ledger already has what
it needs (`store.pending`, `store.recent_tasks`). *Done when:* "what is running?" lists
the running tasks and the last five finished ones from the ledger, with no model call
beyond routing, checked with a stub model. `updates` (mail and notifications) stays out
of scope. *Starts in:* `ethan/router.py`, the `status` branch of `handle`.

<a id="eh-024"></a>**EH-024 — Tests for the secret patterns.** `ethan/redact.py` holds
the twelve patterns that gate every KB write, and no test covers them. *Done when:* each
pattern has one string it must catch and one near-miss it must not; for every string it
catches, `find(scrub(text)[0])` returns nothing.

<a id="eh-025"></a>**EH-025 — Tests for routing and the harvest policy.**
`router.handle` and `harvest.apply` hold the rules the README is built on, and neither
has a test. The suite also writes into the repository's own `state/` folder, so running
it adds rows to a live ledger. *Done when:* with a stub model and a fake `sky`, tests
cover each kind, the hint path and the unknown-KB path; every refusal in
`harvest.apply` has a test (unknown KB, read-only, unknown door, wrong class, too short,
too long, secret found); the suite writes only to a temporary folder. *Starts in:*
`tests/`, `ethan/util.py` (`ROOT`), `ethan/store.py`.

<a id="eh-026"></a>**EH-026 — Config holds only what the code reads.**
`config/ethan.json` still lists a command per hand, a review command, a note and
`hand_silence_sec`. None of them is read since hands moved to `sky build`; only the hand
names are. `run.sh` still calls the service by an old name. *Done when:* the unused keys
are gone; a test fails if `ethan.json` holds a key no module reads; the `run.sh`
comment names Ethan.

<a id="eh-027"></a>**EH-027 — Docs and diagrams match the code.** Several claims are
wrong today. `docs/images/architecture.svg` says a hint pins the KB "with no call at
all". `docs/images/shape.svg` says adding a hand is "one config line". The task-flow
diagram shows a push approved through Telegram, which Ethan cannot do. The README says
the router key is for routing only, but the same model answers questions, follow-ups and
chat. `architecture.svg` names a `--state` flag; the flag is `--status`. *Done when:*
each claim is made true or removed, and each changed diagram has its PNG rendered again.
*Depends on:* EH-001, EH-035.

### A brain you configure

<a id="eh-030"></a>**EH-030 — Brain configuration, written down.** Ethan's goal is a
"brain" you assemble: one or many KBs, a model, skills, policy and tools. The word is
defined only in comments (`.env.example`, `ethan/kb.py`), and no document says how to set
one up. *Decision needed:* what a brain configuration holds, and which parts Ethan owns
and which belong to `sky`. *Done when:* `docs/brain.md` explains each part with one
working example, and `ethan --status` prints the brain in use.

<a id="eh-031"></a>**EH-031 — One interface for every knowledge base.** `ethan/kb.py`
speaks one server shape: a JSON-RPC `tools/call` with fixed tool names and a
`tenant_code`, with no MCP `initialize` step first. The goal is any KB — a retrieval
service, a vector database, a graph store. *Done when:* a KB entry in the map names its
adapter; today's client becomes the `mcp` adapter; every adapter offers search, ingest
and job status, and passes one shared contract test. Write a design note first.

<a id="eh-032"></a>**EH-032 — A local KB that needs no server.** A clean checkout has no
KB it can reach, so context and harvest cannot be tried without setting one up. *Done
when:* a `local` adapter keeps notes in SQLite full-text search under `state/`; the
example map uses it; on a clean checkout, with no network, a question gets cited hits and
a harvest files a note. *Depends on:* EH-031.
*Progress, 0.1.0:* a KB with `"folder"` is a directory of Markdown notes, searched by
word overlap and written as files, with no server; the demo uses one. Still open: full-text
search under `state/`, and the example map using it.

<a id="eh-033"></a>**EH-033 — Search more than one KB for one ask.** Each ask gets
exactly one KB. *Decision needed:* which KBs may be searched together, given their
privacy classes. *Done when:* a route may name several KBs; each hit is cited with its
KB; a personal KB is never mixed into a work brief.

<a id="eh-034"></a>**EH-034 — A router model from any provider, or none.** `ethan/llm.py`
calls one provider's chat endpoint with a key from one fixed variable. With no key, every
ask fails, even one a hint could route. *Done when:* the base URL, the name of the key
variable and the model name come from config; any endpoint that speaks the common
chat-completions format works, including one on `localhost`; with no model configured,
hint-routed asks still work and every other ask gets a clear message. *Depends on:*
EH-001.

<a id="eh-035"></a>**EH-035 — Hands come from config, not code.** The route schema and
the hint pattern name three hands in code. *Done when:* the list of hands comes from
`config/ethan.json`; a test adds a fourth hand by config alone and routes to it; a hand
`sky` does not know is refused with a clear message. *Starts in:* `ethan/router.py` —
`ROUTE_SCHEMA`, `_hint_hand`.

<a id="eh-036"></a>**EH-036 — Who answers a question.** Questions, follow-ups and chat
are answered by the router model, which then reads KB content and earlier results. That
weakens the rule that the router holds the least. *Decision needed:* keep this under a
second, separate model credential, or send questions to a read-only hand through
`sky build`.

### The operator loop

<a id="eh-040"></a>**EH-040 — Approvals through the door you used.** The task-flow
diagram shows Ethan asking "push?" and taking a yes through Telegram. Ethan has no
approval step; a routed build starts at once. *Decision needed:* where approvals live —
`sky` brokers outward writes — and how a door proves the person saying yes is you.
*Done when:* a push the hand proposes waits for a yes through the same door, and a yes
from another door or another user is refused.

<a id="eh-041"></a>**EH-041 — Progress while a run is live.** The door hears
"delegating" and then the result; a 30-minute run says nothing in between. The console
can follow the log; Telegram and the CLI cannot. A short update — the phase or the last
line, checked for secrets — every few minutes. Input during a run stays closed.

<a id="eh-042"></a>**EH-042 — A console token.** Any process on the machine can call the
console API. *Done when:* the service writes a random token under `state/` at start; the
page and `bin/ethan` send it; a call without it gets 401. *Depends on:* EH-005.

<a id="eh-043"></a>**EH-043 — Recurring asks.** There is no scheduler, by design — Ethan
does not act without a door. *Decision needed:* whether it ever should, and what it may
do then (read-only asks only, for example).

<a id="eh-044"></a>**EH-044 — Pick up work assigned to you.** A ticket assigned to you is
picked up by your agent, which does the work and then stops and waits for you. The
assignee never changes. *Decision needed:* needs EH-040 and a broker in `sky` first.

### Reach and distribution

<a id="eh-050"></a>**EH-050 — `pip install` and an `ethan` command.** There is no
packaging file, and `bin/ethan` is run by its path. The ledger and run logs sit inside
the checkout. *Done when:* `pip install .` gives an `ethan` command and a way to start
the service; state lives in a user data folder unless configured; CI installs the
package and runs the suite against it.

<a id="eh-051"></a>**EH-051 — CI on macOS and Windows.** CI runs on Ubuntu only, and
stopping a hung build uses a Unix process-group kill. *Done when:* the suite passes on
macOS and Windows runners, or the README names the supported systems.

<a id="eh-052"></a>**EH-052 — A recorded demo in the README.** One CLI ask, end to end,
recorded, with the exact commands. *Done when:* the recording reproduces on a clean
checkout with no keys, through `--dry-run` and the local KB. *Depends on:* EH-022,
EH-032.
*Progress, 0.1.0:* `./run.sh --demo` runs one ask end to end with no key, and the README
shows a picture of its real output, made by `tools/render-terminal.py`. Still open: the
`--dry-run` path, and a recording of the CLI rather than a still picture.

<a id="eh-053"></a>**EH-053 — A webhook door.** A door is one call:
`router.handle(chat_id, text, reply, door=…)`. A signed HTTP webhook door, with its own
door name and class, that replies to a callback URL — the base for Slack and similar.

<a id="eh-054"></a>**EH-054 — Voice and image doors.** Speech to text on the way in,
text or speech on the way out; an image described as text. Each turns its input into text
before `router.handle`. One door per claim.

## Release review — 2026-10-01

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| EH-900 | Bring release documentation up to the shared standard | release | P1 | M | Done — 0.1.0 | @arupmmi07 |

**Verified:** Add CHANGELOG.md, a keyless worked demo, numbered steps and PNG embeds. Resolve all six checker failures; reconcile existing P0 rows before tagging.
*Done, 0.1.0:* `check-docs.py` reports 0 FAIL and 0 WARN, and no P0 row is open.
