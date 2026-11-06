#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
URL="https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading $URL"
curl -fsSL "$URL" -o "$TMP/forskrifter.tar.bz2"

export SOURCE_URL="$URL"

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
"${PYTHON:-python3}" "$ROOT/tools/regulations/convert_to_markdown.py" "$@"
