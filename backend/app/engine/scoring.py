"""Pertinence des offres et application des filtres.

Le classement privilégie la cohérence réelle (marque, modèle, budget, état,
commune) plutôt que le nombre de résultats.
"""

from __future__ import annotations

from ..config import settings
from ..models import Offer, SearchFilters, SearchIntent
from ..taxonomy import BRANDS, CATEGORY_BY_ID
from .normalize import fold, token_overlap

MIN_RELEVANCE = 0.22
_EUR_USD = 1.08


def to_usd(price: float | None, currency: str | None) -> float | None:
    """Convertit un prix en USD pour comparer un budget (taux indicatif)."""
    if price is None:
        return None
    code = (currency or "USD").upper()
    if code in {"USD", "$"}:
        return price
    if code in {"CDF", "FC", "FCFA"}:
        return price / max(settings.usd_cdf_rate, 1.0)
    if code in {"EUR", "€"}:
        return price * _EUR_USD
    return price


def budget_bounds(intent: SearchIntent) -> tuple[float | None, float | None]:
    """Bornes de budget exprimées en USD (aucune borne inventée)."""
    if intent.budget_usd is not None:
        return None, intent.budget_usd
    return to_usd(intent.price_min, intent.currency), to_usd(intent.price_max, intent.currency)


def _brand_in_text(brand: str, text: str) -> bool:
    folded = fold(text)
    aliases = [brand, *BRANDS.get(brand, {}).get("aliases", [])]
    return any(fold(alias) and fold(alias) in folded for alias in aliases)


def _other_brand_in_text(brand: str, text: str) -> str | None:
    folded = fold(text)
    for other in BRANDS:
        if other == brand:
            continue
        if fold(other) in folded:
            return other
    return None


def _category_keywords(category: str | None) -> list[str]:
    if not category:
        return []
    info = CATEGORY_BY_ID.get(category)
    if not info:
        return []
    keywords = list(info.get("keywords", []))
    for sub in info.get("subcategories", []):
        keywords.extend(sub.get("keywords", []))
    return keywords


def score_offer(offer: Offer, intent: SearchIntent) -> tuple[float, list[str]]:
    """Note de pertinence (0..1) et raisons lisibles par l'utilisateur."""
    text = f"{offer.title} {offer.description or ''}"
    score = 0.30
    reasons: list[str] = []

    if intent.product_terms:
        overlap = token_overlap(" ".join(intent.product_terms), text)
        if overlap > 0:
            score += min(0.28, overlap * 0.3)
            reasons.append("produit correspondant à la recherche")
        else:
            score -= 0.18

    if intent.brand:
        if offer.brand and offer.brand == intent.brand:
            score += 0.16
            reasons.append(f"marque {intent.brand} confirmée")
        elif _brand_in_text(intent.brand, text):
            score += 0.12
            reasons.append(f"marque {intent.brand} citée dans l'annonce")
        else:
            other = _other_brand_in_text(intent.brand, text)
            if other:
                score -= 0.35
                reasons.append(f"annonce d'une autre marque ({other})")
            else:
                score -= 0.12

    if intent.product_model:
        model_tokens = [token for token in fold(intent.product_model).split() if len(token) > 1]
        if model_tokens and all(token in fold(text) for token in model_tokens):
            score += 0.12
            reasons.append("modèle correspondant")

    keywords = _category_keywords(intent.category)
    if keywords and any(fold(keyword) in fold(text) for keyword in keywords):
        score += 0.06
        reasons.append("catégorie cohérente")

    price_usd = to_usd(offer.price, offer.currency)
    _, max_usd = budget_bounds(intent)
    min_usd, _ = budget_bounds(intent)
    if price_usd is not None and max_usd is not None:
        if price_usd <= max_usd:
            score += 0.14
            reasons.append("dans le budget indiqué")
        elif price_usd <= max_usd * 1.15:
            score += 0.06
            reasons.append("légèrement au-dessus du budget")
        elif price_usd > max_usd * 1.4:
            score -= 0.12
            reasons.append("au-dessus du budget")
    if price_usd is not None and min_usd is not None and price_usd < min_usd:
        score -= 0.05

    if intent.condition != "inconnu":
        if offer.condition == intent.condition:
            score += 0.06
            reasons.append(f"état {intent.condition}")
        elif offer.condition != "inconnu":
            score -= 0.04

    if intent.commune and offer.commune and offer.commune == intent.commune:
        score += 0.06
        reasons.append(f"commune {intent.commune}")

    if offer.image is not None and offer.image.source_type != "illustratif":
        score += 0.04

    if offer.is_user_listing:
        score += 0.05
        reasons.append("annonce publiée sur JF MARKET")

    return max(0.0, min(1.0, score)), reasons


def rank_offers(offers: list[Offer], intent: SearchIntent, *, keep_weak: bool = False) -> list[Offer]:
    """Calcule la pertinence et écarte les offres hors sujet."""
    scored: list[Offer] = []
    for offer in offers:
        score, reasons = score_offer(offer, intent)
        offer.relevance_score = round(score, 3)
        offer.relevance_reasons = reasons
        if keep_weak or score >= MIN_RELEVANCE:
            scored.append(offer)
    scored.sort(key=lambda item: item.relevance_score, reverse=True)
    return scored


def apply_filters(offers: list[Offer], filters: SearchFilters, intent: SearchIntent) -> list[Offer]:
    """Applique les filtres utilisateur côté serveur."""
    selected: list[Offer] = []
    for offer in offers:
        price_usd = to_usd(offer.price, offer.currency)
        if filters.price_min is not None and price_usd is not None and price_usd < filters.price_min:
            continue
        if filters.price_max is not None and price_usd is not None and price_usd > filters.price_max:
            continue
        if filters.brand:
            haystack = f"{offer.brand or ''} {offer.title}"
            if not _brand_in_text(filters.brand, haystack):
                continue
        if filters.category:
            keywords = _category_keywords(filters.category)
            if keywords and not any(fold(word) in fold(offer.title) for word in keywords):
                continue
        if filters.condition and offer.condition != filters.condition:
            continue
        if filters.seller_type and offer.seller_type != filters.seller_type:
            continue
        if filters.commune and (offer.commune or "").lower() != filters.commune.lower():
            continue
        if filters.only_with_image and offer.image is None:
            continue
        selected.append(offer)
    return sort_offers(selected, filters.sort)


def sort_offers(offers: list[Offer], order: str) -> list[Offer]:
    """Trie les offres selon le mode demandé."""
    if order == "prix_asc":
        return sorted(offers, key=lambda offer: (offer.price is None, offer.price or 0.0))
    if order == "prix_desc":
        return sorted(offers, key=lambda offer: (offer.price is None, -(offer.price or 0.0)))
    if order == "recent":
        return sorted(offers, key=lambda offer: offer.published_at or offer.fetched_at, reverse=True)
    return sorted(offers, key=lambda offer: offer.relevance_score, reverse=True)


def search_suggestions(intent: SearchIntent) -> list[str]:
    """Suggestions affichables quand aucun résultat fiable n'est trouvé."""
    suggestions: list[str] = []
    if intent.brand and intent.category_label:
        suggestions.append(f"{intent.brand} {intent.category_label}")
    if intent.product_terms:
        suggestions.append(" ".join(intent.product_terms[:3]))
    if intent.brand:
        suggestions.append(f"{intent.brand} occasion Kinshasa")
    suggestions.append("téléphone Samsung Kinshasa")
    seen: set[str] = set()
    unique = [item for item in suggestions if item and not (item in seen or seen.add(item))]
    return unique[:4]
