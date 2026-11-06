#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$ROOT/tools/laws/update.sh" &
laws_pid=$!
"$ROOT/tools/regulations/update.sh" &
regulations_pid=$!

status=0
wait "$laws_pid" || status=1
wait "$regulations_pid" || status=1

exit "$status"
