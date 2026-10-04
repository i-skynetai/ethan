# Changelog

Every release, newest first. Versions follow [semantic versioning](https://semver.org).
IDs refer to rows in the [roadmap](ROADMAP.md).

## Unreleased

### Added

- EH-068: an eval suite, `tests/test_evals.py`, for the four promises: on time, no
  double nag, nothing important missed, nothing sent without a yes. It runs in CI.

- EH-050: `pip install .` gives `ethan` and `ethan-service`. An installed copy keeps
  config in the user's config folder, seeded from shipped defaults, and the ledger in
  the user's data folder; `ETHAN_CONFIG_DIR` and `ETHAN_STATE_DIR` move them. CI
  installs the package and runs both commands.

- EH-062: reaching you. Everything lands in the asking conversation; it also goes to
  your phone (Telegram) when marked urgent, or when you are away and it is not quiet
  hours. Every attempt is recorded with its reason. No call: that is EH-070.

- EH-063: watch a source through a session's own connectors. "Watch mail through the
  claude session ethan every weekday at 09:00: what must I reply to?" asks on schedule,
  review-only, with a fixed answer shape; each item becomes a task once. Ethan holds no
  connector and sends nothing from the source.

- EH-065: one task list. "Add task: … by Friday", "my tasks", "done #N", "snooze task
  #N until …", "drop task #N", by rule with no model. Tasks carry their source and a
  link back; the same item from one source is merged; done touches only the list.

- EH-061: reminders and recurring checks on Ethan's own clock. "Remind me at 15:00 to
  …", "in 20 minutes", "tomorrow at 9", "every weekday at 09:00, …". Each is a ledger
  row that survives a restart; one that came due while Ethan was stopped is told as
  missed, not run late. A scheduled ask runs through the `clock` door, which may remind
  and read but is refused a build. "My reminders" lists, "cancel reminder #N" drops.

- EH-059: a relay is followed to its end. Every change of state is told to the
  conversation that asked; a completed relay delivers the answer there, a failed one
  says why. After a restart, a relay the bridge accepted but Ethan did not record is
  recovered by its dedupe key, never sent twice. The close-out line counts unanswered
  relays. `ethan --status` and `/api/state` list relays.
- EH-023: "what is running?" is answered from the ledger: running tasks, the last five
  finished ones and unanswered relays, with no model call beyond routing. The console's
  `status` shortcut gives the same answer.

- `docs/vision.md`: where Ethan is going. It is an assistant that hands the work to
  Claude and Codex and keeps the clock, the reach, the rules and the record. New
  roadmap rows EH-061 to EH-069 cover it. They are Proposed or Needs decision.

- EH-058: relay an ask to a coding session that is already running, through a local
  message bridge. A rule decides, before any model call, and a relay never starts a
  hand. If no registered session matches, Ethan sends nothing; if several match,
  Ethan asks which one. Relays are review-only unless the ask says to implement.
  Each relay is recorded with its bridge message id and state, and the reply says
  what that state means. Only the console and the CLI may relay.

- EH-057: minimal mask-like character scene. Conversation and agents/context open
  on demand and close with Escape or their close button. New console replies show
  an update card while the conversation is closed. This is in-page notification,
  not a background scheduler or operating-system notification service.
  The visual system uses near-black surfaces, lavender panels and mint accents,
  a centred character, a bottom tool dock, and compact floating updates. Shared
  styles cover the conversation and context panels, with responsive sizing and
  reduced-motion support.

- EH-056: calm, practical assistant voice for model-backed chat and a subtle
  presence indicator driven by active requests and pending tasks. No idle animation
  or invented background thinking; reduced-motion preferences are respected.

- EH-055: conversation-first local console, durable user/reply history, and a
  read-only list of registered Claude and Codex sessions from agent-bridge.
  Registry status is labelled as last recorded, not live availability. Help,
  status and session-list requests need no model key. Run logs remain under
  technical details. Messaging the sessions came later, in EH-058.

### Fixed

- `bin/ethan` with a reused `--chat` printed the conversation's earlier replies before
  the new ones; it now starts from the end of the queue at the moment of the ask.

- EH-051 (in progress): Ethan runs on Windows. A Python `sky` script, such as core's
  `bin/sky` or `demo/fake-sky`, is started through the Python interpreter, and an
  extensionless `sky` on `PATH` is found. A hung `sky build` is stopped with
  `taskkill /T` in its own process group instead of a Unix group kill. `sky build` also
  inherits the Windows variables a process needs to start (`SYSTEMROOT`, `TEMP`,
  `USERPROFILE` and similar; no secrets). Run logs, the KB map, `.env`, config and
  transcripts are read and written as UTF-8 whatever the system's code page. The two
  tests that run a `#!/bin/sh` fake `sky` are skipped on Windows.

## 0.1.0 — 2026-10-01

The first release.

### Added

- `./run.sh --demo`: one ask through routing, launch, close-out and the ledger, with no
  key, no server and no account. `demo/fake-sky` stands in for the harness.
- A KB can be a folder of Markdown notes (`"folder"` in the KB map), searched and
  written with no server.
- `ETHAN_STATE_DIR` and `ETHAN_KB_MAP` move the ledger and the KB map; the demo and the
  tests use them so they never touch a real ledger.
- CI runs `ruff check --select E9,F` beside the tests.
- `tools/render-terminal.py` turns a command's real output into the picture in the README.

### Fixed

- EH-001: a hint decides the route with no model call when the ask's first word names the
  work; hints match whatever the case; when two KBs match, the model chooses between
  only those two.
- EH-002: a KB the router did not choose is never used. An unknown KB gets a reply
  saying so, and nothing is searched or filed under another KB.
- EH-003: the routing call carries one system message with the KB purposes and the ask,
  nothing else. Each ask is stored once, whatever the door.
- EH-004: each chain step carries its kind, so a build step runs as `developer` and a
  review step as `reviewer`; the close-out after a chain names the last step's task.
- EH-005: the console refuses a POST from another web page (403), a body that is not JSON
  (415) and a body over 64 KB (413).
- EH-006: `ethan --ingest` picks the KB from the folder the file is in, never from the
  directory the command was run in.
- EH-007: the privacy wall is on by default. Telegram may file only into personal KBs;
  the console and the CLI may file into any. The CLI is now a door of its own, `cli`,
  and every task row records the door it came through.
- EH-008: every ask ends with exactly one close-out line — after an answer, a failed
  task or an error — so `bin/ethan` returns as soon as the work is done, and an error on
  the Telegram door is reported to the sender.
- EH-009: the ontology validator prints its usage with no arguments and names PyYAML
  when it is missing, instead of stopping with a `NameError`.
- EH-010: no private names or home-folder paths in the repository or its history; a
  test now fails on any absolute home-folder path. `tools/extract-model.sh`, which
  drove one private server, is removed.
- The router and the hand read the same KB map file; a clean checkout no longer hands
  `sky` a path to a file it does not have.
- A console port already in use stops Ethan with a message, instead of leaving a
  process with no door open.
- Status and inbox asks reply with what exists today instead of promising a version.
- Tests close every file and database they open.
