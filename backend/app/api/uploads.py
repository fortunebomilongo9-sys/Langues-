"""Téléversement d'images pour les annonces vendeurs.

Deux destinations réelles :
* Firebase Storage (API REST) si `FIREBASE_PROJECT_ID`/`FIREBASE_STORAGE_BUCKET`
  et un jeton utilisateur sont disponibles ;
* stockage local dans `data/uploads` sinon (servi par `/uploads/...`).
"""

from __future__ import annotations

import io
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from ..auth import AuthContext
from ..config import get_settings
from ..store.repository import new_id
from .deps import require_user

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_SIDE = 1600


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...), context: AuthContext = Depends(require_user)
) -> dict:
    """Téléverse une image de produit et renvoie son URL publique."""
    settings = get_settings()
    content = await file.read(settings.upload_max_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image trop volumineuse (maximum {settings.upload_max_bytes // (1024 * 1024)} Mo)",
        )
    try:
        with Image.open(io.BytesIO(content)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(content)) as image:
            fmt = (image.format or "").upper()
            if fmt not in ALLOWED:
                raise HTTPException(
                    status_code=415, detail="Format non pris en charge. Utilisez JPG, PNG ou WebP."
                )
            image = image.convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=86, optimize=True)
            payload = buffer.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Image illisible ou corrompue") from exc

    name = f"{new_id('img_')}.jpg"
    if settings.storage_enabled and context.id_token:
        url = await _upload_firebase(payload, name, context.id_token)
        return {"url": url, "storage": "firebase", "bytes": len(payload)}

    target = settings.uploads_dir / name
    target.write_bytes(payload)
    return {"url": f"/uploads/{name}", "storage": "local", "bytes": len(payload)}


async def _upload_firebase(payload: bytes, name: str, token: str) -> str:
    settings = get_settings()
    bucket = settings.firebase_storage_bucket
    endpoint = (
        f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
        f"?uploadType=media&name={quote(f'listings/{name}', safe='')}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            endpoint,
            content=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="Firebase Storage a refusé le téléversement. Vérifiez la configuration.",
        )
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{quote(bucket, safe='')}/o/"
        f"{quote(f'listings/{name}', safe='')}?alt=media"
    )
