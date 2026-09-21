# Routing

How a task chooses a knowledge base — and why it is two stages.

## Hints first

Each knowledge base declares hints:

```json
"hints": ["PROJ-", "billing", "invoice"]
```

A task naming `PROJ-412` matches, and no model is called. Most tasks resolve here.
It is free, deterministic, and explainable.

## The small model second

When hints are ambiguous — two KBs match, or none do — a small model decides. It sees:

- each knowledge base's `purpose` string
- the ask

Nothing else. Not the repository, not the ledger, not your files.

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

The task gets **no** knowledge base and a message saying so.

It does not fall back to a default. A repository under a client knowledge base never
falls back to a work one — answering from the wrong knowledge base is worse than
answering from none, and much harder to notice.

## Privacy classes

Each door and each knowledge base carries a class: `personal` or `work`. A task that
arrived through a personal door cannot file into a work knowledge base.

This is checked at harvest, not at routing, because the class that matters is the one
in force when something is written.
