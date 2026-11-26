"""Routeur des comptes : inscription, connexion, favoris, historique."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import AuthContext, AuthError
from ..models import (
    AuthResponse,
    AuthUser,
    Favorite,
    FavoriteCreate,
    HistoryCreate,
    HistoryEntry,
    SignInRequest,
    SignUpRequest,
)
from ..store.repository import new_id
from .deps import get_auth_service, get_repository, rate_limit, require_user

router = APIRouter(prefix="/api", tags=["comptes"])


@router.post("/auth/signup", response_model=AuthResponse, dependencies=[Depends(rate_limit)])
async def signup(payload: SignUpRequest) -> AuthResponse:
    """Crée un compte acheteur ou vendeur."""
    try:
        token, user, provider = await get_auth_service().sign_up(payload)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AuthResponse(token=token, user=user, provider=provider)


@router.post("/auth/signin", response_model=AuthResponse, dependencies=[Depends(rate_limit)])
async def signin(payload: SignInRequest) -> AuthResponse:
    """Connecte un utilisateur existant."""
    try:
        token, user, provider = await get_auth_service().sign_in(payload)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AuthResponse(token=token, user=user, provider=provider)


@router.get("/auth/me", response_model=AuthUser)
async def me(context: AuthContext = Depends(require_user)) -> AuthUser:
    """Profil du compte connecté."""
    return context.user


@router.get("/favorites")
async def list_favorites(context: AuthContext = Depends(require_user)) -> dict:
    """Favoris enregistrés par l'utilisateur connecté."""
    favorites = await get_repository().list_favorites(
        context.user.uid, token=context.id_token
    )
    return {"count": len(favorites), "favorites": [item.model_dump() for item in favorites]}


@router.post("/favorites")
async def add_favorite(
    payload: FavoriteCreate, context: AuthContext = Depends(require_user)
) -> dict:
    """Ajoute une offre aux favoris."""
    favorite = Favorite(
        id=new_id("f_"),
        user_uid=context.user.uid,
        offer=payload.offer,
        note=payload.note,
    )
    saved = await get_repository().add_favorite(favorite, token=context.id_token)
    return saved.model_dump()


@router.delete("/favorites/{favorite_id}")
async def delete_favorite(
    favorite_id: str, context: AuthContext = Depends(require_user)
) -> dict:
    """Retire une offre des favoris."""
    deleted = await get_repository().delete_favorite(
        context.user.uid, favorite_id, token=context.id_token
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Favori introuvable")
    return {"deleted": True, "id": favorite_id}


@router.get("/history")
async def list_history(context: AuthContext = Depends(require_user)) -> dict:
    """Historique de recherche du compte connecté."""
    entries = await get_repository().list_history(
        context.user.uid, limit=30, token=context.id_token
    )
    return {"count": len(entries), "history": [item.model_dump() for item in entries]}


@router.post("/history")
async def add_history(
    payload: HistoryCreate, context: AuthContext = Depends(require_user)
) -> dict:
    """Enregistre une recherche dans l'historique du compte."""
    entry = HistoryEntry(
        query=payload.query,
        intent_summary=payload.intent_summary,
        results=payload.results,
    )
    saved = await get_repository().add_history(
        context.user.uid, entry, token=context.id_token
    )
    return saved.model_dump()
