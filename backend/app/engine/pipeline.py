"""Orchestrateur de la recherche progressive de JF MARKET.

Déroulement : analyse de la requête → collecte sur les sources commerciales →
étapes de reformulation si nécessaire → composition des fiches → pertinence →
déduplication → filtres → réponse.

Aucune offre n'est fabriquée : si rien de fiable n'est trouvé, la réponse le
dit explicitement et propose des reformulations.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from ..config import settings
from ..images.selector import explain_image_choice
from ..models import (
    Offer,
    SearchFilters,
    SearchIntent,
    SearchRequest,
    SearchResponse,
    SourceStatus,
    StageReport,
)
from ..sources.base import RawOffer, SourceContext, SourceRun
from ..sources.page_extractor import PageFetcher
from ..sources.registry import build_sources
from .cache import TTLCache
from .compose import compose_offers, offer_from_listing
from .dedupe import dedupe_offers
from .query_parser import build_search_query, intent_matches_offer, parse_query
from .scoring import apply_filters, rank_offers, search_suggestions

STAGE_LABELS = {
    "exact": "Recherche exacte",
    "synonymes": "Synonymes et variantes",
    "marque-reference": "Marque et référence",
    "elargi": "Recherche élargie",
}

_CONNECTIVITY_HINTS = (
    "délai",
    "delai",
    "timeout",
    "timed out",
    "connect",
    "dns",
    "name resolution",
    "network",
    "réseau",
    "reseau",
    "unreachable",
    "ssl",
)


def _is_connectivity_failure(detail: str) -> bool:
    """Distingue une vraie panne de connexion d'un refus d'accès d'une source.

    Un HTTP 403 ou une page anti-robot ne signifie pas que l'utilisateur est
    hors ligne : seul un échec réseau réel doit déclencher ce message.
    """
    text = (detail or "").lower()
    return any(hint in text for hint in _CONNECTIVITY_HINTS)


def _stage_queries(intent: SearchIntent) -> list[tuple[str, str]]:
    """Construit les étapes de recherche progressive (requête par étape)."""
    stages: list[tuple[str, str]] = [("exact", build_search_query(intent))]
    if intent.expanded_terms:
        stages.append(("synonymes", build_search_query(intent, intent.expanded_terms[:4])))
    reference = intent.product_reference or intent.product_model
    if intent.brand and reference:
        stages.append(("marque-reference", f"{intent.brand} {reference}".strip()))
    broad_terms: list[str] = []
    if intent.category_label:
        broad_terms.append(intent.category_label)
    if intent.brand:
        broad_terms.append(intent.brand)
    if not broad_terms:
        broad_terms = intent.product_terms[:2]
    if broad_terms:
        stages.append(("elargi", " ".join(dict.fromkeys(broad_terms))))
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for stage, query in stages:
        cleaned = " ".join(query.split())
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        unique.append((stage, cleaned))
    return unique


class SearchEngine:
    """Moteur de recherche commercial de JF MARKET."""

    def __init__(self, repository=None) -> None:
        self._repository = repository
        self._cache = TTLCache(
            max_entries=settings.cache_max_entries, ttl_seconds=settings.cache_ttl_search
        )

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Exécute une recherche complète et renvoie une réponse prête à afficher."""
        started = time.perf_counter()
        intent = parse_query(request.query)
        filters = request.filters or SearchFilters()
        key = TTLCache.make_key(
            "search", request.query.strip().lower(), filters.model_dump(), request.limit
        )
        cached = await self._cache.get(key)
        if isinstance(cached, SearchResponse):
            return cached.model_copy(update={"cached": True})

        raw_offers, stages, sources, network_failures, blocked_sources = await self._collect(
            intent, request
        )
        offers = compose_offers(raw_offers, intent)
        offers.extend(await self._local_offers(intent, request))
        offers = rank_offers(offers, intent)
        offers = dedupe_offers(offers)
        offers = apply_filters(offers, filters, intent)
        offers = offers[: min(request.limit, settings.max_results_hard)]

        network_ok = not (network_failures and not offers)
        message = self._message(intent, offers, network_ok, sources, blocked_sources)
        response = SearchResponse(
            query=request.query,
            intent=intent,
            offers=offers,
            count=len(offers),
            stages=stages,
            sources=sources,
            sources_failed=sum(1 for source in sources if source.status == "échec"),
            message=message,
            network_ok=network_ok,
            cached=False,
            took_ms=int((time.perf_counter() - started) * 1000),
            filters=filters,
        )
        await self._cache.set(key, response)
        return response

    async def _collect(
        self, intent: SearchIntent, request: SearchRequest
    ) -> tuple[list[RawOffer], list[StageReport], list[SourceStatus], list[str], list[str]]:
        """Exécute les étapes de recherche jusqu'à obtenir assez d'offres fiables."""
        raw_offers: list[RawOffer] = []
        reports: list[StageReport] = []
        statuses: dict[str, SourceStatus] = {}
        network_failures: list[str] = []
        blocked_sources: list[str] = []
        deadline = time.monotonic() + settings.http_total_budget
        seen_keys: set[str] = set()

        timeout = httpx.Timeout(settings.http_timeout)
        limits = httpx.Limits(max_connections=max(2, settings.http_concurrency))
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
            max_redirects=5,
            limits=limits,
        ) as client:
            fetcher = PageFetcher(client, timeout=settings.http_timeout)
            for stage, query in _stage_queries(intent):
                if raw_offers and len(seen_keys) >= settings.min_results_before_expanding:
                    break
                if time.monotonic() >= deadline:
                    reports.append(
                        StageReport(
                            stage=stage,
                            label=STAGE_LABELS.get(stage, stage),
                            query_used=query,
                            offers_found=0,
                            note="étape ignorée : budget de temps atteint",
                        )
                    )
                    continue
                context = SourceContext(
                    intent=intent,
                    query=query,
                    limit=request.limit,
                    pages_budget=max(2, min(settings.http_max_pages, 5)),
                )
                runs = await self._run_sources(fetcher, context, stage)
                stage_offers: list[RawOffer] = []
                for run in runs:
                    self._merge_status(statuses, run)
                    if run.network_error:
                        detail = run.detail or run.label
                        if _is_connectivity_failure(detail):
                            network_failures.append(detail)
                        else:
                            blocked_sources.append(detail)
                    stage_offers.extend(run.offers)
                for offer in stage_offers:
                    marker = f"{offer.url}|{offer.title[:40].lower()}"
                    if marker in seen_keys:
                        continue
                    seen_keys.add(marker)
                    raw_offers.append(offer)
                reports.append(
                    StageReport(
                        stage=stage,
                        label=STAGE_LABELS.get(stage, stage),
                        query_used=query,
                        offers_found=len(stage_offers),
                        note=None if stage_offers else "aucune offre exploitable à cette étape",
                    )
                )
        return raw_offers, reports, list(statuses.values()), network_failures, blocked_sources

    async def _run_sources(
        self, fetcher: PageFetcher, context: SourceContext, stage: str
    ) -> list[SourceRun]:
        """Interroge les sources en parallèle, en isolant chaque panne."""
        sources = build_sources(fetcher, stage=stage)
        client = fetcher.client

        async def guard(source) -> SourceRun:
            try:
                return await asyncio.wait_for(source.collect(client, context), timeout=settings.http_timeout + 6)
            except asyncio.TimeoutError:
                return SourceRun(
                    source_id=source.id,
                    label=source.label,
                    status="échec",
                    detail="délai d'attente dépassé",
                )
            except Exception as exc:  # noqa: BLE001 - une source ne bloque jamais la recherche
                return SourceRun(
                    source_id=source.id,
                    label=source.label,
                    status="échec",
                    detail=type(exc).__name__,
                )

        return await asyncio.gather(*(guard(source) for source in sources))

    @staticmethod
    def _merge_status(statuses: dict[str, SourceStatus], run: SourceRun) -> None:
        current = statuses.get(run.source_id)
        status_value = "ok" if run.offers else ("echec" if run.status == "échec" else "vide")
        if current is None:
            statuses[run.source_id] = SourceStatus(
                id=run.source_id,
                label=run.label,
                status=status_value,  # type: ignore[arg-type]
                offers=len(run.offers),
                detail=run.detail,
            )
            return
        current.offers += len(run.offers)
        if run.offers:
            current.status = "ok"
        if run.detail and not current.detail:
            current.detail = run.detail

    async def _local_offers(self, intent: SearchIntent, request: SearchRequest) -> list[Offer]:
        """Annonces publiées par les vendeurs JF MARKET, si pertinentes."""
        if self._repository is None:
            return []
        try:
            listings = await self._repository.list_public_listings(limit=200)
        except Exception:  # noqa: BLE001 - la recherche web reste prioritaire
            return []
        offers: list[Offer] = []
        for listing in listings:
            haystack = f"{listing.title} {listing.description}"
            if intent.product_terms and not intent_matches_offer(intent, listing.title, listing.description):
                continue
            if intent.brand and listing.brand and listing.brand != intent.brand:
                continue
            if intent.commune and listing.commune and listing.commune != intent.commune:
                continue
            if intent.condition != "inconnu" and listing.condition != intent.condition:
                continue
            try:
                offers.append(offer_from_listing(listing, intent))
            except Exception:  # noqa: BLE001
                continue
        return offers[: max(4, request.limit // 2)]

    @staticmethod
    def _message(
        intent: SearchIntent,
        offers: list[Offer],
        network_ok: bool,
        sources: list[SourceStatus],
        blocked_sources: list[str] | None = None,
    ) -> str | None:
        if not network_ok:
            return "Connectez-vous à Internet pour effectuer vos recherches."
        if offers:
            return None
        if not any(source.status == "ok" for source in sources):
            if blocked_sources:
                return (
                    "Les sources commerciales interrogées ont refusé l'accès automatisé "
                    "(protection anti-robot ou blocage). Réessayez plus tard, ou publiez "
                    "directement votre article sur JF MARKET."
                )
            return (
                "Les sources commerciales sont momentanément indisponibles. "
                "Réessayez dans quelques instants."
            )
        suggestions = " · ".join(search_suggestions(intent))
        return (
            "Aucune offre fiable trouvée pour cette recherche. "
            f"Reformulations proposées : {suggestions}"
        )


def describe_image_provenance(offer: Offer) -> str:
    """Message d'explication sur l'image d'une offre (utile au frontend)."""
    return explain_image_choice(offer.image)
