"""Utilitaires d'analyse HTML : JSON-LD, OpenGraph, prix, contacts.

Le parseur est volontairement défensif : pages tronquées, JSON invalide,
balises exotiques et contenus malveillants ne doivent jamais faire échouer une
recherche complète.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..engine.normalize import fold, parse_amount, truncate
from ..taxonomy import CURRENCY_ALIASES, NOT_PROVIDED

MAX_HTML_CHARS = 2_500_000
MAX_JSONLD_NODES = 400

_PRICE_PATTERN = re.compile(
    r"(?:(us\s?\$|usd|cdf|fc|€|eur|\$)\s*([\d][\d\s.,]*))"
    r"|(?:([\d][\d\s.,]*)\s*(us\s?\$|usd|cdf|fc|€|eur|\$|francs? congolais|francs?))",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"(?:\+?243|0)\s?\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}|\+\d{9,15}"
)
_EMAIL_PATTERN = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.IGNORECASE)
_WHATSAPP_PATTERN = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\+?\d{8,15})")
_JUNK_IMAGE_PATTERN = re.compile(
    r"(sprite|placeholder|blank|pixel|tracking|loader|logo[-_]?site|favicon|avatar|1x1|spacer)",
    re.IGNORECASE,
)
_CONDITION_NEW = {"newcondition", "new", "neuf", "neuve"}
_CONDITION_USED = {"usedcondition", "used", "occasion", "usag e", "second hand"}
_CONDITION_REFURB = {"refurbishedcondition", "refurbished", "reconditionne", "renewed"}


def decode_html(content: bytes | str) -> str:
    """Décode une page en limitant sa taille (protection mémoire)."""
    if isinstance(content, bytes):
        for encoding in ("utf-8", "latin-1"):
            try:
                return content.decode(encoding, errors="replace")[:MAX_HTML_CHARS]
            except (LookupError, UnicodeDecodeError):
                continue
        return content.decode("utf-8", errors="replace")[:MAX_HTML_CHARS]
    return content[:MAX_HTML_CHARS]


def make_soup(html: str | bytes) -> BeautifulSoup:
    """Construit un arbre BeautifulSoup tolérant."""
    return BeautifulSoup(decode_html(html), "html.parser")


def clean_text(value: str | None, limit: int = 400) -> str:
    """Texte affichable, sans espaces superflus."""
    return truncate(value, limit)


def domain_of(url: str | None) -> str:
    """Domaine normalisé (sans ``www.``) d'une URL."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def sanitize_url(url: str | None, base: str | None = None) -> str | None:
    """N'accepte que des URL http(s) absolues."""
    if not url:
        return None
    candidate = url.strip()
    if base:
        try:
            candidate = urljoin(base, candidate)
        except ValueError:
            return None
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if len(candidate) > 1500:
        return None
    return candidate.split("#")[0]


def currency_from_token(token: str | None) -> str | None:
    """Devise à partir d'un symbole ou d'un mot."""
    if not token:
        return None
    cleaned = " ".join(fold(token).split())
    if cleaned in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[cleaned]
    if "us" in cleaned and "$" in token:
        return "USD"
    return None


def parse_price_text(text: str | None) -> tuple[float | None, str | None, str | None]:
    """Extrait (montant, devise, texte brut) d'un libellé de prix."""
    if not text:
        return None, None, None
    for match in _PRICE_PATTERN.finditer(text):
        groups = match.groups()
        if groups[0]:
            amount = parse_amount(groups[1])
            currency = currency_from_token(groups[0])
        else:
            amount = parse_amount(groups[2])
            currency = currency_from_token(groups[3])
        if amount is not None and amount > 0:
            return amount, currency, truncate(match.group(0), 40)
    return None, None, None


