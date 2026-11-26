"""Extraction des offres commerciales depuis les pages trouvées sur le web.

Principes :
* seules les informations réellement publiées sont conservées ;
* une page sans indice commercial (prix, vente, boutique…) n'est pas une offre ;
* les champs absents restent vides et seront affichés « Non renseigné ».
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx

from ..engine.normalize import fold, truncate
from ..models import SearchIntent
from ..taxonomy import (
    COMMERCIAL_SIGNALS,
    MARKETPLACE_DOMAINS,
    NOT_PROVIDED,
    SITE_CONFIG_BY_DOMAIN,
)
from .base import ImageRef, RawOffer, SerpResult, SourceContext
from .html_utils import (
    candidate_images,
    clean_text,
    detect_availability,
    detect_condition,
    domain_of,
    extract_page_text,
    find_contacts,
    make_soup,
    meta_content,
    open_graph,
    parse_price_text,
    products_from_jsonld,
    sanitize_url,
)

MAX_PAGE_BYTES = 1_400_000
_HTML_TYPES = ("text/html", "application/xhtml", "application/xml", "text/plain")
_PRICE_HINT_RE = re.compile(r"(prix|price|tarif|fc\b|cdf|usd|\$|€)", re.IGNORECASE)
_IMAGE_LIMIT_PER_OFFER = 6


class PageFetcher:
    """Téléchargement de pages avec limites de taille et de type MIME."""

    def __init__(self, client: httpx.AsyncClient, *, timeout: float = 9.0) -> None:
        self._client = client
        self._timeout = timeout
        self._cache: dict[str, tuple[int, bytes, str]] = {}

    @property
    def client(self) -> httpx.AsyncClient:
        """Client HTTP partagé, utilisé par les sources pour leurs appels parallèles."""
        return self._client

    async def fetch(self, url: str) -> tuple[bytes | None, str | None, str | None]:
        """Renvoie (contenu, type, erreur)."""
        if not url:
            return None, None, "URL vide"
        cached = self._cache.get(url)
        if cached is not None:
            return cached[1], cached[2], None
        try:
            response = await self._client.get(url, follow_redirects=True)
        except httpx.TimeoutException:
            return None, None, "délai dépassé"
        except httpx.HTTPError as exc:
            return None, None, type(exc).__name__
        except Exception as exc:  # noqa: BLE001
            return None, None, type(exc).__name__

        if response.status_code >= 400:
            return None, None, f"HTTP {response.status_code}"
        content_type = (response.headers.get("content-type") or "").lower()
        if content_type and not any(item in content_type for item in _HTML_TYPES):
            return None, None, f"type non exploitable ({content_type.split(';')[0]})"
        content = response.content
        if len(content) > MAX_PAGE_BYTES:
            content = content[:MAX_PAGE_BYTES]
        if len(content) < 200:
            return None, None, "page vide"
        self._cache[url] = (response.status_code, content, content_type or "text/html")
        if len(self._cache) > 80:
            self._cache.pop(next(iter(self._cache)))
        return content, content_type or "text/html", None


def _is_commercial(text: str, price_found: bool) -> bool:
    if price_found:
        return True
    folded = fold(text)
    return any(signal in folded for signal in COMMERCIAL_SIGNALS)


def _site_profile(url: str) -> tuple[str, str, float, str]:
    """(source_id, source_name, confiance, type de vendeur) pour un domaine."""
    domain = domain_of(url)
    config = SITE_CONFIG_BY_DOMAIN.get(domain)
    if config:
        return config["id"], config["label"], float(config.get("trust", 0.7)), "boutique"
    if domain in MARKETPLACE_DOMAINS:
        return domain, domain, 0.68, "boutique"
    return domain or "web", domain or "Web", 0.45, "inconnu"


def _images_for(page_url: str, json_images: list[str], og_image: str | None, html_images: list[tuple[str, str | None]]) -> list[ImageRef]:
    images: list[ImageRef] = []
    seen: set[str] = set()
    for raw in json_images:
        url = sanitize_url(raw, page_url)
        if not url or url in seen:
            continue
        seen.add(url)
        images.append(ImageRef(url=url, origin="jsonld", page_url=page_url))
    if og_image:
        url = sanitize_url(og_image, page_url)
        if url and url not in seen:
            seen.add(url)
            images.append(ImageRef(url=url, origin="og", page_url=page_url))
    for url, alt in html_images:
        if url in seen:
            continue
        seen.add(url)
        images.append(ImageRef(url=url, alt=alt, origin="html", page_url=page_url))
        if len(images) >= _IMAGE_LIMIT_PER_OFFER + 2:
            break
    return images[:_IMAGE_LIMIT_PER_OFFER + 2]


def offer_from_page(
    html: bytes | str,
    page_url: str,
    *,
    stage: str = "exact",
    serp_title: str | None = None,
    serp_snippet: str | None = None,
    trust_override: float | None = None,
) -> list[RawOffer]:
    """Transforme une page HTML en une ou plusieurs offres structurées."""
    soup = make_soup(html)
    page_text = extract_page_text(soup)
    og = open_graph(soup, page_url)
    products = products_from_jsonld(soup, page_url)
    contacts = find_contacts(page_text)
    source_id, source_name, trust, seller_hint = _site_profile(page_url)
    if trust_override is not None:
        trust = trust_override

    offers: list[RawOffer] = []
    if products:
        html_images = candidate_images(soup, page_url)
        for product in products[:5]:
            title = clean_text(product.get("title"), 200)
            if not title:
                continue
            price = product.get("price")
            currency = product.get("currency")
            price_text = None
            if price is None:
                price, detected_currency, price_text = parse_price_text(
                    f"{title} {product.get('description') or ''} {page_text[:400]}"
                )
                currency = currency or detected_currency
            product_url = product.get("url") or page_url
            images = _images_for(
                product_url,
                product.get("images") or [],
                og.get("image"),
                html_images,
            )
            description = product.get("description") or clean_text(og.get("description"), 500) or None
            availability = detect_availability(product.get("availability"))
            if availability == "inconnu":
                availability = detect_availability(page_text[:1200])
            condition = detect_condition(product.get("condition"))
            if condition == "inconnu":
                condition = detect_condition(f"{title} {description or ''}")
            offers.append(
                RawOffer(
                    title=title,
                    url=sanitize_url(product_url, page_url) or page_url,
                    source_id=source_id,
                    source_name=source_name,
                    site_domain=domain_of(page_url),
                    description=description,
                    price=float(price) if isinstance(price, (int, float)) else None,
                    currency=currency,
                    price_text=price_text,
                    brand=product.get("brand"),
                    product_model=product.get("sku") if isinstance(product.get("sku"), str) else None,
                    condition_text=condition,
                    availability_text=availability,
                    seller_name=product.get("seller_name"),
                    seller_type=seller_hint,
                    location_text=None,
                    images=images,
                    contact_phone=contacts.get("phone"),
                    contact_email=contacts.get("email"),
                    contact_whatsapp=contacts.get("whatsapp"),
                    published_at=product.get("published_at"),
                    trust=trust,
                    stage=stage,
                    extraction="jsonld",
                )
            )
        if offers:
            return offers

    # 2. Extraction générique (page produit sans données structurées)
    heading = soup.find("h1")
    title = (
        clean_text(heading.get_text(" ", strip=True), 200)
        if heading
        else clean_text(og.get("title") or serp_title, 200)
    )
    if not title:
        return []

    meta_price = meta_content(
        soup,
        names=("product:price:amount", "og:price:amount"),
        props=("product:price:amount", "og:price:amount"),
    )
    meta_currency = meta_content(
        soup,
        names=("product:price:currency", "og:price:currency"),
        props=("product:price:currency", "og:price:currency"),
    )
    price: float | None = None
    currency: str | None = clean_text(meta_currency, 8) or None
    price_text: str | None = None
    if meta_price:
        price, _currency, price_text = parse_price_text(meta_price)
        if price is None:
            from ..engine.normalize import parse_amount

            price = parse_amount(meta_price)
            price_text = clean_text(meta_price, 40)

    description = clean_text(og.get("description"), 500) or clean_text(serp_snippet, 500) or None

    if price is None:
        # On cherche un prix dans la partie visible de la page, sans le fabriquer.
        for chunk in re.split(r"(?<=[.!?])\s+|\n", page_text[:2500]):
            if _PRICE_HINT_RE.search(chunk):
                candidate_price, candidate_currency, candidate_text = parse_price_text(chunk)
                if candidate_price is not None:
                    price = candidate_price
                    currency = currency or candidate_currency
                    price_text = candidate_text
                    break

    combined = f"{title} {description or ''} {page_text[:800]}"
    if not _is_commercial(combined, price is not None):
        return []

    images = _images_for(page_url, [], og.get("image"), candidate_images(soup, page_url))
    condition = detect_condition(f"{title} {description or ''}")
    availability = detect_availability(page_text[:1400])

    return [
        RawOffer(
            title=title,
            url=page_url,
            source_id=source_id,
            source_name=source_name,
            site_domain=domain_of(page_url),
            description=description,
            price=price,
            currency=currency or None,
            price_text=price_text,
            brand=None,
            product_model=None,
            condition_text=condition,
            availability_text=availability,
            seller_name=None,
            seller_type=seller_hint,
            images=images,
            contact_phone=contacts.get("phone"),
            contact_email=contacts.get("email"),
            contact_whatsapp=contacts.get("whatsapp"),
            trust=trust,
            stage=stage,
            extraction="html",
        )
    ]


async def extract_offers_from_results(
    fetcher: PageFetcher,
    results: list[SerpResult],
    context: SourceContext,
    *,
    stage: str = "exact",
    max_pages: int | None = None,
) -> tuple[list[RawOffer], list[str]]:
    """Télécharge les pages pertinentes d'une liste SERP et en extrait les offres."""
    if not results:
        return [], []
    budget = max_pages or context.pages_budget
    selected = results[:budget]
    offers: list[RawOffer] = []
    errors: list[str] = []
    semaphore = asyncio.Semaphore(4)

    async def handle(result: SerpResult) -> list[RawOffer]:
        async with semaphore:
            content, _content_type, error = await fetcher.fetch(result.url)
            if error or content is None:
                if error:
                    errors.append(f"{domain_of(result.url)} : {error}")
                return []
            try:
                return offer_from_page(
                    content,
                    result.url,
                    stage=stage,
                    serp_title=result.title,
                    serp_snippet=result.snippet,
                )
            except Exception:  # noqa: BLE001 - une page cassée ne bloque pas la recherche
                errors.append(f"{domain_of(result.url)} : page illisible")
                return []

    for batch_offers in await asyncio.gather(*(handle(result) for result in selected)):
        offers.extend(batch_offers)
    return offers, errors


def describe_missing(value: str | None) -> str:
    """Libellé d'affichage pour une information absente."""
    return truncate(value, 120) or NOT_PROVIDED


def result_is_commercial(result: SerpResult) -> bool:
    """Filtre rapide : le titre/extrait SERP évoque-t-il une vente ?"""
    haystack = fold(f"{result.title} {result.snippet or ''}")
    if any(signal in haystack for signal in COMMERCIAL_SIGNALS):
        return True
    domain = domain_of(result.url)
    return domain in MARKETPLACE_DOMAINS or domain in SITE_CONFIG_BY_DOMAIN


def url_belongs_to_result(url: str, result: SerpResult) -> bool:
    """Vérifie qu'un lien extrait reste sur le même site que le résultat SERP."""
    left = urlparse(url).netloc.lower().replace("www.", "")
    right = urlparse(result.url).netloc.lower().replace("www.", "")
    return bool(left) and left == right
