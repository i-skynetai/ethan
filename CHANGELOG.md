# Changelog

Every release, newest first. Versions follow [semantic versioning](https://semver.org).
IDs refer to rows in the [roadmap](ROADMAP.md).

## 0.1.0 — 2026-10-01

The first release.

### Added

- `./run.sh --demo`: one ask through routing, launch, close-out and the ledger, with no
  key, no server and no account. `demo/fake-sky` stands in for the harness.
- A KB can be a folder of Markdown notes (`"folder"` in the KB map), searched and
  written with no server.
- `ETHAN_STATE_DIR` and `ETHAN_KB_MAP` move the ledger and the KB map; the demo and the
  tests use them so they never touch a real ledger.
- `tools/render-terminal.py` turns a command's real output into the picture in the README.

### Known open

- EH-007: the shipped `config/doors.json` lets every door write to every privacy class,
  so the privacy wall is off until you narrow it.

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
