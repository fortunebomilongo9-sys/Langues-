"""Backends de stockage : Firestore REST (production) ou fichier JSON local.

Le backend Firestore utilise exclusivement l'API REST officielle et la clé
publique Web de Firebase côté serveur : aucune dépendance binaire lourde, donc
compatible avec une image Alpine. Sans configuration Firebase, JF MARKET bascule
sur un stockage JSON local afin de rester immédiatement utilisable.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

import httpx

from ..config import get_settings

FIRESTORE_BASE = "https://firestore.googleapis.com/v1"


class StorageBackend(Protocol):
    """Interface minimale commune aux deux backends."""

    name: str

    async def get_doc(self, collection: str, doc_id: str, token: str | None = None) -> dict | None: ...

    async def set_doc(
        self, collection: str, doc_id: str, data: dict, token: str | None = None
    ) -> dict: ...

    async def delete_doc(self, collection: str, doc_id: str, token: str | None = None) -> None: ...

    async def query(
        self,
        collection: str,
        filters: list[tuple[str, str, Any]] | None = None,
        *,
        limit: int = 100,
        token: str | None = None,
    ) -> list[dict]: ...


class LocalBackend:
    """Stockage JSON local, atomique et protégé par un verrou asynchrone."""

    name = "local-json"

    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self.path = path or (settings.data_dir / "jfmarket.json")
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, dict[str, dict]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, dict[str, dict]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self.path.parent), delete=False
        )
        try:
            json.dump(data, handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, self.path)

    async def get_doc(self, collection: str, doc_id: str, token: str | None = None) -> dict | None:
        async with self._lock:
            data = self._read()
        return data.get(collection, {}).get(doc_id)

    async def set_doc(
        self, collection: str, doc_id: str, data: dict, token: str | None = None
    ) -> dict:
        async with self._lock:
            store = self._read()
            store.setdefault(collection, {})[doc_id] = data
            self._write(store)
        return data

    async def delete_doc(self, collection: str, doc_id: str, token: str | None = None) -> None:
        async with self._lock:
            store = self._read()
            if doc_id in store.get(collection, {}):
                del store[collection][doc_id]
                self._write(store)

    async def query(
        self,
        collection: str,
        filters: list[tuple[str, str, Any]] | None = None,
        *,
        limit: int = 100,
        token: str | None = None,
    ) -> list[dict]:
        async with self._lock:
            data = self._read()
        rows = list(data.get(collection, {}).values())
        for field, operator, value in filters or []:
            rows = [row for row in rows if _match(row.get(field), operator, value)]
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return rows[:limit]


def _match(current: Any, operator: str, expected: Any) -> bool:
    if operator == "==":
        return current == expected
    if operator == "!=":
        return current != expected
    if operator == "in":
        return current in (expected or [])
    if operator == ">=":
        return (current or "") >= expected
    if operator == "<=":
        return (current or "") <= expected
    return False


# --- Conversion Firestore REST -------------------------------------------------


def to_firestore(data: dict) -> dict:
    """Convertit un dict Python en `fields` Firestore REST."""
    return {"fields": {key: _to_value(value) for key, value in data.items()}}


def _to_value(value: Any) -> dict:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_to_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {key: _to_value(item) for key, item in value.items()}}}
    return {"stringValue": str(value)}


def from_firestore(document: dict) -> dict:
    """Convertit un document Firestore REST en dict Python."""
    fields = document.get("fields", {})
    data = {key: _from_value(value) for key, value in fields.items()}
    name = document.get("name", "")
    if name:
        data.setdefault("id", name.rsplit("/", 1)[-1])
    return data


def _from_value(value: dict) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    if "nullValue" in value:
        return None
    if "arrayValue" in value:
        return [_from_value(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {key: _from_value(item) for key, item in value["mapValue"].get("fields", {}).items()}
    return None


class FirestoreBackend:
    """Backend Firestore via REST.

    Les lectures publiques (annonces) utilisent la clé Web du projet ; les
    écritures utilisent le jeton d'identité Firebase de l'utilisateur, afin que
    les règles de sécurité Firestore restent applicables.
    """

    name = "firestore"

    def __init__(self, project_id: str, api_key: str) -> None:
        self.project_id = project_id
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=12.0, follow_redirects=True)
        return self._client

    def _collection_url(self, collection: str) -> str:
        return (
            f"{FIRESTORE_BASE}/projects/{self.project_id}/databases/(default)"
            f"/documents/{collection}"
        )

    def _doc_url(self, collection: str, doc_id: str) -> str:
        return f"{self._collection_url(collection)}/{doc_id}"

    def _params(self, token: str | None) -> dict:
        return {} if token else {"key": self.api_key}

    def _headers(self, token: str | None) -> dict:
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def get_doc(self, collection: str, doc_id: str, token: str | None = None) -> dict | None:
        response = await self._http().get(
            self._doc_url(collection, doc_id),
            params=self._params(token),
            headers=self._headers(token),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return from_firestore(response.json())

    async def set_doc(
        self, collection: str, doc_id: str, data: dict, token: str | None = None
    ) -> dict:
        response = await self._http().patch(
            self._doc_url(collection, doc_id),
            params=self._params(token),
            headers=self._headers(token),
            json=to_firestore(data),
        )
        response.raise_for_status()
        stored = from_firestore(response.json())
        stored.setdefault("id", doc_id)
        return stored

    async def delete_doc(self, collection: str, doc_id: str, token: str | None = None) -> None:
        response = await self._http().delete(
            self._doc_url(collection, doc_id),
            params=self._params(token),
            headers=self._headers(token),
        )
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()

    async def query(
        self,
        collection: str,
        filters: list[tuple[str, str, Any]] | None = None,
        *,
        limit: int = 100,
        token: str | None = None,
    ) -> list[dict]:
        structured: dict[str, Any] = {
            "from": [{"collectionId": collection}],
            "limit": limit,
        }
        clauses = []
        for field, operator, value in filters or []:
            op = {
                "==": "EQUAL",
                "!=": "NOT_EQUAL",
                "in": "IN",
                ">=": "GREATER_THAN_OR_EQUAL",
                "<=": "LESS_THAN_OR_EQUAL",
            }.get(operator, "EQUAL")
            field_filter: dict[str, Any] = {
                "field": {"fieldPath": field},
                "op": op,
                "value": _to_value(value),
            }
            clauses.append({"fieldFilter": field_filter})
        if clauses:
            structured["where"] = clauses[0] if len(clauses) == 1 else {"compositeFilter": {"op": "AND", "filters": clauses}}
        response = await self._http().post(
            f"{FIRESTORE_BASE}/projects/{self.project_id}/databases/(default)/documents:runQuery",
            params=self._params(token),
            headers=self._headers(token),
            json={"structuredQuery": structured},
        )
        response.raise_for_status()
        results = []
        for item in response.json():
            document = item.get("document")
            if document:
                results.append(from_firestore(document))
        return results


def make_backend() -> StorageBackend:
    """Choisit Firestore si Firebase est configuré, sinon le stockage local."""
    settings = get_settings()
    if settings.firebase_enabled:
        return FirestoreBackend(
            project_id=settings.firebase_project_id or "",
            api_key=settings.firebase_api_key or "",
        )
    return LocalBackend()
