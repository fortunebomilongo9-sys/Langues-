"""Dépendances partagées par les routeurs : services, sécurité, limitation."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status

from ..auth import AuthContext, AuthError, AuthService
from ..config import get_settings
from ..engine.pipeline import SearchEngine
from ..store.repository import Repository


@lru_cache(maxsize=1)
def get_repository() -> Repository:
    return Repository()


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(get_repository())


@lru_cache(maxsize=1)
def get_engine() -> SearchEngine:
    return SearchEngine(get_repository())


class RateLimiter:
    """Limitation simple par client, en mémoire, sans dépendance externe."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        window = self.hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de requêtes. Patientez une minute avant de réessayer.",
            )
        window.append(now)


@lru_cache(maxsize=1)
def get_limiter() -> RateLimiter:
    return RateLimiter(get_settings().rate_limit_per_minute)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "inconnu"


async def rate_limit(request: Request) -> None:
    get_limiter().check(client_key(request))


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


async def optional_user(request: Request) -> AuthContext | None:
    token = _bearer(request)
    if not token:
        return None
    try:
        return await get_auth_service().authenticate(token)
    except AuthError:
        return None
    except Exception:  # noqa: BLE001 - jamais de panne bloquante
        return None


async def require_user(request: Request) -> AuthContext:
    token = _bearer(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Connectez-vous pour accéder à cette fonctionnalité.",
        )
    try:
        return await get_auth_service().authenticate(token)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


async def require_seller(context: AuthContext = Depends(require_user)) -> AuthContext:
    if context.user.role != "vendeur":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les comptes vendeur peuvent publier des annonces.",
        )
    return context
