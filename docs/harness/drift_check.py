#!/usr/bin/env python
"""Harness manifest drift check (harnessforge pattern, v0).

Compares each component's recorded sha256 in manifest.json against disk:
- status user-edited + drift  -> flag, skip (never overwrite user work)
- status generated + drift    -> exit 1 (require explicit --force decision by owner)
Run via `make harness-check` or CI. Read-only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not MANIFEST.exists():
        print("manifest.json missing — regenerate harness v0", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    drifted: list[str] = []
    for comp in manifest.get("components", []):
        path = HERE.parents[1] / comp["path"]
        if not path.exists():
            drifted.append(f"{comp['id']}: MISSING {comp['path']}")
            continue
        if sha256(path) != comp.get("sha256"):
            if comp.get("status") == "user-edited":
                print(f"drift (user-edited, skipping): {comp['path']}")
            else:
                drifted.append(
                    f"{comp['id']}: changed {comp['path']} (status={comp.get('status')})"
                )
    if drifted:
        print("harness drift detected:")
        print("\n".join(drifted))
        print(
            "resolve with owner approval: regenerate via harness-generation --force or update manifest"
        )
        return 1
    print(
        f"harness v{manifest.get('harness_version', '?')}: no drift across "
        f"{len(manifest.get('components', []))} components"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
