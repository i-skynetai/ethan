#!/usr/bin/env bash
# Start Ultron. Reads .env beside this script.
cd "$(dirname "$0")"
exec python3 -m ethan.main "$@"
