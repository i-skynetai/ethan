# Getting started

## 0. Try the demo first

```bash
./run.sh --demo
```

No key, no server, no harness. It runs one ask through routing, launch and close-out
against a sample shop and a folder KB, using `demo/fake-sky` in place of the harness.

## 1. Keys

```bash
cp .env.example .env
```

| Key | What it is |
|---|---|
| `OPENAI_API_KEY` | Routing only — Ethan's own small thinking. Give it a low-privilege key. |
| `OPENAI_MODEL` | Any chat model that key can use. A small one is correct here. |
| `TELEGRAM_BOT_TOKEN` | Optional. Only if you want the Telegram door. |
| `TELEGRAM_ALLOWED_USER_IDS` | Your Telegram user id. Nobody else can talk to it. |
| `KB_*_PAT` | One token per knowledge base, named by that KB's `pat_env`. |

Tokens live in `.env`, never in `kb-map.json`.

## 2. Knowledge bases

```bash
cp config/kb-map.example.json config/kb-map.json
```

Each entry needs a `purpose` — one specific sentence. This is the routing signal, so
"our billing platform, invoices, payment providers and dunning" routes well and
"work stuff" does not.

Without `kb-map.json` Ethan falls back to the example and logs that it did, so a clean
checkout runs. It will not route usefully until you fill it in.

A KB can also be a folder of Markdown notes on this machine — `"folder": "~/notes"`
in place of `mcp_url`, `tenant_code` and `pat_env`. See `demo/kb-map.json`.

## 3. Run

Either from the checkout, or installed:

```bash
pip install .
ethan-service            # the service; `ethan` is the command
```

Installed, Ethan keeps its config in your config folder (`%APPDATA%\ethan` on Windows,
`~/.config/ethan` elsewhere; seeded from the shipped defaults on first start, and
`ETHAN_CONFIG_DIR` moves it) and its ledger in your data folder (`%LOCALAPPDATA%\ethan`
or `~/.local/share/ethan`; `ETHAN_STATE_DIR` moves it). Put `.env` in the config folder.
From a checkout:

```bash
./run.sh
```

The console door comes up on `http://localhost:8787`. Telegram attaches if a bot token
is present; without one, the console still runs. If the port is taken and Telegram is
off, Ethan says so and stops; set `ETHAN_CONSOLE_PORT` to a free port.

## 4. Give it a task

```bash
bin/ethan "review PROJ-412"
```

A hint plus a first word that names the work decides the route with no model call.
Ethan routes it to a knowledge base, calls `sky build` with a role, and reports back
when the run ends. It does not stream the run — mid-session input is deliberately
closed until there is a real boundary for it.

## 5. Hand an ask to a session that is already open

Set `ETHAN_BRIDGE_DIR` in `.env` to a checkout of the local message bridge
(`agent-bridge`). Then, from the console or the command line:

```bash
bin/ethan "ask the codex session codex-ethan to review the open merge request"
```

Ethan passes the ask on, reports the bridge's message id, and follows it until the
session answers. Without `ETHAN_BRIDGE_DIR`, Ethan says it cannot reach a running
session and sends nothing. See [Routing](routing.md#passing-an-ask-to-a-running-session).

## 6. Set a reminder

```bash
bin/ethan --chat me "remind me at 15:00 to send the report"
bin/ethan --chat me "every weekday at 09:00, what is running?"
```

The reminder lands in that conversation at the time. A scheduled ask may only read:
a status ask, a question or a review-only relay. `bin/ethan --status` lists what is
scheduled. See [Routing](routing.md#reminders-and-checks-on-ethans-own-clock).

## 7. Keep one task list

```bash
bin/ethan --chat me "add task: send the report by friday"
bin/ethan --chat me "what should I do now?"
bin/ethan --chat me "done #1"
```

Tasks from reminders, meetings and watches land in the same list. See
[Routing](routing.md#one-task-list).

## 8. Watch a source

```bash
bin/ethan --chat me "watch mail through the claude session ethan every weekday at 09:00: what must I reply to?"
```

Every weekday at 09:00 Ethan asks that session (review-only) and turns each item it
reports into a task. The session reads your mail through its own connector; Ethan
never holds the credential. See [Routing](routing.md#watching-a-source-through-a-session).

## What it will not do

- Push, merge, or comment on a ticket. Outward actions belong to the harness's broker
  and to you.
- Act on its own, with one exception: the reminders and read-only checks you set on
  its clock. It never starts a hand unattended.
- File a result into a KB whose privacy class the door does not list in
  `config/doors.json`. As shipped, Telegram may file only into `personal` KBs; the
  console and the `ethan` command (the `cli` door) may file into any class.