def detect_condition(text: str | None) -> str:
    """État du produit à partir d'un texte libre."""
    folded = fold(text)
    if not folded:
        return "inconnu"
    if any(word in folded for word in ("reconditionne", "refurb", "renewed")):
        return "reconditionne"
    if any(word in folded for word in ("occasion", "occase", "usag", "second hand", "okaz")):
        return "occasion"
    if any(word in folded for word in ("neuf", "neuve", "brand new", "scelle", "emballe")):
        return "neuf"
    compacted = folded.replace(" ", "")
    if compacted in _CONDITION_NEW:
        return "neuf"
    if compacted in _CONDITION_USED:
        return "occasion"
    if compacted in _CONDITION_REFURB:
        return "reconditionne"
    return "inconnu"


def detect_availability(text: str | None) -> str:
    """Disponibilité annoncée par la source."""
    if not text:
        return "inconnu"
    folded = fold(text)
    if any(
        word in folded
        for word in ("outofstock", "out of stock", "rupture", "epuise", "soldout", "sold out")
    ):
        return "non confirmee"
    if any(
        word in folded
        for word in ("instock", "in stock", "disponible", "en stock", "ajouter au panier", "add to cart")
    ):
        return "disponible"
    return "inconnu"


def find_contacts(text: str | None) -> dict[str, str]:
    """Contacts publics explicitement présents dans la page (jamais inventés)."""
    contacts: dict[str, str] = {}
    if not text:
        return contacts
    compacted = " ".join(text.split())
    phone = _PHONE_PATTERN.search(compacted)
    if phone:
        digits = re.sub(r"[^\d+]", "", phone.group(0))
        if 8 <= len(re.sub(r"\D", "", digits)) <= 15:
            contacts["phone"] = digits
    whatsapp = _WHATSAPP_PATTERN.search(compacted)
    if whatsapp:
        contacts["whatsapp"] = "+" + re.sub(r"\D", "", whatsapp.group(1))
    email = _EMAIL_PATTERN.search(compacted)
    if email:
        contacts["email"] = email.group(0)
    return contacts


def extract_page_text(soup: BeautifulSoup, limit: int = 6000) -> str:
    """Texte lisible d'une page (sans scripts ni styles)."""
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    return truncate(soup.get_text(" ", strip=True), limit)


def _safe_json(raw: str) -> Any | None:
    """Charge un bloc JSON-LD en tolérant les erreurs fréquentes."""
    candidate = raw.strip()
    if not candidate:
        return None
    for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            return json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def iter_jsonld_nodes(soup: BeautifulSoup) -> Iterable[dict]:
    """Parcourt tous les noeuds JSON-LD d'une page."""
    count = 0
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        data = _safe_json(script.string or script.get_text() or "")
        if data is None:
            continue
        stack: list[Any] = [data]
        while stack and count < MAX_JSONLD_NODES:
            current = stack.pop()
            count += 1
            if isinstance(current, list):
                stack.extend(current)
                continue
            if not isinstance(current, dict):
                continue
            yield current
            graph = current.get("@graph")
            if isinstance(graph, (list, dict)):
                stack.append(graph)
            for key in ("itemListElement", "item", "mainEntity", "hasOfferCatalog"):
                nested = current.get(key)
                if isinstance(nested, (list, dict)):
                    stack.append(nested)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _name_of(value: Any) -> str | None:
    if isinstance(value, dict):
        name = value.get("name") or value.get("legalName")
        return clean_text(name, 120) if isinstance(name, str) else None
    if isinstance(value, str):
        return clean_text(value, 120)
    return None


def _images_from_jsonld(value: Any) -> list[str]:
    urls: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            candidate = item.get("url") or item.get("contentUrl")
            if isinstance(candidate, str):
                urls.append(candidate)
    return urls


