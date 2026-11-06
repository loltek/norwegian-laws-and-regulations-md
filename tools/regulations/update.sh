#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
URL="https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2"
CONVERTER="$ROOT/tools/regulations/convert_to_markdown.py"
STATE="$ROOT/forskrifter/dataset.json"

FORCE=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading $URL"
curl -fsSL "$URL" -o "$TMP/forskrifter.tar.bz2"

HASH="$("${PYTHON:-python3}" "$ROOT/tools/blake3sum.py" "$TMP/forskrifter.tar.bz2" | awk '{print $1}')"
CONVERTER_HASH="$("${PYTHON:-python3}" "$ROOT/tools/blake3sum.py" "$CONVERTER" | awk '{print $1}')"

if [[ "$FORCE" -eq 0 && ${#ARGS[@]} -eq 0 && -f "$STATE" && -f "$ROOT/forskrifter/index.json" ]] \
  && compgen -G "$ROOT/forskrifter/*.md" >/dev/null; then
  read -r PREV_HASH PREV_CONVERTER < <(
    python3 - "$STATE" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    data = {}
print(data.get("source_b3sum", ""), data.get("converter_b3sum", ""))
PY
  )
  if [[ "$HASH" == "$PREV_HASH" && "$CONVERTER_HASH" == "$PREV_CONVERTER" ]]; then
    echo "Source and converter unchanged (BLAKE3 $HASH); skipping conversion."
    exit 0
  fi
fi

export SOURCE_URL="$URL"
export SOURCE_B3SUM="$HASH"
export CONVERTER_B3SUM="$CONVERTER_HASH"

echo "Extracting"
tar -xjf "$TMP/forskrifter.tar.bz2" -C "$TMP"

rm -rf "$ROOT/src"
mkdir -p "$ROOT/src"
for dir in sf del ins stv; do
  if [[ -d "$TMP/$dir" ]]; then
    mv "$TMP/$dir" "$ROOT/src/"
  fi
done

if [[ ! -d "$ROOT/src/sf" ]]; then
  echo "error: tarball did not contain sf/" >&2
  exit 1
fi

echo "Converting regulations"
"${PYTHON:-python3}" "$CONVERTER" "${ARGS[@]}"
