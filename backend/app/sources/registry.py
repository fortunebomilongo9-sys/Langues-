"""Registre des sources commerciales consultees par JF MARKET."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from .base import SearchSource, SourceContext, SourceRun
from .marketplace import MarketplaceSource, marketplace_configs
from .page_extractor import PageFetcher, extract_offers_from_results, result_is_commercial
from .serpapi import SerpApiSource
from .web_search import search_web

MAX_PAGE_ERRORS = 3


@dataclass
class WebSearchSource:
    """Recherche web multi-moteurs + lecture des pages commerciales."""

    id = "web"
    label = "Recherche web commerciale"
    kind = "web"

    def __init__(self, fetcher: PageFetcher, *, stage: str = "exact", engines=None) -> None:
        self._fetcher = fetcher
        self._stage = stage
        self._engines = engines

    async def collect(self, client, context: SourceContext) -> SourceRun:
        results, errors = await search_web(
            client, context.query, per_engine=8, engines=self._engines
        )
        if not results:
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="échec",
                detail="; ".join(errors[:2]) or "aucun résultat",
                network_error=bool(errors),
            )
        commercial = [result for result in results if result_is_commercial(result)]
        if not commercial:
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="vide",
                detail="aucun lien commercial parmi les résultats",
            )
        offers, page_errors = await extract_offers_from_results(
            self._fetcher, commercial, context, stage=self._stage
        )
        detail_parts = (errors + page_errors)[:MAX_PAGE_ERRORS]
        return SourceRun(
            source_id=self.id,
            label=self.label,
            offers=offers,
            status="ok" if offers else "vide",
            detail="; ".join(detail_parts) or None,
            network_error=not offers and bool(errors),
        )


def build_sources(fetcher: PageFetcher, *, stage: str = "exact") -> list[SearchSource]:
    """Construit la liste des sources actives pour une étape de recherche."""
    sources: list[SearchSource] = [WebSearchSource(fetcher, stage=stage)]
    sources.extend(MarketplaceSource(fetcher, config, stage=stage) for config in marketplace_configs())
    if settings.serpapi_enabled:
        sources.append(SerpApiSource(settings.serpapi_key, stage=stage))
    return sources


def source_catalog() -> list[dict]:
    """Descriptif des sources et de leur disponibilité (endpoint /health)."""
    catalog: list[dict] = [
        {
            "id": "web",
            "label": "Recherche web commerciale",
            "kind": "web",
            "enabled": True,
            "detail": "DuckDuckGo, Bing, Mojeek",
        }
    ]
    for config in marketplace_configs():
        catalog.append(
            {
                "id": config["id"],
                "label": config["label"],
                "kind": "marketplace",
                "enabled": True,
                "detail": ", ".join(config["domains"]),
            }
        )
    catalog.append(
        {
            "id": "serpapi-google-shopping",
            "label": "Google Shopping (API commerciale)",
            "kind": "serpapi",
            "enabled": settings.serpapi_enabled,
            "detail": "activée par SERPAPI_KEY" if not settings.serpapi_enabled else "clé détectée",
        }
    )
    return catalog
