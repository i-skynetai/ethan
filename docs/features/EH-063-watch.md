# EH-063 — Watch a source through a session's own connectors

**Status:** Done — 0.2.0 · **Owner:** Claude (ethan), 2026-10-04 · **Issue:** —

## What is missing today

Ethan cannot tell you that a mail needs an answer or that a ticket assigned to you
changed. It has no connector to mail, chat or tickets, and it should not grow one:
Claude and Codex already read those sources through their own connectors, and keeping
a second set of credentials in Ethan would widen what a small local service holds.
Today, "any new mail?" is classed `updates` and declined.

## What done looks like

- `watch mail through the claude session ethan every weekday at 09:00: what must I
  reply to?` stores a watch and a clock row; nothing is sent until the time.
- At the time, one review-only relay goes to that session with the question, "only
  items since <last run>", and a fixed answer shape; the relay is tagged with the watch.
- Each line of the answer in that shape becomes a task on the one list, with the watch's
  source, the link, why it matters and a due date when one can be read. The same item
  reported again is merged, not added twice.
- `- nothing` is told as "nothing new"; lines that do not fit the shape are shown and
  are not tasks; a failed answer is told and makes no tasks.
- A target no longer registered with the bridge skips the run and says so.
- `my watches` lists; `stop watch #N` ends one and cancels its clock row; tasks stay.
- Nothing is ever sent from the source: every watch relay is review-only.

## Design

`ethan/watch.py` holds the watches table and the three steps: `take` (the ask),
`run` (called by `clock.tick` for a clock row of kind `watch`) and `absorb` (called by
`relay._check` when a relay whose `purpose` is `watch:<id>` completes or fails). The
relay table gains a `purpose` column; `relay.dispatch` sends a tagged relay without a
door's `reply`. Tasks go through `todo.add`, which merges on source and link. Three
modules are reused, none changed in shape: the clock schedules, the relay carries, the
list keeps.

## What it does not do

- No connector in Ethan. The session reads the source; Ethan never holds its credential.
- No action on the source: no reply sent, no ticket changed, no mark-as-read.
- No model call in Ethan: the ask, the schedule and the answer are read by rules.
- No judgement of what matters: the session answers the question you wrote.

## How it is measured

`tests/test_watch.py`, with a fake bridge and a fake clock: one send per run, review-only,
the shape and the "since" in the text; two items → two tasks with link and due date;
the same answer again plus one new line → one new task, two merged; `- nothing`; a
failed answer; an unregistered target; list and stop. Live: one watch against the real
bridge and this Claude session, run from the console.
