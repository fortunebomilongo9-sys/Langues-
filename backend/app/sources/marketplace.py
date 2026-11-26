"""Sources « marketplace » : pages de résultats de boutiques en ligne.

L'extraction est pilotée par les configurations de :mod:`app.taxonomy`
(sélecteurs CSS), ce qui permet d'ajouter une boutique sans toucher au moteur.
"""

from __future__ import annotations

from ..engine.normalize import fold
from ..taxonomy import SITE_CONFIGS
from .base import ImageRef, RawOffer, SourceContext, SourceRun
from .html_utils import (
    clean_text,
    detect_condition,
    domain_of,
    make_soup,
    parse_price_text,
    sanitize_url,
)
from .page_extractor import PageFetcher

MAX_CARDS = 14


def offers_from_cards(
    html: bytes | str,
    page_url: str,
    config: dict,
    *,
    stage: str = "exact",
) -> list[RawOffer]:
    """Extrait les cartes produit d'une page de résultats de boutique."""
    soup = make_soup(html)
    cards = soup.select(config.get("card_selector", "article"))
    offers: list[RawOffer] = []
    seen: set[str] = set()
    for card in cards[:MAX_CARDS]:
        title_node = card.select_one(config.get("title_selector", "h3"))
        title = clean_text(title_node.get_text(" ", strip=True), 200) if title_node else ""
        link_node = card.select_one(config.get("link_selector", "a"))
        href = sanitize_url(link_node.get("href") if link_node else None, page_url)
        if not title or not href:
            continue
        key = fold(title)
        if key in seen:
            continue
        seen.add(key)

        price_node = card.select_one(config.get("price_selector", ".price"))
        price_text = price_node.get_text(" ", strip=True) if price_node else None
        amount, currency, parsed_text = parse_price_text(price_text)
        if currency is None and amount is not None:
            currency = config.get("currency")

        image_url = None
        image_node = card.select_one(config.get("image_selector", "img"))
        if image_node is not None:
            raw = image_node.get("data-src") or image_node.get("src") or image_node.get("data-lazy-src")
            image_url = sanitize_url(raw, page_url)
        alt = clean_text(image_node.get("alt"), 160) if image_node is not None else None

        offers.append(
            RawOffer(
                title=title,
                url=href,
                source_id=config["id"],
                source_name=config["label"],
                site_domain=domain_of(href) or domain_of(page_url),
                description=None,
                price=amount,
                currency=currency,
                price_text=parsed_text,
                condition_text=detect_condition(title),
                availability_text="disponible" if amount is not None else "inconnu",
                seller_name=None,
                seller_type="boutique",
                images=([ImageRef(url=image_url, alt=alt, origin="html", page_url=href)] if image_url else []),
                trust=float(config.get("trust", 0.7)),
                stage=stage,
                extraction="marketplace",
            )
        )
    return offers


class MarketplaceSource:
    """Page de résultats d'une boutique en ligne configurée."""

    kind = "marketplace"

    def __init__(self, fetcher: PageFetcher, config: dict, *, stage: str = "exact") -> None:
        self._fetcher = fetcher
        self._config = config
        self._stage = stage
        self.id = str(config["id"])
        self.label = str(config["label"])

    async def collect(self, client, context: SourceContext) -> SourceRun:
        url = str(self._config["search_url"]).format(query=_quote(context.query))
        content, _content_type, error = await self._fetcher.fetch(url)
        if error or content is None:
            return SourceRun(
                source_id=self.id,
                label=self.label,
                status="echec",
                detail=f"Boutique inaccessible ({error or 'réponse vide'})",
                network_error=bool(error),
            )
        offers = offers_from_cards(content, url, self._config, stage=self._stage)
        return SourceRun(
            source_id=self.id,
            label=self.label,
            offers=offers,
            status="ok" if offers else "vide",
            detail=None if offers else "Aucune carte produit reconnue sur la page",
        )


def _quote(value: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(value)


def marketplace_configs() -> list[dict]:
    """Configurations de boutiques disponibles."""
    return list(SITE_CONFIGS)
