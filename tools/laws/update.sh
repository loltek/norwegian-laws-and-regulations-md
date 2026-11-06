#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
URL="https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2"
CONVERTER="$ROOT/tools/laws/convert_to_markdown.py"
STATE="$ROOT/lover/dataset.json"

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
curl -fsSL "$URL" -o "$TMP/lover.tar.bz2"

HASH="$(b3sum "$TMP/lover.tar.bz2" | awk '{print $1}')"
CONVERTER_HASH="$(b3sum "$CONVERTER" | awk '{print $1}')"

if [[ "$FORCE" -eq 0 && ${#ARGS[@]} -eq 0 && -f "$STATE" && -f "$ROOT/lover/index.json" ]] \
  && compgen -G "$ROOT/lover/*.md" >/dev/null; then
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
tar -xjf "$TMP/lover.tar.bz2" -C "$TMP"
if [[ ! -d "$TMP/nl" ]]; then
  echo "error: tarball did not contain nl/" >&2
  exit 1
fi

rm -rf "$ROOT/nl"
mv "$TMP/nl" "$ROOT/nl"

echo "Converting laws"
"${PYTHON:-python3}" "$CONVERTER" "${ARGS[@]}"
