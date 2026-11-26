"""Modèles de données de JF MARKET (Pydantic v2).

Ces schémas sont le contrat public de l'API : le frontend ne reçoit jamais
d'objet brut issu du scraping, uniquement ces structures normalisées.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Condition = Literal["neuf", "occasion", "reconditionne", "inconnu"]
SellerType = Literal["boutique", "particulier", "inconnu"]
ImageSourceType = Literal["vendeur", "fabricant", "commercial", "illustratif"]
Availability = Literal["disponible", "non confirmee", "inconnu"]
SortOrder = Literal["pertinence", "prix_asc", "prix_desc", "recent"]
SourceState = Literal["ok", "vide", "echec", "desactive"]
UserRole = Literal["acheteur", "vendeur"]

NOT_PROVIDED = "Non renseigné"


def utcnow() -> str:
    """Horodatage ISO 8601 UTC (seconde)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SearchIntent(BaseModel):
    """Résultat de l'analyse intelligente d'une requête utilisateur."""

    raw_query: str
    normalized_query: str = ""
    product_terms: list[str] = Field(default_factory=list)
    expanded_terms: list[str] = Field(default_factory=list)
    corrections: dict[str, str] = Field(default_factory=dict)
    brand: str | None = None
    product_model: str | None = None
    product_reference: str | None = None
    category: str | None = None
    category_label: str | None = None
    subcategory: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    budget_usd: float | None = None
    condition: Condition = "inconnu"
    commune: str | None = None
    city: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class OfferImage(BaseModel):
    """Image associée à une offre, avec sa provenance et son score de cohérence."""

    url: str
    alt: str | None = None
    source_type: ImageSourceType = "illustratif"
    source_label: str = NOT_PROVIDED
    match_score: float = 0.0
    matched_signals: list[str] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None


class ContactInfo(BaseModel):
    """Moyen de contact public trouvé sur la page source (jamais inventé)."""

    type: Literal["telephone", "whatsapp", "email", "page"]
    value: str
    verified: bool = False
    note: str | None = None


class Offer(BaseModel):
    """Fiche commerciale normalisée."""

    id: str
    title: str
    description: str | None = None
    brand: str | None = None
    product_model: str | None = None
    price: float | None = None
    currency: str | None = None
    price_display: str = NOT_PROVIDED
    condition: Condition = "inconnu"
    availability: Availability = "inconnu"
    seller_name: str | None = None
    seller_type: SellerType = "inconnu"
    location: str | None = None
    commune: str | None = None
    city: str | None = None
    source_id: str
    source_name: str
    source_url: str
    site_domain: str = ""
    image: OfferImage | None = None
    images: list[OfferImage] = Field(default_factory=list)
    contact: ContactInfo | None = None
    relevance_score: float = 0.0
    relevance_reasons: list[str] = Field(default_factory=list)
    published_at: str | None = None
    stage: str = "exact"
    is_user_listing: bool = False
    fetched_at: str = Field(default_factory=utcnow)


class SearchFilters(BaseModel):
    """Filtres appliqués côté serveur après collecte."""

    price_min: float | None = None
    price_max: float | None = None
    brand: str | None = None
    category: str | None = None
    condition: Condition | None = None
    seller_type: SellerType | None = None
    commune: str | None = None
    only_with_image: bool = False
    sort: SortOrder = "pertinence"

    @field_validator("price_min", "price_max")
    @classmethod
    def _positive(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Le prix ne peut pas être négatif")
        return value


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    filters: SearchFilters | None = None
    limit: int = Field(default=24, ge=1, le=60)
    fresh: bool = False

    @field_validator("query")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Requête trop courte")
        return cleaned


class StageReport(BaseModel):
    """Trace d'une étape de la recherche progressive."""

    stage: str
    label: str
    query_used: str
    offers_found: int = 0
    note: str | None = None


class SourceStatus(BaseModel):
    """État d'une source consultée pendant la recherche."""

    id: str
    label: str
    status: SourceState = "ok"
    offers: int = 0
    detail: str | None = None


class SearchResponse(BaseModel):
    query: str
    intent: SearchIntent
    offers: list[Offer] = Field(default_factory=list)
    count: int = 0
    stages: list[StageReport] = Field(default_factory=list)
    sources: list[SourceStatus] = Field(default_factory=list)
    sources_failed: int = 0
    message: str | None = None
    network_ok: bool = True
    cached: bool = False
    took_ms: int = 0
    filters: SearchFilters = Field(default_factory=SearchFilters)
    generated_at: str = Field(default_factory=utcnow)


class ImageSearchResponse(BaseModel):
    query_guess: str | None = None
    method: str
    intent: SearchIntent | None = None
    offers: list[Offer] = Field(default_factory=list)
    count: int = 0
    message: str | None = None
    network_ok: bool = True


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
    time: str = Field(default_factory=utcnow)
    auth_provider: str
    storage_backend: str
    database_backend: str
    sources: list[SourceStatus] = Field(default_factory=list)
    image_search: str
    firebase_configured: bool = False
    serpapi_configured: bool = False


# --------------------------------------------------------------------------
# Comptes utilisateurs
# --------------------------------------------------------------------------


class SignUpRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=6, max_length=200)
    role: UserRole = "acheteur"
    display_name: str = Field(min_length=2, max_length=80)
    phone: str | None = Field(default=None, max_length=30)
    # Un vendeur déclare lui-même s'il est une boutique ou un particulier.
    seller_type: SellerType = "particulier"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
            raise ValueError("Adresse e-mail invalide")
        return cleaned


class SignInRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class AuthUser(BaseModel):
    uid: str
    email: str
    role: UserRole = "acheteur"
    display_name: str
    seller_type: SellerType = "particulier"
    created_at: str = Field(default_factory=utcnow)


class AuthResponse(BaseModel):
    token: str
    user: AuthUser
    provider: str


# --------------------------------------------------------------------------
# Annonces publiées par les vendeurs
# --------------------------------------------------------------------------


class ListingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=4000)
    price: float = Field(ge=0, le=1_000_000_000)
    currency: str = Field(default="USD", max_length=8)
    condition: Condition = "inconnu"
    category: str | None = Field(default=None, max_length=40)
    brand: str | None = Field(default=None, max_length=60)
    product_model: str | None = Field(default=None, max_length=80)
    commune: str | None = Field(default=None, max_length=60)
    city: str = Field(default="Kinshasa", max_length=60)
    images: list[str] = Field(default_factory=list, max_length=6)
    contact_phone: str | None = Field(default=None, max_length=30)
    contact_whatsapp: str | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=200)


class ListingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    price: float | None = Field(default=None, ge=0, le=1_000_000_000)
    currency: str | None = Field(default=None, max_length=8)
    condition: Condition | None = None
    category: str | None = Field(default=None, max_length=40)
    brand: str | None = Field(default=None, max_length=60)
    product_model: str | None = Field(default=None, max_length=80)
    commune: str | None = Field(default=None, max_length=60)
    city: str | None = Field(default=None, max_length=60)
    images: list[str] | None = Field(default=None, max_length=6)
    contact_phone: str | None = Field(default=None, max_length=30)
    contact_whatsapp: str | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=200)
    status: Literal["publie", "archive"] | None = None


class Listing(BaseModel):
    id: str
    seller_uid: str
    seller_name: str
    seller_type: SellerType = "particulier"
    title: str
    description: str = ""
    price: float
    currency: str = "USD"
    condition: Condition = "inconnu"
    category: str | None = None
    brand: str | None = None
    product_model: str | None = None
    commune: str | None = None
    city: str = "Kinshasa"
    images: list[str] = Field(default_factory=list)
    contact_phone: str | None = None
    contact_whatsapp: str | None = None
    contact_email: str | None = None
    status: Literal["publie", "archive"] = "publie"
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)


class FavoriteCreate(BaseModel):
    offer: Offer
    note: str | None = Field(default=None, max_length=300)


class Favorite(BaseModel):
    id: str
    user_uid: str
    offer: Offer
    note: str | None = None
    created_at: str = Field(default_factory=utcnow)


class HistoryEntry(BaseModel):
    query: str
    intent_summary: str | None = None
    results: int = 0
    created_at: str = Field(default_factory=utcnow)


class HistoryCreate(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    intent_summary: str | None = Field(default=None, max_length=300)
    results: int = 0


class TaxonomyResponse(BaseModel):
    categories: list[dict]
    brands: list[dict]
    communes: list[str]
    cities: list[str]
    trending: list[dict]
    popular_brands: list[str]
    conditions: list[dict]
    seller_types: list[dict]
    image_sources: dict[str, str]
    currency_note: str
