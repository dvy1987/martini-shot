"""Firestore state wrapper (plan A-2, C-6.2). Real database only (C-1.1) —
the lease queue (A-3) builds on transactions; this module stays thin.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.cloud import firestore

from backend.core.config import Settings


class FirestoreStore:
    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def set_doc(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        self._client.collection(collection).document(doc_id).set(data)

    def get_doc(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snap = self._client.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None  # type: ignore[union-attr]

    def delete_doc(self, collection: str, doc_id: str) -> None:
        self._client.collection(collection).document(doc_id).delete()

    def new_doc_id(self, collection: str) -> str:
        return self._client.collection(collection).document().id

    def list_where(
        self, collection: str, field: str, value: object
    ) -> list[dict[str, Any]]:
        """Real query with doc ids embedded under 'id' (test/ops helper)."""
        out: list[dict[str, Any]] = []
        for snap in (
            self._client.collection(collection).where(field, "==", value).stream()
        ):
            data = snap.to_dict() or {}
            data["id"] = snap.id
            out.append(data)
        return out

    def transactional_update(
        self,
        collection: str,
        doc_id: str,
        mutate: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Compare-and-set inside a Firestore transaction: read the doc, apply
        the pure `mutate` to it, write the result back. If the doc changes
        between read and write the transaction retries — the last-committed
        write always wins and stale full-document overwrites are impossible.
        Used by the lease queue, intake pause flags and the approval machine."""
        client = self._client
        ref = client.collection(collection).document(doc_id)

        @firestore.transactional
        def _tx(tx: firestore.Transaction) -> None:
            snap = ref.get(transaction=tx)
            doc = snap.to_dict() or {} if snap.exists else {}
            tx.set(ref, mutate(doc), merge=True)

        _tx(client.transaction())

    @property
    def client(self) -> firestore.Client:
        return self._client


def get_firestore(settings: Settings) -> FirestoreStore:
    client = firestore.Client(
        project=settings.gcp_project_id,
        database=settings.firestore_database or "(default)",
    )
    return FirestoreStore(client)
