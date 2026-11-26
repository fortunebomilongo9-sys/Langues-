"""Déduplication des offres et protection contre les doublons.

Deux offres sont considérées identiques si elles pointent vers la même URL
normalisée, ou si elles partagent le même titre normalisé et un prix très
proche sur le même site.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..models import Offer
from .normalize import fold, tokens

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "ref_src", "spm", "affiliate_id", "mc_cid",
}


def normalize_url(url: str) -> str:
    """URL canonique : sans paramètres de suivi ni fragment."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in _TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower().removeprefix("www."), path, "", urlencode(query), "")
    )


def _title_signature(offer: Offer) -> str:
    significant = [token for token in tokens(offer.title) if len(token) > 2]
    return " ".join(significant[:8])


def dedupe_offers(offers: list[Offer]) -> list[Offer]:
    """Supprime les doublons en conservant la meilleure occurrence."""
    ordered = sorted(offers, key=lambda offer: offer.relevance_score, reverse=True)
    seen_urls: set[str] = set()
    seen_signatures: dict[tuple[str, str], float] = {}
    unique: list[Offer] = []

    for offer in ordered:
        url_key = normalize_url(offer.source_url)
        if url_key in seen_urls:
            continue
        signature = (offer.site_domain or "", _title_signature(offer))
        if signature[1]:
            previous_price = seen_signatures.get(signature)
            if previous_price is not None:
                same_price = (
                    offer.price is not None
                    and previous_price > 0
                    and abs(offer.price - previous_price) / max(previous_price, 1.0) < 0.03
                )
                if same_price:
                    continue
            seen_signatures[signature] = offer.price or 0.0
        seen_urls.add(url_key)
        unique.append(offer)

    return unique


def title_signature(title: str) -> str:
    """Signature de titre réutilisable par les tests et les annonces locales."""
    return " ".join(token for token in fold(title).split() if len(token) > 2)
