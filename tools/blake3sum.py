#!/usr/bin/env python3
"""Print BLAKE3 hashes for files, one "hash  path" line per file."""

from __future__ import annotations

import sys

from blake3 import blake3

CHUNK_SIZE = 1024 * 1024


def hash_file(path: str) -> str:
    digest = blake3()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    for path in sys.argv[1:]:
        print(f"{hash_file(path)}  {path}")


if __name__ == "__main__":
    main()
