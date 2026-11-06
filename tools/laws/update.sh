#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
URL="https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading $URL"
curl -fsSL "$URL" -o "$TMP/lover.tar.bz2"

export SOURCE_URL="$URL"

echo "Extracting"
tar -xjf "$TMP/lover.tar.bz2" -C "$TMP"
if [[ ! -d "$TMP/nl" ]]; then
  echo "error: tarball did not contain nl/" >&2
  exit 1
fi

rm -rf "$ROOT/nl"
mv "$TMP/nl" "$ROOT/nl"

echo "Converting laws"
"${PYTHON:-python3}" "$ROOT/tools/laws/convert_to_markdown.py"
