"""Sélection des images attachées à une offre.

Aucune image aléatoire : si aucune image ne passe le seuil de cohérence,
l'offre est affichée sans photo et l'utilisateur en est informé.
"""

from __future__ import annotations

from ..models import OfferImage, SearchIntent
from ..sources.base import RawOffer
from .matcher import is_acceptable, score_image

MAX_IMAGES = 4


def attach_images(offer: RawOffer, intent: SearchIntent) -> tuple[OfferImage | None, list[OfferImage]]:
    """Choisit les images cohérentes d'une offre (la première est la principale)."""
    scored = []
    seen: set[str] = set()
    for image in offer.images:
        if not image.url or image.url in seen:
            continue
        seen.add(image.url)
        result = score_image(image, intent, offer.title, offer.site_domain, offer.trust)
        if not is_acceptable(result):
            continue
        scored.append((result, image))

    scored.sort(key=lambda item: item[0].score, reverse=True)
    selected = [
        OfferImage(
            url=image.url,
            alt=image.alt,
            source_type=result.source_type,  # type: ignore[arg-type]
            source_label=result.source_label,
            match_score=round(result.score, 3),
            matched_signals=result.signals,
            width=image.width,
            height=image.height,
        )
        for result, image in scored[:MAX_IMAGES]
    ]
    if not selected:
        return None, []
    return selected[0], selected


def explain_image_choice(primary: OfferImage | None) -> str:
    """Phrase affichable sur la provenance de l'image."""
    if primary is None:
        return "Aucune image cohérente trouvée : aucune photo aléatoire n'est affichée."
    if primary.source_type == "illustratif":
        return "Image illustrative : elle ne provient pas de l'annonce du vendeur."
    return primary.source_label
