# Architecture

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Telegram │  │ console  │  │   CLI    │        doors
└────┬─────┘  └────┬─────┘  └────┬─────┘
     └─────────────┼─────────────┘
                   ▼
            ┌─────────────┐
            │   router    │   hints first; a small model only when ambiguous
            └──────┬──────┘
                   ▼
        ┌──────────────────────┐
        │  knowledge base map  │   which KB owns this task?
        └──────────┬───────────┘
                   ▼
            ┌─────────────┐
            │  sky build  │   role, tool allowlist, human gate
            └──────┬──────┘
                   ▼
            ┌─────────────┐
            │  the hand   │   Claude · Codex · Kimi
            └──────┬──────┘
                   ▼
            ┌─────────────┐
            │   harvest   │   redact, then file back into the KB
            └──────┬──────┘
                   ▼
            ┌─────────────┐
            │   ledger    │   SQLite: task, route, outcome
            └─────────────┘
```

## Doors

A door is a way in. Telegram, a local console on `:8787`, and the CLI. Each door
carries a privacy class — a personal door cannot file into a work knowledge base.

## Router

Two stages, cheapest first:

1. **Hints.** Each knowledge base lists prefixes and keywords. A task naming `PROJ-412`
   goes to whichever KB claims that prefix. No model call.
2. **A small model.** Only when hints are ambiguous. It sees each KB's stated `purpose`
   and the ask — nothing else. It uses its own low-privilege credential, which is why
   it never sees the tokens the hand will use.

## Knowledge base map

`config/kb-map.json`. One entry per KB: `purpose` (the routing signal), `mcp_url`,
`tenant_code`, `privacy`, `pat_env`, `hints`, `repos`.

Working directory comes from the caller, not from the KB's repo list. A task started
in a directory works on that directory.

## The hand

Ethan does not spawn `claude` or `codex` directly. It calls `sky build --json` and
reads the structured result.

Spawning directly was built first and rejected on review: the child inherited every
secret in the environment, and no role policy applied to it. Going through the harness
means one place decides what a run may do.

## Harvest

After the run exits — not during. The result is redacted, then filed into the knowledge
base the task resolved to.

Redaction **refuses** rather than scrubs. A document containing something that looks
like a credential is not quietly cleaned and stored; it is rejected and reported. A
silent scrub hides the near-miss, and the near-miss is the thing worth knowing about.

## Ledger

SQLite. Task, door, route decision, hand, outcome, timing. It is the answer to "what
did it actually do" — separate from whatever the transcript says.
