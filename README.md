# Ethan

[![tests](https://github.com/i-skynetai/ethan/actions/workflows/tests.yml/badge.svg)](https://github.com/i-skynetai/ethan/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![licence](https://img.shields.io/badge/licence-Apache%202.0-blue)](LICENSE)

*The charioteer — steers, never fights.*

Ethan is a free, local assistant for professional work. It keeps your reminders, your
task list and your hand-offs, and gets the actual work done by the AI agents you already
have — Claude Code, Codex — rather than doing it itself. One always-on service on your
laptop, standard library only, with several ways in: a local web console, a command
line and Telegram. The person stays the authority.

![One service: doors on the way in, a router that decides, knowledge bases it reads, and hands that act](docs/images/architecture.png)

## Why it is built

Most people with Claude or Codex use them one chat at a time: open a session, explain
the context again, watch it, copy the result somewhere, forget to follow up. The tools
are strong; the operating around them is where the value leaks. Ethan is that operating
layer and nothing more. It decides when something needs doing and who should do it,
hands it over with the right context, follows it to the answer, and keeps a record you
can trust. It does not rebuild what the agents already do well: reading your mail or
tickets through their own connectors, summarising, drafting, writing code.

It is built for one person first — real benefit from AI in a working day, with no new
service to pay for or trust — and for teams after that. Because Ethan
is provider-neutral and keeps its rules, identity and ledger in the open, it is a small,
honest way for an organisation to make everyday AI use effective and accountable across
more than one provider. The [vision](docs/vision.md) says where it is going.

## Words you need

- **Door** — a way in: the console, the `ethan` command, Telegram.
- **Knowledge base (KB)** — where what you know is stored and searched: a remote
  service or a folder of Markdown notes.
- **Hint** — a keyword a KB claims, such as `PROJ-`; an ask containing it needs no model.
- **Hand** — the coding agent that does the work, started through `sky build` from
  [Skynet Harness](https://github.com/i-skynetai/skynet-harness).
- **Close-out** — the hand says what is worth keeping; Ethan checks policy before
  writing it.

## See it work in sixty seconds

You need Python 3.11 or newer and git. No key, no account, no server:

```bash
git clone https://github.com/i-skynetai/ethan.git
cd ethan
./run.sh --demo
```

The demo runs one ask through routing, launch, close-out and the ledger on a sample shop
copied to a temporary folder. Only the hand is faked: `demo/fake-sky` prints a fixed
review. Its real output:

![The real output of ./run.sh --demo: a hinted ask routed with no model call, launched as a reviewer, a note kept, the session closed](docs/images/demo.png)

## Use it in five steps

1. **Install the harness** and put its `core/bin/sky` on your `PATH`, or set `sky.bin`
   in `config/ethan.json`, or export `SKY_BIN`. Without it Ethan still routes, and
   refuses to build with a message saying which to do.
2. **Add your keys.** `cp .env.example .env`, then fill in `OPENAI_API_KEY`. It is used
   only for routing asks that no hint decides; reminders, tasks, relays and watches
   need no key at all.
3. **Describe your KBs.** `cp config/kb-map.example.json config/kb-map.json`, then give
   each KB a specific `purpose`, its `hints` and its privacy class. See
   [Routing](docs/routing.md).
4. **Start it.** `./run.sh`, or `pip install .` and `ethan-service`. The console opens
   at `http://127.0.0.1:8787`.
5. **Ask.** `ethan "review PROJ-412"`, `ethan "remind me at 15:00 to send the report"`,
   `ethan "ask the codex session codex-ethan to review the open merge request"`.

## What happens on every ask

![One ask: through a door, routed by hint or a small model, cited context, launched through sky build, then the close-out](docs/images/run.png)

Rules first: a reminder, a task, a relay or a watch is read with no model. For work, a
hint picks the KB, else a small model sees only each KB's purpose and the ask. Ethan
pulls cited context, writes a brief, and starts the hand through `sky build` with one
secret. Afterwards the hand proposes what to keep, and Ethan checks the privacy class
and scans for secrets before writing. See [Architecture](docs/architecture.md).

## What you get

- Routing by hint first, with a model only when the hint cannot decide; a KB the router
  did not choose is never used.
- Close-out that always reports: kept, nothing kept and why, or refused and why.
- A privacy wall on by default: Telegram may file only into personal KBs.
- A SQLite ledger of tasks, runs, logs, relays, reminders and every close-out decision.
- Asks handed to an open coding session and followed to the answer; reminders, one
  task list, and watches on your mail or tickets through that session — by rules, and
  nothing sent on your behalf.

## What it is not

- Not an agent that approves, merges or pushes. It picks and launches; you decide.
- Not a policy engine. The harness enforces what a run may do; Ethan only chooses.
- Not finished: a call when you are away and one policy file are open rows in the
  [roadmap](ROADMAP.md).

## Status

Version 0.2.0. 144 tests, standard library only, CI on Python 3.11 to 3.13:
`python3 -m unittest discover -s tests -t .`. The real hand path has been tested only
with a fake `sky`. Changes: the [changelog](CHANGELOG.md).

## Links

| | |
|---|---|
| [Vision](docs/vision.md) | Where Ethan is going: an assistant that hands the work to Claude and Codex |
| [Architecture](docs/architecture.md) | Doors, router, hands, close-out |
| [Getting started](docs/getting-started.md) | Keys, knowledge bases, first task |
| [Routing](docs/routing.md) | How an ask is read and where it goes |
| [Roadmap](ROADMAP.md) | Every planned feature, its status and owner |
| [Contributing](CONTRIBUTING.md) | Running the checks, claiming work, docs rules |

## Licence

Apache 2.0. See [LICENSE](LICENSE).
