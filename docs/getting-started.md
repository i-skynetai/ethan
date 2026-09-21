# Getting started

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

## 3. Run

```bash
./run.sh
```

The console door comes up on `http://localhost:8787`. Telegram attaches if a bot token
is present; without one, the console still runs.

## 4. Give it a task

```
work on PROJ-412
```

Ethan routes it to a knowledge base, calls `sky build` with a role, and reports back
when the run ends. It does not stream the run — mid-session input is deliberately
closed until there is a real boundary for it.

## What it will not do

- Push, merge, or comment on a ticket. Outward actions belong to the harness's broker
  and to you.
- Act without a door. There is no scheduler and no unattended mode.
- File a personal-door result into a work knowledge base.
