"""Handoff Validator, silent mode (spec S0b, plan A-5, AC-S0b.1).

Runs inside the spine at every station transition: verifies a turnover
manifest (v1 JSON: files with ref/sha256/bytes) against the actually
delivered files, plus the ingest scene bag (ingested / spoken_words / scene)
after the ingest look. Discrepancies try a repair first (restore lost
metadata from the shot, or run the ingest look if it never happened), then
block if still broken. Every outcome carries an orchestrator_note.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.firestore import FirestoreStore
from backend.jobs.models import utc_now_iso

ANNOTATION_COLLECTION = "pc-annotations"


@dataclass
class HandoffResult:
    passed: bool
    codes: list[str] = field(default_factory=list)
    blocked_files: list[str] = field(default_factory=list)
    annotation_id: str | None = None
    repaired: bool = False
    repaired_scene: dict[str, Any] | None = None
    orchestrator_note: str = ""
    blocked_scene: bool = False


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scene_sha256(bag: dict[str, Any]) -> str:
    canonical = {
        "ingested": bool(bag.get("ingested")),
        "spoken_words": str(bag.get("spoken_words") or ""),
        "scene": str(bag.get("scene") or ""),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def scene_bag_for_manifest(meta: dict[str, Any] | None) -> dict[str, Any]:
    from backend.supervisor.station_agents.ingest_understand import scene_bag

    bag = scene_bag(meta)
    out = {
        "ingested": bag["ingested"],
        "spoken_words": bag["spoken_words"],
        "scene": bag["scene"],
    }
    out["sha256"] = scene_sha256(out)
    return out


def turnover_manifest(
    *,
    project_id: str,
    from_station: str,
    to_station: str,
    files: list[dict[str, Any]],
    scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "version": 1,
        "project_id": project_id,
        "from_station": from_station,
        "to_station": to_station,
        "files": list(files),
    }
    if scene is not None:
        doc["scene"] = scene_bag_for_manifest(scene)
    return doc


def _codes_and_blocks(
    manifest: dict[str, Any], delivered: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    codes: list[str] = []
    blocked: list[str] = []
    if (
        not isinstance(manifest, dict)
        or manifest.get("version") != 1
        or not isinstance(manifest.get("files"), list)
    ):
        return ["MANIFEST_INVALID"], []

    expected: list[dict[str, Any]] = manifest["files"]
    delivered_by_ref = {
        d.get("ref"): d for d in delivered if isinstance(d, dict) and d.get("ref")
    }

    if len(expected) != len(delivered):
        codes.append("COUNT_MISMATCH")

    for entry in expected:
        ref = entry.get("ref")
        if not ref or ref not in delivered_by_ref:
            codes.append("MISSING_FILE")
            blocked.append(str(ref))
            continue
        got = delivered_by_ref[ref]
        expected_sha = entry.get("sha256")
        got_sha = got.get("sha256")
        if expected_sha and got_sha and expected_sha != got_sha:
            codes.append("CHECKSUM_MISMATCH")
            blocked.append(str(ref))
    return codes, blocked


def _scene_codes(
    manifest: dict[str, Any],
    *,
    require_scene: bool,
    delivered_scene: dict[str, Any] | None,
) -> list[str]:
    if not require_scene and not isinstance(manifest.get("scene"), dict):
        return []
    scene = manifest.get("scene")
    if require_scene and not isinstance(scene, dict):
        return ["SCENE_MISSING"]
    if not isinstance(scene, dict):
        return []
    if not delivered_scene:
        return ["SCENE_MISSING"]
    expected = scene_bag_for_manifest(scene)
    got = scene_bag_for_manifest(delivered_scene)
    if expected["sha256"] != got["sha256"]:
        return ["SCENE_MISMATCH"]
    if require_scene and not got.get("ingested"):
        return ["SCENE_MISSING"]
    return []


def _blocked_note(codes: list[str]) -> str:
    if "SCENE_MISSING" in codes:
        return (
            "Ingest look never happened and scene metadata could not be "
            "restored. Block this station until ingest watches the original "
            "and writes spoken words plus a scene description."
        )
    if "SCENE_MISMATCH" in codes:
        return (
            "Scene metadata on the handoff does not match the delivered bag "
            "and could not be reconciled from the shot. Do not invent a "
            "different script or description."
        )
    if codes:
        return (
            "Media files failed the handoff check "
            f"({', '.join(codes)}). Do not proceed; the clip bytes are not "
            "the ones ingest registered."
        )
    return ""


class HandoffValidator:
    def __init__(self, store: FirestoreStore | None = None) -> None:
        self._store = store

    @classmethod
    def without_store(cls) -> HandoffValidator:
        """Pure gate for unit contexts (no annotation persistence)."""
        return cls(store=None)

    def validate(
        self,
        manifest: dict[str, Any],
        delivered: list[dict[str, Any]],
        *,
        job_id: str,
        require_scene: bool = False,
        delivered_scene: dict[str, Any] | None = None,
        shot_id: str = "",
        store: Any | None = None,
        settings: Any | None = None,
        payload: bytes | None = None,
        media: Any | None = None,
        watch: Any | None = None,
    ) -> HandoffResult:
        codes, blocked = _codes_and_blocks(manifest, delivered)
        scene_codes = _scene_codes(
            manifest, require_scene=require_scene, delivered_scene=delivered_scene
        )
        codes.extend(scene_codes)
        store = store if store is not None else self._store
        repaired = False
        repaired_scene: dict[str, Any] | None = None
        note = ""
        if any(code in codes for code in ("SCENE_MISSING", "SCENE_MISMATCH")):
            repaired_scene, note, repaired = self._repair_scene(
                shot_id=shot_id,
                store=store,
                expected=manifest.get("scene")
                if isinstance(manifest.get("scene"), dict)
                else None,
                settings=settings,
                payload=payload,
                media=media,
                watch=watch,
            )
            if repaired and repaired_scene is not None:
                codes = [
                    code
                    for code in codes
                    if code not in {"SCENE_MISSING", "SCENE_MISMATCH"}
                ]
        if not note:
            note = _blocked_note(codes)
        result = HandoffResult(
            passed=not codes,
            codes=codes,
            blocked_files=blocked,
            repaired=repaired,
            repaired_scene=repaired_scene,
            orchestrator_note=note,
            blocked_scene=any(
                code in codes for code in ("SCENE_MISSING", "SCENE_MISMATCH")
            ),
        )
        if not result.passed or result.repaired:
            result.annotation_id = self._annotate(manifest, job_id, result)
        return result

    def _repair_scene(
        self,
        *,
        shot_id: str,
        store: Any,
        expected: dict[str, Any] | None,
        settings: Any | None,
        payload: bytes | None,
        media: Any | None,
        watch: Any | None,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        from backend.supervisor.station_agents.ingest_understand import (
            ensure_scene_understanding,
            scene_understanding_from_shot,
        )

        if store is None or not shot_id or not hasattr(store, "get_doc"):
            return (
                None,
                (
                    "Scene metadata is missing from the handoff and there is "
                    "no shot to restore it from. Ingest look may not have run."
                ),
                False,
            )
        existing = scene_understanding_from_shot(store, shot_id)
        if isinstance(existing, dict) and existing.get("ingested"):
            bag = scene_bag_for_manifest(existing)
            if expected and scene_sha256(expected) != scene_sha256(bag):
                return (
                    bag,
                    (
                        "Handoff scene bag drifted from the shot. Restored "
                        "spoken words and scene description from the ingest "
                        "look already on the shot."
                    ),
                    True,
                )
            return (
                bag,
                (
                    "Scene metadata was missing from the handoff payload "
                    "(lost in transit). Restored ingested/script/scene from "
                    "the shot."
                ),
                True,
            )
        if payload is not None and media is not None:
            try:
                bag = ensure_scene_understanding(
                    store,
                    shot_id,
                    settings=settings,
                    payload=payload,
                    media=media,
                    watch=watch,
                )
            except Exception as exc:
                return (
                    None,
                    (
                        "Ingest look never happened. Attempted to watch the "
                        f"original and failed ({type(exc).__name__}). Block "
                        "until ingest can see the clip."
                    ),
                    False,
                )
            if bag.get("ingested"):
                return (
                    scene_bag_for_manifest(bag),
                    (
                        "Ingest look had not run. Ran ingest understand now "
                        "and wrote spoken words and scene description onto "
                        "the shot."
                    ),
                    True,
                )
        return (
            None,
            (
                "Ingest look never happened. No scene description or script "
                "on the shot, and the original clip was not available to watch."
            ),
            False,
        )

    def _annotate(
        self, manifest: dict[str, Any], job_id: str, result: HandoffResult
    ) -> str | None:
        if self._store is None or not hasattr(self._store, "set_doc"):
            return None
        kind = (
            "handoff.repaired"
            if result.passed and result.repaired
            else "handoff.blocked"
        )
        doc_id = f"ann-{job_id}-{utc_now_iso().replace(':', '')}"
        self._store.set_doc(
            ANNOTATION_COLLECTION,
            doc_id,
            {
                "type": kind,
                "job_id": job_id,
                "project_id": manifest.get("project_id", ""),
                "from_station": manifest.get("from_station", ""),
                "to_station": manifest.get("to_station", ""),
                "codes": result.codes,
                "blocked_files": result.blocked_files,
                "blocked_scene": result.blocked_scene,
                "repaired": result.repaired,
                "orchestrator_note": result.orchestrator_note,
                "at": utc_now_iso(),
            },
        )
        return doc_id
