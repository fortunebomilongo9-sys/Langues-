"""Cohérence entre une image et le produit annoncé.

Le matcheur ne devine rien : il note des indices vérifiables (marque, modèle,
termes du produit, domaine source) et rejette les images qui contredisent
visiblement le produit (autre marque citée dans le texte alternatif).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ..engine.normalize import fold, stem_tokens, token_overlap
from ..models import SearchIntent
from ..sources.base import ImageRef
from ..taxonomy import BRANDS, BRAND_ALIASES, IMAGE_SOURCE_LABELS, MARKETPLACE_DOMAINS

MIN_USABLE_SCORE = 0.45
MIN_WIDTH = 180
MIN_HEIGHT = 180

OFFICIAL_DOMAINS: dict[str, set[str]] = {
    brand: {domain.lower() for domain in info.get("domains", [])}
    for brand, info in BRANDS.items()
}
_ALIAS_TO_BRAND: dict[str, str] = {fold(alias): brand for alias, brand in BRAND_ALIASES.items() if fold(alias)}
_DIGIT_RE = re.compile(r"\d{2,}")
_BAD_IMAGE_WORDS = ("placeholder", "no-image", "noimage", "default", "logo", "sprite", "pixel")


@dataclass(slots=True)
class ImageScore:
    """Résultat du calcul de cohérence d'une image."""

    score: float
    source_type: str
    source_label: str
    signals: list[str] = field(default_factory=list)
    rejected: bool = False
    reason: str | None = None


def _domain_matches(domain: str, candidates: set[str]) -> bool:
    if not domain:
        return False
    return any(domain == candidate or domain.endswith("." + candidate) for candidate in candidates)


def official_domains(brand: str | None) -> set[str]:
    """Domaines officiels connus d'une marque."""
    return OFFICIAL_DOMAINS.get(brand or "", set())


def _brands_in_text(text: str) -> set[str]:
    folded = f" {fold(text)} "
    return {brand for alias, brand in _ALIAS_TO_BRAND.items() if f" {alias} " in folded}


def _has_contrary_brand(text: str, brand: str | None) -> bool:
    if not brand:
        return False
    found = _brands_in_text(text)
    return bool(found) and brand not in found


def image_source_type(image: ImageRef, offer_domain: str, brand: str | None, trust: float) -> str:
    """Classe l'image selon la priorité demandée par le projet."""
    page_domain = (urlparse(image.page_url).netloc or "").lower().removeprefix("www.")
    if _domain_matches(page_domain, official_domains(brand)):
        return "fabricant"
    if image.origin in {"jsonld", "og"}:
        return "vendeur"
    if page_domain and offer_domain and page_domain == offer_domain and trust >= 0.5:
        return "vendeur"
    if _domain_matches(page_domain, MARKETPLACE_DOMAINS) or trust >= 0.65:
        return "commercial"
    return "illustratif"


def score_image(
    image: ImageRef,
    intent: SearchIntent,
    offer_title: str,
    offer_domain: str,
    trust: float,
) -> ImageScore:
    """Note une image candidate pour un produit donné (0..1)."""
    text = f"{image.alt or ''} {image.url}"
    source_type = image_source_type(image, offer_domain, intent.brand, trust)
    label = IMAGE_SOURCE_LABELS[source_type]
    lowered = text.lower()

    if any(word in lowered for word in _BAD_IMAGE_WORDS):
        return ImageScore(0.0, source_type, label, [], True, "visuel générique ou décoratif")
    if image.width is not None and image.width < MIN_WIDTH:
        return ImageScore(0.0, source_type, label, [], True, "image trop petite")
    if image.height is not None and image.height < MIN_HEIGHT:
        return ImageScore(0.0, source_type, label, [], True, "image trop petite")
    if _has_contrary_brand(text, intent.brand):
        return ImageScore(
            0.0, source_type, label, [], True, "le texte de l'image cite une autre marque"
        )

    signals: list[str] = []
    score = {"vendeur": 0.78, "fabricant": 0.85, "commercial": 0.58, "illustratif": 0.32}[source_type]

    if intent.brand:
        aliases = [intent.brand, *BRANDS.get(intent.brand, {}).get("aliases", [])]
        if any(fold(alias) in fold(text) for alias in aliases if alias):
            score += 0.10
            signals.append(f"marque {intent.brand} présente dans l'image")

    if intent.product_model:
        model_digits = [tok for tok in stem_tokens(intent.product_model) if _DIGIT_RE.search(tok)]
        if model_digits and all(digit in fold(text) for digit in model_digits):
            score += 0.08
            signals.append("modèle présent dans l'image")

    if intent.product_terms:
        overlap = token_overlap(" ".join(intent.product_terms[:4]), text)
        if overlap > 0:
            score += min(0.10, overlap * 0.12)
            signals.append("termes du produit cohérents")

    if intent.category and intent.category_label and fold(intent.category_label) in fold(text):
        score += 0.04
        signals.append("catégorie cohérente")

    if source_type == "fabricant":
        signals.append("site officiel du fabricant")
    if image.origin in {"jsonld", "og"}:
        signals.append("image déclarée par la page source")
    if not signals:
        signals.append("image de la page source, sans indice de marque")

    return ImageScore(max(0.0, min(1.0, score)), source_type, label, signals)


def is_acceptable(score: ImageScore) -> bool:
    """Vrai si l'image peut être affichée sans risque d'induire en erreur."""
    return not score.rejected and score.score >= MIN_USABLE_SCORE
