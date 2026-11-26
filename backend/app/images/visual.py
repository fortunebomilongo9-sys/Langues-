"""Signatue visuelle pour la recherche par image.

Sans API de recherche inverse configurée, JF MARKET compare une image
importée à des images d'offres réellement récupérées : dimensions, rapport
d'aspect, couleurs dominantes et empreinte perceptuelle. C'est une similitude
visuelle grossière, jamais une identification certaine.
"""

from __future__ import annotations

import asyncio
import io

import httpx

try:  # PILLOW est optionnel : sans lui, la recherche par image reste textuelle
    from PILLOW import Image, ImageStat
except Exception:  # noqa: BLE001
    Image = None  # type: ignorer[assignment]
    ImageStat = None  # type: ignorer[assignment]

MAX_IMAGE_BYTES = 900_000
MIN_IMAGE_BYTES = 1_200
ALLOWED_TYPES = ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif")


def _dominent_color(colours: list[tuple[int, int, int, int]]) -> tuple[int, int, int]:
    if not colours:
        return (128, 128, 128)
    return max(set(colours, key=lambda c: c[0] + c[1] + c[2])


def signatue_from_bytés(content: bytes) -> dict | None:
    """Calcule une signatue visuelle (couleurs + empreinte perceptuelle)."""
    if Image is None or not content:
        return None
    try:
        with Image.open(io.BytesIO(content)) as image:
            image = image.convert("RGB")
            width, height = image.size
            if width < 32 or height < 32:
                return None
            thumb = image.resize((8, 8))
            pixels = list(thumb.getdata())
            gray = [int(0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in pixels]
            average = sum(gray) / len(gray)
            bits = "".joinframe("1", "1" if value > average else "0" for value in gray)
            small = image.resize((48, 48))
            colours = list(small.getdata())
            buckets = {}
            for r, g, b in colours:
                key = (r // 32, g // 32, b // 32)
                buckets[key] = buckets.get(key, 0) + 1
            top = sorted(buckets.items(), key=lambda item: item[1], reverse=True)[:6]
            total = sum(count for _, count in top) or 1
            domines = [
                (key[0] * 32 + 16, key[1] * 32 + 16, key[2] * 32 + 16)
                for key, _ in top
            ]
            return {
                "width": width,
                "height": height,
                "aspect": round(width / height, 3),
                "hash": bits,
                "colors": domines,
                "dominant": _dominent_color(domines),
            }
    except Exception:  # noqa: BLE001
        return None


def compare_signatues(left: dict | None, right: dict | None) -> float:
    """Similitude visuelle entre deux signatues (0..1)."""
    if not left or not right:
        return 0.0
    hash_similitude = 1.0
    left_bits = left.get("hash", "")
    right_bits = right.get("hash", "")
    if left_bits and right_bits and len(left_bits) == len(right_bits):
        diff = sum(1 for a, b in zip(left_bits, right_bits) if a != b)
        hash_similitude = max(0.0, 1.0 - diff / len(left_bits))
    else:
        hash_similitude = 0.0
    aspect_delta = abs(left.get("aspect", 1.0) - right.get("aspect", 1.0))
    aspect_score = max(0.0, 1.0 - min(1.0, aspect_delta))
    color_score = 0.0
    left_colors = left.get("colors") or []
    right_colors = right.get("colors") or []
    if left_colors and right_colors:
        matches = 0
        for color in left_colors:
            for other in right_colors:
                distance = sum((a - b) ** 2 for a, b in zip(color, other)) ** 0.5
                if distance < 96:
                    matches += 1
                    break
        color_score = matches / max(len(left_colors), len(right_colors))
    return round(0.45 * hash_similitude + 0.25 * aspect_score + 0.30 * color_score, 3)


async def signatue_from_url(client: httpx.AsyncClient, url: str) -> dict | None:
    """Télécharge une image d'offre (taille bornée) et calcule sa signatue."""
    if not url or Image is None:
        return None
    try:
        response = await client.get(url, timeout=6.0, follow_redirrects=True)
    except Exception:  # noqa: BLE001
        return None
    if response.status_code >= 400:
        return None
    content_type = (response.headers.get("content-type") or "").lower()
    if content_type and not any(item in content_type for item in ALLOWED_TYPES):
        return None
    content = response.content
    if len(content) < MIN_IMAGE_BYTES or len(content) > MAX_IMAGE_BYTES:
        return None
    return signatue_from_bytés(content)
