"""Adaptateur « API de recherche commerciale » (Google Shopping via SerpApi).

Activé uniquement si la clé ``SERPAPI_KEY`` est présente dans
l'environnement du serveur. La clé ne quitte jamais le backend.
"""

from __future__ import annotations

from urllib.parse import urlparse

from ..models import SearchIntent
from .base import ImageRef, RawOffer, SourceContext, SourceRun
from .html_utils import clean_text, domain_of, parse_price_text, sanitize_url

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


class SerpApiSource:
    """Résultats marchands structurés fournis par une API commerciale."""

    id = "serpapi-google-shopping"
    label = "Google Shopping (API commerciale)"
    kind = "serpapi"

    def __init__(self, api_key: str | None, *, stage: str = "exact") -> None:
        self._api_key = api_key
        self._stage = stage

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def collect(self, client, context: SourceContext) -> SourceRun:
        if not self._api_key:
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="desactive",
                detail="Clé SERPAPI_KEY non configurée",
            )
        params = {
            "engine": "google_shopping",
            "q": context.query,
            "gl": "cd",
            "hl": "fr",
            "num": "20",
            "api_key": self._api_key,
        }
        try:
            response = await client.get(SERPAPI_ENDPOINT, params=params, timeout=12.0)
        except Exception as exc:  # noqa: BLE001
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="echec",
                detail=f"API commerciale injoignable ({type(exc).__name__})",
                network_error=True,
            )
        if response.status_code == 401:
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="echec",
                detail="Clé d'API commerciale refusée",
            )
        if response.status_code >= 400:
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="echec",
                detail=f"API commerciale : HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="echec",
                detail="Réponse de l'API commerciale illisible",
            )

        offers: list[RawOffer] = []
        for item in (payload.get("shopping_results") or [])[: context.limit]:
            title = clean_text(item.get("title"), 200)
            link = sanitize_url(item.get("product_link") or item.get("link"))
            if not title or not link:
                continue
            price_text = item.get("price")
            amount, currency, parsed_text = parse_price_text(price_text)
            extracted = item.get("extracted_price")
            if isinstance(extracted, (int, float)) and extracted > 0:
                amount = float(extracted)
            seller = clean_text(item.get("source"), 120) or None
            images: list[ImageRef] = []
            thumbnail = sanitize_url(item.get("thumbnail"))
            if thumbnail:
                images.append(ImageRef(url=thumbnail, origin="og", page_url=link))
            offers.append(
                RawOffer(
                    title=title,
                    url=link,
                    source_id=self.id,
                    source_name=self.label,
                    site_domain=domain_of(link) or urlparse(link).netloc,
                    description=clean_text(item.get("snippet"), 400) or None,
                    price=amount,
                    currency=currency,
                    price_text=parsed_text,
                    condition_text=None,
                    availability_text=None,
                    seller_name=seller,
                    seller_type="boutique" if seller else "inconnu",
                    images=images,
                    trust=0.82,
                    stage=self._stage,
                    extraction="serpapi",
                )
            )
        return SourceRun(
            source_id=self.id,
            label=self.label,
            offers=offers,
            status="ok" if offers else "vide",
            detail=None if offers else "Aucun résultat marchand retourné par l'API",
        )


async def search_shopping_images(
    client, api_key: str, query: str, *, limit: int = 8
) -> tuple[list[dict], str | None]:
    """Recherche d'images indépendante via la même API commerciale.

    Renvoie une liste de dicts ``{url, title, source, link}`` réellement fournis
    par le fournisseur. Aucune image n'est inventée.
    """
    params = {
        "engine": "google_images",
        "q": query,
        "gl": "cd",
        "hl": "fr",
        "num": str(max(1, min(limit, 20))),
        "api_key": api_key,
    }
    try:
        response = await client.get(SERPAPI_ENDPOINT, params=params, timeout=12.0)
    except Exception as exc:  # noqa: BLE001
        return [], f"recherche d'images injoignable ({type(exc).__name__})"
    if response.status_code >= 400:
        return [], f"recherche d'images : HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return [], "réponse d'images illisible"
    items: list[dict] = []
    for entry in (payload.get("images_results") or [])[:limit]:
        url = sanitize_url(entry.get("original") or entry.get("thumbnail"))
        if not url:
            continue
        items.append(
            {
                "url": url,
                "title": clean_text(entry.get("title"), 200),
                "source": clean_text(entry.get("source"), 120),
                "link": sanitize_url(entry.get("link")),
            }
        )
    return items, None


def serpapi_intent_query(intent: SearchIntent) -> str:
    """Requête image dérivée de l'intention (marque + modèle + produit)."""
    parts = [intent.brand or "", intent.product_model or ""]
    parts.extend(intent.product_terms[:3])
    return " ".join(part for part in parts if part).strip() or intent.raw_query
