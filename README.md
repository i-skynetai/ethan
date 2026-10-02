# Ethan

[![tests](https://github.com/arupmmi07/ethan/actions/workflows/tests.yml/badge.svg)](https://github.com/arupmmi07/ethan/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![licence](https://img.shields.io/badge/licence-Apache%202.0-blue)](LICENSE)


*The charioteer — steers, never fights.*

**A personal agent that decides which knowledge base and which coding agent a task
needs, launches it under policy, and files what it learned back.** One always-on
service, several doors in, several knowledge bases, several hands.

```
   Telegram ─┐
   console  ─┼──►  router  ──►  knowledge base  ──►  hand          ──►  harvest
   CLI      ─┘   (intent →      (the right one      (Claude ·          (redact,
                  KB + hand)     for this task)      Codex · Kimi)      file back)
```

Ethan does not do the work. It decides *who* should, gives them the right context,
and records the result. The person stays the authority.

## Why

Without it you are the operator, every session: pick the knowledge base, pick the
coding agent, write the brief, watch it, then decide what to keep. That is the job
Ethan takes — not the engineering judgement, the operating.

## What it does

- **Routes.** Reads the ask, matches it against each knowledge base's stated purpose,
  and picks one. Hints first, a small model only when hints are ambiguous.
- **Launches under policy.** Calls the same `sky build` path a person would call, so
  the run gets a role, a tool allowlist and a human gate. It does not spawn a coding
  agent directly.
- **Separates its own credential.** The router model uses a low-privilege key of its
  own. It never sees the tokens the hand uses.
- **Harvests.** After the run exits, redacts and files the result back into the
  knowledge base. After exit, not continuously — a session that is still running has
  not learned anything yet.
- **Keeps a ledger.** SQLite. Every task, door, route decision and outcome.

## How it fits together

![One service: doors on the way in, a router that decides, knowledge bases it reads,
and hands that act](docs/images/architecture.svg)

One Python process. Every arrow crosses a process boundary, and the router is the only
part that knows everything.

## Three design decisions

**Ethan replaces the operator, not the accountable human.** It picks and launches. It
does not approve, merge or push.

**It calls `sky build`, never a coding agent directly.** Spawning `claude` itself was
built and rejected: the child inherited every secret in the environment and no policy
applied. Going through the harness means one place decides what a run may do.

**Close-out is never silent.** A run that ends without a result says so. The failure
mode that matters is not a crash — it is a session that quietly produced nothing and
reported nothing.

## Setup

Python 3.11+ and the standard library, plus two things from outside:

| | |
|---|---|
| **An OpenAI key** | routing only — one small call to decide which KB and which hand |
| **[Skynet Harness](https://github.com/arupmmi07/skynet-harness)** | Ethan never spawns a coding agent itself; it calls `sky build`, and that is where the policy lives |

```bash
git clone https://github.com/arupmmi07/ethan.git
cd ethan
cp .env.example .env                       # fill in the keys
cp config/kb-map.example.json config/kb-map.json
./run.sh
```

Put the harness's `core/bin/sky` on your PATH, or set `sky.bin` in `config/ethan.json`,
or export `SKY_BIN`. Without it Ethan still starts and routes — it refuses at the point
of building and says which of the three to do, rather than failing somewhere less
obvious.

Without `config/kb-map.json` Ethan falls back to the shipped example and says so, so a
clean checkout runs. The router and the hand are given the same map either way. See
[docs/getting-started.md](docs/getting-started.md).

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | Doors, router, hands, harvest |
| [Getting started](docs/getting-started.md) | Keys, knowledge bases, first task |
| [Routing](docs/routing.md) | How a task chooses a knowledge base |
| [Contributing](CONTRIBUTING.md) | Running the tests, and what a change needs |


## Status

Working — **16 tests**, about 2,100 lines of Python. Standard library,
plus a routing model client. CI runs the suite on Python 3.11, 3.12 and 3.13.

Mid-session input is deliberately closed until there is a real boundary for it.

## Licence

Apache 2.0. See [LICENSE](LICENSE).
