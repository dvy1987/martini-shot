#!/usr/bin/env python
"""Regenerate docs/harness/manifest.json with fresh sha256 hashes (harness v0).

Deterministic scaffold: run after intentional harness edits, with owner
approval (governance: manifest statuses may not be edited by evolve agents).
Usage: python docs/harness/gen_manifest.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

COMPONENTS = [
    ("prompt", "AGENTS.md", "generated"),
    ("tools", "docs/harness/tools.md", "generated"),
    ("middleware", "docs/harness/middleware.md", "generated"),
    ("skills", ".agents/ROUTING.md", "user-edited"),
    ("sub-agents", "docs/plans/2026-08-26-post-command-plan.md", "user-edited"),
    ("memory", "docs/memory/MEMORY-ROUTING.md", "user-edited"),
    ("governance", "docs/harness/governance.md", "generated"),
    ("verification", "docs/harness/eval-interface.md", "generated"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = {
        "harness_version": "v0",
        "created": datetime.now(tz=timezone.utc).date().isoformat(),
        "components": [
            {
                "id": cid,
                "path": path,
                "status": status,
                "sha256": sha256(ROOT / path),
                "allowed_write": status == "generated",
                "written_by": "harness-generation v0",
            }
            for cid, path, status in COMPONENTS
        ],
        "eval_interface": "docs/harness/eval-interface.md",
        "held_out_split": "docs/harness/tasks.json (split=held-out)",
        "allowed_write_paths": [
            "backend/**",
            "frontend/src/**",
            "scripts/**",
            "tests/**",
            "docs/adr/",
            "docs/harness/runs/",
            "docs/memory/",
        ],
        "notes": (
            "Drift CI: make harness-check (or python docs/harness/drift_check.py). "
            "Drift on generated components -> non-zero exit (no silent overwrite). "
            "User-edited components are flagged and skipped on regeneration."
        ),
    }
    out = HERE / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(manifest['components'])} components)")


if __name__ == "__main__":
    main()
