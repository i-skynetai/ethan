---
name: Propose a feature
about: Something Ethan should do, or a door, knowledge base or hand it should reach, that is not on the roadmap
---

<!-- Check ROADMAP.md first: https://github.com/i-skynetai/ethan/blob/main/ROADMAP.md
If it is there, use "Claim a feature" instead. An accepted proposal gets an EH ID and a
row in ROADMAP.md. -->

**The ask you would send Ethan**, in one sentence — or the door, knowledge base or hand
it should reach.

**What it costs today** — what you do by hand instead: which knowledge base you pick,
which agent you start, what you copy between them.

**What done looks like** — the reply you expect, and what the ledger should record.

**What it must never do** — the line it must not cross: a secret it must not hold, a
knowledge base it must not write to, an action that needs your yes first.

A new door is one function that turns its input into `router.handle(chat_id, text,
reply, door=...)`; `ethan/door_telegram.py` is the smallest example.
