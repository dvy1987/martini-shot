"""SHA-256 of ingested bytes (G1 arrival+checksum; D-1 will add probe)."""

from __future__ import annotations

import hashlib


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
