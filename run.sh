#!/usr/bin/env bash
# Start Ethan. Reads .env beside this script. `./run.sh --demo` needs no .env at all.
cd "$(dirname "$0")"
exec python3 -m ethan.main "$@"
