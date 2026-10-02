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

## Privacy classes

Each door and each knowledge base carries a class: `personal` or `work`. A task that
arrived through a personal door cannot file into a work knowledge base.

This is checked at harvest, not at routing, because the class that matters is the one
in force when something is written.
