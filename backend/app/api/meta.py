"""Routeurs de catalogue : santé, taxonomie, sources, suggestions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..config import get_settings
from ..engine.normalize import fold
from ..engine.query_parser import parse_query
from ..engine.scoring import search_suggestions
from ..models import HealthResponse, TaxonomyResponse
from ..sources.registry import source_catalog
from ..taxonomy import (
    BRANDS,
    CATEGORIES,
    CITIES,
    COMMUNES,
    CONDITION_LABELS,
    IMAGE_SOURCE_LABELS,
    POPULAR_BRANDS,
    SELLER_TYPE_LABELS,
    TRENDING_SEARCHES_2026,
)
from .deps import get_engine, rate_limit

router = APIRouter(prefix="/api", tags=["catalogue"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """État du service et des sources réellement configurées."""
    settings = get_settings()
    repository = request.app.state.repository
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        auth_provider="firebase" if settings.firebase_enabled else "local",
        storage_backend="firebase-storage" if settings.storage_enabled else "local",
        database_backend=(
            "firestore" if settings.firebase_enabled else "local"
        ),
        sources=[
            {
                "id": item["id"],
                "label": item["label"],
                "kind": item["kind"],
                "status": "ok" if item.get("enabled", True) else "desactive",
                "detail": item.get("detail"),
                "results": 0,
                "took_ms": 0,
            }
            for item in source_catalog()
        ],
        image_search=(
            "serpapi+cohérence" if settings.serpapi_enabled else "cohérence+signature visuelle"
        ),
        firebase_configured=settings.firebase_enabled,
        serpapi_configured=settings.serpapi_enabled,
    )


@router.get("/taxonomy", response_model=TaxonomyResponse)
async def taxonomy() -> TaxonomyResponse:
    """Catégories, marques, communes et recherches populaires."""
    brands = [
        {
            "name": name,
            "aliases": data.get("aliases", []),
            "categories": data.get("categories", []),
            "official_site": data.get("official_site"),
        }
        for name, data in BRANDS.items()
    ]
    return TaxonomyResponse(
        categories=CATEGORIES,
        brands=brands,
        communes=COMMUNES,
        cities=sorted(CITIES.keys()),
        trending=TRENDING_SEARCHES_2026,
        popular_brands=POPULAR_BRANDS,
        conditions=[{"id": key, "label": value} for key, value in CONDITION_LABELS.items()],
        seller_types=[{"id": key, "label": value} for key, value in SELLER_TYPE_LABELS.items()],
        image_sources=IMAGE_SOURCE_LABELS,
        currency_note=(
            "Les prix sont affichés dans la devise publiée par le vendeur (USD ou CDF). "
            "Aucune conversion n'est inventée : un prix absent est affiché « Non renseigné »."
        ),
    )


@router.get("/sources")
async def sources() -> dict:
    """Liste des sources commerciales consultées et leur disponibilité."""
    return {"sources": source_catalog()}


@router.get("/suggest", dependencies=[Depends(rate_limit)])
async def suggest(q: str = Query(default="", max_length=120)) -> dict:
    """Suggestions et corrections proposées pour une requête partielle."""
    cleaned = " ".join((q or "").split())
    if len(cleaned) < 2:
        return {"query": cleaned, "suggestions": [], "corrections": {}}
    intent = parse_query(cleaned)
    suggestions = search_suggestions(intent)
    return {
        "query": cleaned,
        "normalized": fold(cleaned),
        "suggestions": suggestions,
        "corrections": intent.corrections,
        "brand": intent.brand,
        "category": intent.category,
        "commune": intent.commune,
    }
