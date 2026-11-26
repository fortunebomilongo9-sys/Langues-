"""Routeur du moteur de recherche : texte naturel et recherche par image."""

from __future__ import annotations

import asyncio
import re

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..auth import AuthContext
from ..config import get_settings
from ..engine.pipeline import SearchEngine
from ..images.visual import compare_signatures, signature_from_bytes, signature_from_url
from ..models import HistoryCreate, ImageSearchResponse, SearchRequest, SearchResponse
from ..store.repository import Repository
from .deps import (
    get_engine,
    get_repository,
    optional_user,
    rate_limit,
)

router = APIRouter(prefix="/api", tags=["recherche"])

MAX_IMAGE_BYTES = 6 * 1024 * 1024
_GENERIC_STEMS = {
    "image", "photo", "img", "picture", "screenshot", "capture", "whatsapp", "download",
    "telechargement", "produit", "article", "new", "final", "copie", "copy", "unnamed",
}


def _hint_from_filename(filename: str | None) -> str | None:
    """Déduit un mot-clé du nom de fichier, sans jamais inventer de produit."""
    if not filename:
        return None
    stem = filename.rsplit(".", 1)[0]
    stem = re.sub(r"[_\-.]+", " ", stem)
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem)
    words = [word for word in stem.split() if word.isalpha() and len(word) > 1]
    cleaned = " ".join(
        word for word in words if word.lower() not in _GENERIC_STEMS and not word.isdigit()
    )
    return cleaned if len(cleaned) >= 3 else None


@router.post("/search", response_model=SearchResponse, dependencies=[Depends(rate_limit)])
async def search(
    payload: SearchRequest,
    context: AuthContext | None = Depends(optional_user),
    engine: SearchEngine = Depends(get_engine),
    repository: Repository = Depends(get_repository),
) -> SearchResponse:
    """Lance une recherche commerciale complète sur les sources réelles."""
    response = await engine.search(payload)
    if context is not None:
        try:
            await repository.add_history(
                context.user.uid,
                HistoryCreate(
                    query=payload.query,
                    intent_summary=_intent_summary(response),
                    results=response.count,
                ).model_dump()
                | {},
                token=context.id_token,
            )
        except Exception:  # noqa: BLE001 - l'historique ne doit jamais bloquer une recherche
            pass
    return response


def _intent_summary(response: SearchResponse) -> str:
    intent = response.intent
    parts = [intent.product or intent.normalized_query or response.query]
    if intent.brand:
        parts.append(intent.brand)
    if intent.product_model:
        parts.append(intent.product_model)
    if intent.budget_max:
        parts.append(f"budget {intent.budget_max:g} {intent.currency or 'USD'}")
    if intent.condition and intent.condition != "inconnu":
        parts.append(intent.condition)
    if intent.commune:
        parts.append(intent.commune)
    return " · ".join(parts)[:300]


@router.post("/search/image", response_model=ImageSearchResponse, dependencies=[Depends(rate_limit)])
async def search_by_image(
    file: UploadFile = File(...),
    hint: str | None = Form(default=None),
    limit: int = Form(default=12),
    engine: SearchEngine = Depends(get_engine),
) -> ImageSearchResponse:
    """Recherche des offres à partir d'une photographie importée.

    La photo est analysée (dimensions, couleurs dominantes, empreinte
    perceptuelle) puis comparée aux images des offres réellement récupérées.
    Un mot-clé est nécessaire pour lancer la collecte : il peut être saisi par
    l'utilisateur ou déduit du nom du fichier.
    """
    settings = get_settings()
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Fichier image vide")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image trop volumineuse (maximum {settings.upload_max_bytes // (1024 * 1024)} Mo)",
        )
    signature = signature_from_bytes(content)
    if signature is None:
        raise HTTPException(
            status_code=400, detail="Format d'image non reconnu. Utilisez JPG, PNG ou WebP."
        )

    guess = " ".join((hint or "").split())[:120] or _hint_from_filename(file.filename)
    if not guess:
        return ImageSearchResponse(
            method="signature visuelle",
            query_guess=None,
            count=0,
            message=(
                "Image analysée. Ajoutez un mot-clé (par exemple « Samsung S24 ») pour que "
                "JF MARKET recherche les offres correspondantes : aucun produit n'est deviné."
            ),
        )

    response = await engine.search(SearchRequest(query=guess, limit=max(limit, 8)))
    offers = [offer for offer in response.offers if offer.image or offer.images]
    if not offers:
        return ImageSearchResponse(
            method="signature visuelle",
            query_guess=guess,
            intent=response.intent,
            count=0,
            network_ok=response.network_ok,
            message=response.message
            or "Aucune offre avec image n'a été trouvée pour cette recherche.",
        )

    scored: list[tuple[float, object]] = []
    async with httpx.AsyncClient(
        timeout=8.0, headers={"User-Agent": settings.user_agent}, follow_redirects=True
    ) as client:
        semaphore = asyncio.Semaphore(6)

        async def compare(offer) -> tuple[float, object]:
            urls = [offer.image.url] if offer.image else []
            urls += [image.url for image in offer.images[:2]]
            best = 0.0
            async with semaphore:
                for url in urls[:3]:
                    try:
                        other = await signature_from_url(client, url)
                    except Exception:  # noqa: BLE001
                        continue
                    best = max(best, compare_signatures(signature, other))
            return best, offer

        scored = list(await asyncio.gather(*(compare(offer) for offer in offers[:10])))

    scored.sort(key=lambda item: item[0], reverse=True)
    kept = [(score, offer) for score, offer in scored if score >= 0.55]
    selected = [offer for _, offer in kept[:limit]] or [offer for _, offer in scored[:limit]]
    for score, offer in scored:
        if offer in selected:
            offer.relevance_reasons = list(offer.relevance_reasons) + [
                f"Similitude visuelle {round(score * 100)} %"
            ]

    return ImageSearchResponse(
        method="signature visuelle (couleurs, proportions, empreinte perceptuelle)",
        query_guess=guess,
        intent=response.intent,
        offers=selected,
        count=len(selected),
        network_ok=response.network_ok,
        message=(
            "Offres classées par ressemblance visuelle avec votre photo. "
            "Vérifiez toujours la marque et le modèle sur l'annonce originale : "
            "la comparaison visuelle ne prouve pas l'identité exacte du produit."
        ),
    )
