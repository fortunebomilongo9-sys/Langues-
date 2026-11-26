"""Composition d'une fiche commerciale normalisée.

Transforme une offre brute (issue du web ou d'une annonce locale) en objet
`Offer` prêt pour l'API : prix formaté, état, disponibilité, commune,
provenance de l'image et contact vérifiable uniquement.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from ..images.selector import attach_images
from ..models import ContactInfo, Listing, Offer, SearchIntent
from ..sources.base import RawOffer
from ..sources.html_utils import parse_price_text
from ..taxonomy import COMMUNE_ALIASES, COMMUNES, CONDITION_LABELS, NOT_PROVIDED
from .normalize import fold, truncate

CONDITIONS = {"neuf", "occasion", "reconditionne", "inconnu"}
_CURRENCY_SYMBOLS = {"USD": "$", "CDF": "FC", "EUR": "€"}
_NUMBER_RE_DIGITS = 3


def detect_commune(text: str | None) -> str | None:
    """Identifie une commune de Kinshasa citée dans un texte, sans l'inventer."""
    if not text:
        return None
    haystack = f" {fold(text)} "
    for alias, commune in COMMUNE_ALIASES.items():
        folded = fold(alias)
        if folded and f" {folded} " in haystack:
            return commune
    for commune in COMMUNES:
        if f" {fold(commune)} " in haystack:
            return commune
    return None


def detect_city(text: str | None) -> str | None:
    """Ville détectée (Kinshasa par défaut si une commune est trouvée)."""
    if not text:
        return None
    haystack = fold(text)
    for city in ("kinshasa", "lubumbashi", "goma", "matadi", "bukavu", "kolwezi", "mbuji-mayi"):
        if city in haystack:
            return city.title()
    return None


def format_price(price: float | None, currency: str | None) -> str:
    """Prix affichable, ou « Non renseigné » si le prix est absent."""
    if price is None:
        return NOT_PROVIDED
    whole = int(round(price))
    grouped = f"{whole:,}".replace(",", " ")
    code = (currency or "").upper()
    symbol = _CURRENCY_SYMBOLS.get(code)
    return f"{grouped} {code}" if code else f"{grouped} {symbol or ''}".strip()


def normalize_condition(value: str | None) -> str:
    """Ramène un libellé d'état à l'énumération interne."""
    folded = fold(value)
    if not folded:
        return "inconnu"
    if "recondition" in folded or "refurb" in folded:
        return "reconditionne"
    if "occasion" in folded or "usage" in folded or "used" in folded:
        return "occasion"
    if "neuf" in folded or "new" in folded:
        return "neuf"
    return folded if folded in CONDITIONS else "inconnu"


def _offer_id(url: str, title: str) -> str:
    digest = hashlib.sha1(f"{url}|{fold(title)[:80]}".encode("utf-8")).hexdigest()
    return f"web-{digest[:14]}"


def _contact(raw: RawOffer) -> ContactInfo | None:
    """Contact public trouvé sur la page source ; jamais inventé."""
    if raw.contact_whatsapp:
        return ContactInfo(
            type="whatsapp",
            value=raw.contact_whatsapp,
            verified=False,
            note="Numéro publié par la source, non vérifié par JF MARKET",
        )
    if raw.contact_phone:
        return ContactInfo(
            type="telephone",
            value=raw.contact_phone,
            verified=False,
            note="Numéro publié par la source, non vérifié par JF MARKET",
        )
    if raw.contact_email:
        return ContactInfo(
            type="email",
            value=raw.contact_email,
            verified=False,
            note="Adresse publiée par la source, non vérifiée par JF MARKET",
        )
    return None


def compose_offer(raw: RawOffer, intent: SearchIntent) -> Offer:
    """Construit une fiche `Offer` complète à partir d'une offre brute."""
    commune = detect_commune(raw.location_text) or detect_commune(raw.title) or detect_commune(raw.description)
    city = detect_city(raw.location_text) or ("Kinshasa" if commune else None)
    primary_image, images = attach_images(raw, intent)
    condition = normalize_condition(raw.condition_text)
    price, currency = raw.price, raw.currency
    if price is None:
        # Prix explicitement publié dans l'annonce : on le lit, on ne l'invente jamais.
        for text in (raw.price_text, raw.description):
            amount, detected, _ = parse_price_text(text)
            if amount is not None:
                price, currency = amount, currency or detected
                break
    return Offer(
        id=_offer_id(raw.url, raw.title),
        title=truncate(raw.title, 160) or NOT_PROVIDED,
        description=truncate(raw.description, 600) if raw.description else None,
        brand=raw.brand,
        product_model=raw.product_model,
        price=price,
        currency=currency,
        price_display=format_price(price, currency),
        condition=condition,  # type: ignore[arg-type]
        availability=(raw.availability_text or "inconnu"),  # type: ignore[arg-type]
        seller_name=raw.seller_name,
        seller_type=raw.seller_type,
        location=raw.location_text or commune,
        commune=commune,
        city=city,
        source_id=raw.source_id,
        source_name=raw.source_name,
        source_url=raw.url,
        site_domain=raw.site_domain,
        image=primary_image,
        images=images,
        contact=_contact(raw),
        published_at=raw.published_at,
        stage=raw.stage,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def compose_offers(raws: list[RawOffer], intent: SearchIntent) -> list[Offer]:
    """Compose une liste d'offres en ignorant les entrées inexploitables."""
    offers: list[Offer] = []
    for raw in raws:
        if not raw.title or not raw.url:
            continue
        try:
            offers.append(compose_offer(raw, intent))
        except Exception:  # noqa: BLE001 - une offre cassée ne bloque pas les autres
            continue
    return offers


def offer_from_listing(listing: Listing, intent: SearchIntent) -> Offer:
    """Transforme une annonce publiée dans JF MARKET en fiche de résultat."""
    commune = listing.commune or detect_commune(f"{listing.title} {listing.description}")
    images = []
    primary = None
    for index, url in enumerate(listing.images[:4]):
        from ..models import OfferImage

        image = OfferImage(
            url=url,
            alt=listing.title,
            source_type="vendeur",
            source_label="Image publiée par le vendeur",
            match_score=0.95,
            matched_signals=["image téléversée par le vendeur", "annonce vérifiée par compte"],
        )
        images.append(image)
        if index == 0:
            primary = image
    contact = None
    if listing.contact_whatsapp:
        contact = ContactInfo(type="whatsapp", value=listing.contact_whatsapp, verified=True, note="Fourni par le vendeur dans son annonce")
    elif listing.contact_phone:
        contact = ContactInfo(type="telephone", value=listing.contact_phone, verified=True, note="Fourni par le vendeur dans son annonce")
    elif listing.contact_email:
        contact = ContactInfo(type="email", value=listing.contact_email, verified=True, note="Fourni par le vendeur dans son annonce")
    return Offer(
        id=f"local-{listing.id}",
        title=listing.title,
        description=listing.description or None,
        brand=listing.brand,
        product_model=listing.product_model,
        price=listing.price,
        currency=listing.currency,
        price_display=format_price(listing.price, listing.currency),
        condition=listing.condition,
        availability="disponible",
        seller_name=listing.seller_name,
        seller_type=listing.seller_type,
        location=commune or listing.city,
        commune=commune,
        city=listing.city,
        source_id="jfmarket",
        source_name="Annonce JF MARKET",
        source_url=f"/annonce/{listing.id}",
        site_domain="jfmarket",
        image=primary,
        images=images,
        contact=contact,
        published_at=listing.created_at,
        is_user_listing=True,
        stage="annonce-locale",
    )
