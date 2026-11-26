"""Routeur des annonces publiées par les vendeurs JF MARKET."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import AuthContext
from ..engine.normalize import fold
from ..models import Listing, ListingCreate, ListingUpdate, utcnow
from ..store.repository import new_id
from .deps import get_repository, rate_limit, require_seller, require_user

router = APIRouter(prefix="/api/listings", tags=["annonces"])


@router.get("", dependencies=[Depends(rate_limit)])
async def list_listings(limit: int = Query(default=12, ge=1, le=60)) -> dict:
    """Dernières publications des vendeurs (annonces publiques uniquement)."""
    listings = await get_repository().list_public_listings(limit=limit)
    return {"count": len(listings), "listings": [item.model_dump() for item in listings]}


@router.get("/mine")
async def my_listings(context: AuthContext = Depends(require_user)) -> dict:
    """Annonces du vendeur connecté (publiées et archivées)."""
    listings = await get_repository().list_seller_listings(
        context.user.uid, token=context.id_token
    )
    return {"count": len(listings), "listings": [item.model_dump() for item in listings]}


@router.get("/{listing_id}")
async def get_listing(listing_id: str) -> dict:
    """Détail d'une annonce publiée."""
    listing = await get_repository().get_listing(listing_id)
    if listing is None or listing.status != "publie":
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    return listing.model_dump()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_listing(
    payload: ListingCreate,
    context: AuthContext = Depends(require_seller),
    _: None = Depends(rate_limit),
) -> dict:
    """Publie une nouvelle annonce (compte vendeur requis)."""
    listing = Listing(
        id=new_id("l_"),
        seller_uid=context.user.uid,
        seller_name=context.user.display_name,
        seller_type="particulier",
        title=payload.title.strip(),
        description=payload.description.strip(),
        price=payload.price,
        currency=payload.currency.upper(),
        condition=payload.condition,
        category=payload.category,
        brand=payload.brand,
        product_model=payload.product_model,
        commune=payload.commune,
        city=payload.city,
        images=[url for url in payload.images if url.startswith(("http://", "https://", "/uploads/"))],
        contact_phone=payload.contact_phone,
        contact_whatsapp=payload.contact_whatsapp,
        contact_email=payload.contact_email,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    created = await get_repository().create_listing(listing, token=context.id_token)
    return created.model_dump()


@router.patch("/{listing_id}")
async def update_listing(
    listing_id: str,
    payload: ListingUpdate,
    context: AuthContext = Depends(require_user),
) -> dict:
    """Modifie une annonce appartenant au vendeur connecté."""
    repository = get_repository()
    current = await repository.get_listing(listing_id, token=context.id_token)
    if current is None:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    if current.seller_uid != context.user.uid:
        raise HTTPException(status_code=403, detail="Cette annonce ne vous appartient pas")
    changes = payload.model_dump(exclude_none=True)
    if "images" in changes:
        changes["images"] = [
            url for url in changes["images"] if url.startswith(("http://", "https://", "/uploads/"))
        ]
    if "currency" in changes:
        changes["currency"] = changes["currency"].upper()
    updated = await repository.update_listing(listing_id, changes, token=context.id_token)
    return updated.model_dump() if updated else {}


@router.delete("/{listing_id}")
async def delete_listing(
    listing_id: str, context: AuthContext = Depends(require_user)
) -> dict:
    """Supprime définitivement une annonce du vendeur connecté."""
    repository = get_repository()
    current = await repository.get_listing(listing_id, token=context.id_token)
    if current is None:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    if current.seller_uid != context.user.uid:
        raise HTTPException(status_code=403, detail="Cette annonce ne vous appartient pas")
    await repository.delete_listing(listing_id, token=context.id_token)
    return {"deleted": True, "id": listing_id}


@router.get("/search/local", dependencies=[Depends(rate_limit)])
async def search_local(q: str = Query(min_length=2, max_length=120)) -> dict:
    """Recherche simple dans les annonces publiées sur JF MARKET."""
    needle = fold(q)
    listings = await get_repository().list_public_listings(limit=200)
    matches = [
        item
        for item in listings
        if needle in fold(f"{item.title} {item.description} {item.brand or ''} {item.commune or ''}")
    ]
    return {"count": len(matches), "listings": [item.model_dump() for item in matches[:24]]}
