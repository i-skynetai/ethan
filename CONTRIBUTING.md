# Contributing

## Run the checks

```bash
python3 -m unittest discover -s tests -t .
./run.sh --demo
ruff check --select E9,F .
```

183 tests, standard library only — the same command CI runs, and CI runs the same ruff
check (syntax errors, undefined and unused names). All three must pass. The demo
needs no key; if it stops printing `Session can close`, something on the main path broke.

## The evals

`tests/test_evals.py` runs with the suite. It is not more unit tests: each scenario is a
short story — a reminder set, a watch answered, a relay pending — and a score that must
hold (every reminder within one tick, one task per reported item, nothing sent without a
yes). A feature that changes behaviour adds a scenario there, and a change that lowers a
score does not merge.

## Claim a feature before you start

[ROADMAP.md](ROADMAP.md) is the only list of planned work. Every feature, known bug and
fix is a row with an ID, a priority, a size, a status and an owner.

1. Pick a `Ready` row. New here? Take one marked *good first issue*.
2. Open an issue with the *Claim a feature* template, naming the ID.
3. In your first pull request, set the row to `In progress` with your handle and the date.
4. When the pull request is ready, set it to `In review`. A maintainer sets it to
   `Done` with the version when it merges.

One feature per person at a time. A large (L) feature starts from
[the design template](docs/features/TEMPLATE.md). An idea that is not a row does not
exist yet: propose it with the *Propose a feature* template.

## What a change needs

- A test that fails without it.
- A recorded reason for anything the change makes impossible.
- No new runtime dependency beyond the standard library and the routing model client.

## Documentation

The README follows one order: title and badges, a plain description, a picture in the
first 25 lines, the problem, the words you need, a sixty-second demo with a picture of
its real output, numbered steps, a run diagram, features, what it is not, status, links
and licence. At most 900 words; counts and versions exact; dates absolute.

Pictures are PNG on the page, with the SVG source beside them in `docs/images`, and you
open the PNG and look at it before committing. A terminal picture shows real output:
regenerate it with `tools/render-terminal.py`. Diagram source code (for example Mermaid)
goes only under a "Diagram sources" appendix. Every README claim has a test.

## What will be refused

- Ethan spawning a coding agent directly instead of going through `sky build`.
- Silent redaction. If harvest finds something that looks like a credential it refuses
  and reports; it does not quietly clean and store.
- A close-out path that can end a run without saying what happened.
- The router being given a credential that can do more than route, or more context than
  the KB purposes and the ask.
