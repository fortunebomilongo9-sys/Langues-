"""Dépôt applicatif : comptes, annonces, favoris et historique.

Chaque méthode est indépendante du backend (Firestore ou JSON local) et
renvoie des modèles Pydantic validés.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from ..models import AuthUser, Favorite, HistoryEntry, Listing, utcnow
from .backends import StorageBackend, make_backend


def new_id(prefix: str = "") -> str:
    token = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]
    return f"{prefix}{token}" if prefix else token


class Repository:
    """Accès aux collections persistées de JF MARKET."""

    def __init__(self, backend: StorageBackend | None = None) -> None:
        self.backend = backend or make_backend()

    # --- Comptes ---------------------------------------------------------
    async def get_user(self, uid: str, token: str | None = None) -> dict | None:
        return await self.backend.get_doc("users", uid, token)

    async def get_user_by_email(self, email: str) -> dict | None:
        rows = await self.backend.query("users", [("email", "==", email.strip().lower())], limit=1)
        return rows[0] if rows else None

    async def save_user(self, user: dict, token: str | None = None) -> dict:
        uid = user["uid"]
        return await self.backend.set_doc("users", uid, user, token)

    async def to_auth_user(self, data: dict) -> AuthUser:
        return AuthUser(
            uid=data.get("uid") or data.get("id", ""),
            email=data.get("email", ""),
            role=data.get("role", "acheteur"),
            display_name=data.get("display_name") or data.get("email", "").split("@")[0],
            seller_type=data.get("seller_type") or "particulier",
            created_at=data.get("created_at", utcnow()),
        )

    # --- Annonces --------------------------------------------------------
    async def create_listing(self, listing: Listing, token: str | None = None) -> Listing:
        await self.backend.set_doc("listings", listing.id, listing.model_dump(), token)
        return listing

    async def get_listing(self, listing_id: str, token: str | None = None) -> Listing | None:
        data = await self.backend.get_doc("listings", listing_id, token)
        return Listing(**data) if data else None

    async def update_listing(
        self, listing_id: str, changes: dict[str, Any], token: str | None = None
    ) -> Listing | None:
        current = await self.get_listing(listing_id, token)
        if current is None:
            return None
        payload = current.model_dump()
        payload.update({key: value for key, value in changes.items() if value is not None})
        payload["updated_at"] = utcnow()
        updated = Listing(**payload)
        await self.backend.set_doc("listings", listing_id, updated.model_dump(), token)
        return updated

    async def delete_listing(self, listing_id: str, token: str | None = None) -> None:
        await self.backend.delete_doc("listings", listing_id, token)

    async def list_public_listings(self, limit: int = 200) -> list[Listing]:
        rows = await self.backend.query("listings", [("status", "==", "publie")], limit=limit)
        listings = []
        for row in rows:
            try:
                listings.append(Listing(**row))
            except Exception:  # noqa: BLE001 - un document corrompu ne bloque pas la liste
                continue
        listings.sort(key=lambda item: item.created_at, reverse=True)
        return listings

    async def list_seller_listings(self, seller_uid: str, token: str | None = None) -> list[Listing]:
        rows = await self.backend.query("listings", [("seller_uid", "==", seller_uid)], limit=200, token=token)
        listings = []
        for row in rows:
            try:
                listings.append(Listing(**row))
            except Exception:  # noqa: BLE001
                continue
        listings.sort(key=lambda item: item.created_at, reverse=True)
        return listings

    # --- Favoris ---------------------------------------------------------
    async def add_favorite(self, favorite: Favorite, token: str | None = None) -> Favorite:
        await self.backend.set_doc("favorites", favorite.id, favorite.model_dump(), token)
        return favorite

    async def list_favorites(self, user_uid: str, token: str | None = None) -> list[Favorite]:
        rows = await self.backend.query("favorites", [("user_uid", "==", user_uid)], limit=200, token=token)
        favorites = []
        for row in rows:
            try:
                favorites.append(Favorite(**row))
            except Exception:  # noqa: BLE001
                continue
        favorites.sort(key=lambda item: item.created_at, reverse=True)
        return favorites

    async def delete_favorite(
        self, user_uid: str, favorite_id: str, token: str | None = None
    ) -> bool:
        data = await self.backend.get_doc("favorites", favorite_id, token)
        if not data or data.get("user_uid") != user_uid:
            return False
        await self.backend.delete_doc("favorites", favorite_id, token)
        return True

    # --- Historique de recherche ----------------------------------------
    async def add_history(
        self, user_uid: str, entry: HistoryEntry, token: str | None = None
    ) -> HistoryEntry:
        doc_id = f"{user_uid}-{int(datetime.now(tz=timezone.utc).timestamp() * 1000)}-{new_id()[:5]}"
        payload = entry.model_dump()
        payload["id"] = doc_id
        payload["user_uid"] = user_uid
        await self.backend.set_doc("history", doc_id, payload, token)
        return entry

    async def list_history(
        self, user_uid: str, limit: int = 30, token: str | None = None
    ) -> list[HistoryEntry]:
        rows = await self.backend.query("history", [("user_uid", "==", user_uid)], limit=limit, token=token)
        entries = []
        for row in rows:
            try:
                entries.append(HistoryEntry(**row))
            except Exception:  # noqa: BLE001
                continue
        entries.sort(key=lambda item: item.created_at, reverse=True)
        return entries[:limit]
