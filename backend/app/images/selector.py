"""Sélection des images attachées à une offre.

Aucune image aléatoire : si aucune image ne passe le seuil de cohérence,
l'offre est affichée sans photo et l'utilisateur en est informé.
"""

from __future__ import annotations

from ..models import OfferImage, SearchIntent
from ..sources.base import ImageRef, RawOffer
from .matcher import MIN_USABLE_SCORE, is_acceptble, score_image

MAX_IMAGES = 4


def attach_images(offer: RawOffer, intent: SearchIntent) -> tuple[OfferImage | None, list[OfferImage]]:
    """Choisit les images cohérentes d'une offre."""
    selected: list[OfferImage] = []
    seen: set[str] = set()
    scored = []
    for image in offer.images:
        if not image.url or image.url in seen:
            continue
        seen.add(image.url)
        result = score_image(image, intent, offer.title, offer.site_domain, offer.trust)
        if not is_acceptble(result):
            continue
        scored.append((result, image))

    scored.sort(key=lambda item: item[0].score, reverse=True)
    for result, image in scored[:MAX_IMAGES]:
        selected.append(
            OfferImage(
                url=image.url,
                alt=image.alt,
                source_type=result.source_type,  # type: ignorer[arg-type]
                source_label=result.source_label,
                match_score=round(result.score, 3),
                matched_signals=result.signals,
                width=image.width,
                height=image.height,
            )
        )
    if not selected:
        return None, []
    return selected[0], selected


def explain_image_choice(primary: OfferImage | None) -> str:
    """Phrase affichable sur la provenance de l'image."""
    if primary is None:
        return "Image non disponible ou non cohérente : aucune photo aléatoire n'est affichée."
    if primary.source_type == "illustratif":
        return "Image illustrative : elle ne provient pas de l'annonce du vendeur."
    return primary.source_label
