# Contributing

```bash
python3 -m unittest discover -s tests -t .
```

Standard library only — the same command CI runs. They must pass.

## What a change needs

- A test that fails without it.
- A recorded reason for anything the change makes impossible.
- No new runtime dependency beyond the standard library and the routing model client.

## What will be refused

- Ethan spawning a coding agent directly instead of going through `sky build`.
- Silent redaction. If harvest finds something that looks like a credential it refuses
  and reports; it does not quietly clean and store.
- A close-out path that can end a run without saying what happened.
- The router being given a credential that can do more than route.