def products_from_jsonld(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """Produits structurés (schema.org) trouvés dans la page."""
    products: list[dict] = []
    seen: set[str] = set()
    for node in iter_jsonld_nodes(soup):
        raw_type = node.get("@type")
        types = [str(item).lower() for item in _as_list(raw_type)]
        if not any("product" in item for item in types):
            continue
        name = _name_of(node.get("name"))
        if not name:
            continue
        offers = node.get("offers") or node.get("offer")
        offer_node: dict = {}
        for candidate in _as_list(offers):
            if isinstance(candidate, dict):
                offer_node = candidate
                break
        price = offer_node.get("price") or offer_node.get("lowPrice") or node.get("price")
        currency = offer_node.get("priceCurrency") or node.get("priceCurrency")
        availability = offer_node.get("availability") or node.get("availability")
        condition = offer_node.get("itemCondition") or node.get("itemCondition")
        seller = offer_node.get("seller") or node.get("seller") or node.get("brand")
        url = (
            offer_node.get("url")
            or node.get("url")
            or _as_list(node.get("mainEntityOfPage"))[0]
            if isinstance(_as_list(node.get("mainEntityOfPage"))[0] if _as_list(node.get("mainEntityOfPage")) else None, str)
            else None
        )
        images = [
            image
            for image in (
                sanitize_url(item, page_url) for item in _images_from_jsonld(node.get("image"))
            )
            if image
        ]
        amount = None
        if isinstance(price, (int, float)):
            amount = float(price)
        elif isinstance(price, str):
            amount, _currency_from_price, _ = parse_price_text(price)
            currency = currency or _currency_from_price
        key = f"{fold(name)}|{amount}"
        if key in seen:
            continue
        seen.add(key)
        products.append(
            {
                "title": name,
                "description": clean_text(node.get("description"), 500) or None,
                "price": amount,
                "currency": str(currency).upper()[:3] if isinstance(currency, str) else None,
                "availability": str(availability) if availability else None,
                "condition": str(condition) if condition else None,
                "seller_name": _name_of(seller),
                "brand": _name_of(node.get("brand")),
                "sku": node.get("sku") or node.get("mpn"),
                "images": images,
                "url": sanitize_url(url, page_url) if isinstance(url, str) else None,
                "published_at": node.get("datePublished") if isinstance(node.get("datePublished"), str) else None,
            }
        )
    return products


def open_graph(soup: BeautifulSoup, page_url: str) -> dict[str, Any]:
    """Métadonnées OpenGraph / TwitterCard de la page."""
    meta: dict[str, Any] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if not key or not content:
            continue
        key = key.strip().lower()
        if key in {
            "og:title", "og:description", "og:image", "og:site_name", "og:price:amount",
            "og:price:currency", "product:price:amount", "product:price:currency",
            "twitter:image", "twitter:title", "twitter:description",
        }:
            meta.setdefault(key, content.strip())
    image = meta.get("og:image") or meta.get("twitter:image")
    if image:
        meta["image"] = sanitize_url(image, page_url)
    title = soup.title.get_text(strip=True) if soup.title and soup.title.string else None
    meta.setdefault("title", clean_text(meta.get("og:title") or title, 200))
    return meta


def candidate_images(
    soup: BeautifulSoup, page_url: str, limit: int = 12
) -> list[tuple[str, str | None]]:
    """Images exploitables d'une page, avec leur texte alternatif."""
    found: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        raw_src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        srcset = img.get("srcset") or img.get("data-srcset")
        if not raw_src and srcset:
            raw_src = srcset.split(",")[-1].strip().split(" ")[0]
        url = sanitize_url(raw_src, page_url)
        if not url or url in seen:
            continue
        if url.lower().startswith("data:"):
            continue
        if _JUNK_IMAGE_PATTERN.search(url):
            continue
        if domain_of(url) in {"facebook.com", "google-analytics.com", "doubleclick.net"}:
            continue
        alt = clean_text(img.get("alt"), 160) or None
        seen.add(url)
        found.append((url, alt))
        if len(found) >= limit:
            break
    return found


def meta_content(soup: BeautifulSoup, *, names: tuple[str, ...] = (), props: tuple[str, ...] = ()) -> str | None:
    """Premier contenu meta correspondant."""
    for name in names:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    for prop in props:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def not_provided(value: str | None) -> str:
    """Libellé commun pour une information absente."""
    return value.strip() if value and value.strip() else NOT_PROVIDED
