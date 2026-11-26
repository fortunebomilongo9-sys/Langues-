"""Types partagés par les sources de JF MARKET.

Aucune offre de ce module n'est inventée : chaque ``RawOffer`` provient d'une
page réellement téléchargée, et chaque champ absent reste vide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..models import SearchIntent, SellerType

SourceKind = Literal["web", "serpapi", "marketplace", "store"]


@dataclass(slots=True)
class ImageRef:
    """Image candidate trouvée sur une page source."""

    url: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None
    origin: Literal["jsonld", "og", "html"] = "html"
    page_url: str = ""


@dataclass(slots=True)
class RawOffer:
    """Offre brute extraite d'une page, avant normalisation."""

    title: str
    url: str
    source_id: str
    source_name: str
    site_domain: str = ""
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    price_text: str | None = None
    brand: str | None = None
    product_model: str | None = None
    condition_text: str | None = None
    availability_text: str | None = None
    seller_name: str | None = None
    seller_type: SellerType = "inconnu"
    location_text: str | None = None
    images: list[ImageRef] = field(default_factory=list)
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_whatsapp: str | None = None
    published_at: str | None = None
    trust: float = 0.5
    stage: str = "exact"
    extraction: str = "html"


@dataclass(slots=True)
class SerpResult:
    """Résultat brut d'un moteur de recherche web."""

    title: str
    url: str
    snippet: str | None = None
    engine: str = ""
    position: int = 0


@dataclass
class SourceRun:
    """Compte-rendu d'exécution d'une source."""

    source_id: str
    label: str
    offers: list[RawOffer] = field(default_factory=list)
    status: Literal["ok", "vide", "echec", "desactive"] = "ok"
    detail: str | None = None
    network_error: bool = False


class SearchSource(Protocol):
    """Contrat minimal d'une source consultable."""

    id: str
    label: str
    kind: SourceKind

    async def collect(self, client, context: "SourceContext") -> SourceRun:  # pragma: no cover
        ...


@dataclass(slots=True)
class SourceContext:
    """Paramètres transmis aux sources pour une étape de recherche."""

    intent: SearchIntent
    query: str
    limit: int
    pages_budget: int = 6
