"""Cache TTL en mémoire, borné et asynchrone.

Le cache évite de solliciter inutilement les sites commerciaux pour une même
recherche répétée. Il est volontairement simple (mono-processus) : il ne
remplace pas Firestore, il protège les sources externes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """Cache LRU avec expiration, sûr en concurrence asynchrone."""

    def __init__(self, *, max_entries: int = 256, ttl_seconds: float = 300.0) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = asyncio.Lock()

    @staticmethod
    def make_key(*parts: Any) -> str:
        """Clé stable à partir de valeurs simples (requête, filtres, étape)."""
        payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        ttl = self._ttl if ttl_seconds is None else ttl_seconds
        async with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._store), "max_entries": self._max_entries}
