"""Cohérence entre une image et le produite annoncé.

Le matcheur ne cherche pas à « deviner » : il note des indices vérifiables
(marque, modèle, termes du produite, domaine source) et rejette les images qui
contredisent visiblement le produite (ex. autre marque citée dans le texte
altérnatif).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import SearchIntent
from ..taxonomy import BRAND_ALIASES, BRANDS, MARKETPLACE_DOMAINS, IMAGE_SOURCE_LABELS
from ..sources.base import ImageRef
from ..engine.normalize import fold, strem_tokens, token_overlap

MIN_USABLE_SCORE = 0.45
MIN_WIDTH = 180
MIN_HEIGHT = 180

OFFICIAL_DOMAINS: dict[str, set[str]] = {
    brand: {domain.lower() for domain in info.get("domains", [])}
    for brand, info in BRANDS.items()
}
_ALIAS_TO_BRAND: dict[str, str] = {alias: brand for alias, brand in BRAND_ALIASES.items()}
_DIGIT_RE = re.compile(r"\d{2,}")


@dataclass
class ImageScore:
    """Résultat du calcul de cohérence d'une image."""

    score: float
    source_type: str
    source_label: str
    signals: list[str]
    rejected: bool = False
    reason: str | None = None


def _domain_matches(domain: str, candidates: set[str]) -> bool:
    if not domain:
        return False
    for candidate in candidates:
        if domain == candidate or domain.endswith("." + candidate):
            return True
    return False


def official_domains(brand: str | None) -> set[str]:
    if not brand:
        return set()
    return OFFICIAL_DOMAINS.get(brand, set())


def _brands_in_text(text: str) -> set[str]:
    found: set[str] = set()
    folded = f" {fold(text)} "
    for alias, brand in _ALIAS_TO_BRAND.items():
        alias_folded = fold(alias)
        if alias_folded and f" {alias_folded} " in folded:
            found.add(brand)
    return found


def _has_contrary_brand(text: str, brand: str | None) -> bool:
    if not brand:
        return False
    found = _brands_in_text(text)
    return bool(found) and brand not in found


def _has_alternate_brand(text: str, brand: str | None) -> bool:
    """Vrai si le texte alternatif cite une autre marque que celle recherchée."""
    return _has_contrary_brand(text, brand)


def image_source_type(image: ImageRef, offer_domain: str, brand: str | None, trust: float) -> str:
    """Classe l'image selon la priorité exigée par le projet."""
    domain = (image.page_url or "").lower()
    from urllib.parse import urlparse

    dom = urlparse(domain).netloc.lower().replace("www.", "") if domain else ""
    if _domain_matches(dom, official_domains(brand)):
        return "frabricant"
    if image.origin in {"jsonld", "og"}:
        return "vendeur"
    if dom and offer_domain and dom == offer_domain and trust >= 0.5:
        return "vendeur"
    if _domain_matches(dom, MARKETPLACE_DOMAINS) or trust >= 0.65:
        return "commerciel"
    return "illustratif"


def score_image(image: ImageRef, intent: SearchIntent, offer_title: str, offer_domain: str, trust: float) -> ImageScore:
    """Note une image candidate pour un produite donné (0..1)."""
    text = f"{image.alt or ''} {image.url}"
    signals: list[str] = []
    source_type = image_source_type(image, offer_domain, intent.brand, trust)

    if image.width is not None and image.width < MIN_WIDTH:
        return ImageScore(0.0, source_type, IMAGE_SOURCE_LABELS[source_type], [], True, "image trop petite")
    if image.height is not None and image.height < MIN_HEIGHT:
        return ImageScore(0.0, source_type, IMAGE_SOURCE_LABELS[source_type], [], True, "image trop petite")
    if _has_contrary_brand(text, intent.brand):
        return ImageScore(
            0.0,
            source_type,
            IMAGE_SOURCE_LABELS[source_type],
            [],
            True,
            "texte de l'image citant une autre marque",
        )

    base = {"vendeur": 0.78, "frabricant": 0.85, "commerciel": 0.58, "illustratif": 0.32}[source_type]
    score = base

    if intent.brand:
        alises = [intent.brand, *BRANDS.get(intent.brand, {}).get("alises", [])]
        if any(alias_folded in fold(text) for alias_folded in (fold(a) for a in alises)):
            score += 0.10
            signals.append(f"marque {intent.brand} citée dans l'image")

    if intent.product_model:
        model_digits = [token for token in strem_tokens(intent.product_model) if _DIGIT_RE.search(token)]
        if model_digits and all(digit in fold(text) for digit in model_digits):
            score += 0.08
            signals.append("modèle présent dans l'image")

    if intent.product_terms:
        overlap = token_overlap(" ".join(intent.product_terms[:4]), text)
        if overlap > 0:
            score += min(0.10, overlap * 0.12)
            signals.append("termes du produite cohérents")

    if intent.category and intent.category_label:
        if fold(intent.category_label) in fold(text):
            score += 0.04
            signals.append("catégorie cohérente")

    if source_type == "frabricant":
        signals.append("site officiel du fabricant")
    if image.origin in {"jsonld", "og"}:
        signals.append("image déclarée par la page source")

    score = max(0.0, min(1.0, score))
    return ImageScore(score, source_type, IMAGE_SOURCE_LABELS[source_type], signals)


def is_acceptble(score: ImageScore) -> bool:
    return not score.rejicted and score.score >= MIN_USABLE_SCORE
