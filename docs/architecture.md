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

![One task end to end — from the ask, through routing and context, to a build and a
review by two different agents](images/task-flow.png)

## Doors

A door is a way in. Telegram, a local console on `:8787`, and the CLI. Each door
carries a privacy class — a personal door cannot file into a work knowledge base.

## Router

Two stages, cheapest first:

1. **Hints.** Each knowledge base lists prefixes and keywords, matched whatever the
   case. When exactly one KB's hint matches and the ask's first word names the work
   (`review PROJ-412`, `fix PROJ-9`), that decides it. No model call.
2. **A small model.** Otherwise: two KBs matched, none did, or the kind of work is not
   clear. It sees each KB's stated `purpose` — only the matching KBs, when two matched —
   the ask, and whether an earlier result exists. Nothing else: no conversation, no
   earlier output. It uses its own low-privilege credential, which is why
   it never sees the tokens the hand will use.

## Knowledge base map

`config/kb-map.json`. One entry per KB: `purpose` (the routing signal), `mcp_url`,
`tenant_code`, `privacy`, `pat_env`, `hints`, `repos`. A KB with `folder` instead is a
directory of Markdown notes on this machine, searched and written with no server; the
demo's KB is one.

Working directory comes from the caller, not from the KB's repo list. A task started
in a directory works on that directory.

## The hand

Ethan does not spawn `claude` or `codex` directly. It calls `sky build --json` and
reads the structured result.

Spawning directly was built first and rejected on review: the child inherited every
secret in the environment, and no role policy applied to it. Going through the harness
means one place decides what a run may do.

![Ethan stays thin — the doors and the hands are the parts that
grow](images/shape.png)

## Harvest

After the run exits — not during. The result is redacted, then filed into the knowledge
base the task resolved to.

Redaction **refuses** rather than scrubs. A document containing something that looks
like a credential is not quietly cleaned and stored; it is rejected and reported. A
silent scrub hides the near-miss, and the near-miss is the thing worth knowing about.

## Ledger

SQLite. Task, door, route decision, hand, outcome, timing. It is the answer to "what
did it actually do" — separate from whatever the transcript says.

## Closing a session

![Closing a session: the hand proposes what is worth keeping, and Ethan checks that
proposal against policy](images/closeout.png)

Ethan holds no opinion about what matters. The hand that did the work proposes what is
worth keeping; Ethan's only judgement is whether that knowledge base exists, is
writable, and matches the privacy class of the door the ask came through.
