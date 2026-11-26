"""Signature visuelle pour la recherche par image.

Sans API de recherche inverse configurée, JF MARKET compare l'image importée à
des images d'offres réellement récupérées : dimensions, rapport d'aspect,
couleurs dominantes et empreinte perceptuelle. C'est une similitude visuelle
grossière, jamais une identification certaine.
"""

from __future__ import annotations

import io

import httpx

try:  # Pillow reste optionnel : sans lui, la recherche par image reste textuelle.
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None  # type: ignore[assignment]

MAX_IMAGE_BYTES = 900_000
MIN_IMAGE_BYTES = 1_200
ALLOWED_TYPES = ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif")


def _dominant(colours: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not colours:
        return (128, 128, 128)
    return max(colours, key=lambda c: sum(c))


def signature_from_bytes(content: bytes) -> dict | None:
    """Calcule une signature visuelle (empreinte perceptuelle + couleurs)."""
    if Image is None or not content:
        return None
    try:
        with Image.open(io.BytesIO(content)) as handle:
            image = handle.convert("RGB")
            width, height = image.size
            if width < 32 or height < 32:
                return None
            gray = [
                int(0.299 * r + 0.587 * g + 0.114 * b)
                for r, g, b in image.resize((8, 8)).getdata()
            ]
            average = sum(gray) / len(gray)
            bits = "".join("1" if value > average else "0" for value in gray)
            buckets: dict[tuple[int, int, int], int] = {}
            for r, g, b in image.resize((48, 48)).getdata():
                key = (r // 32, g // 32, b // 32)
                buckets[key] = buckets.get(key, 0) + 1
            top = sorted(buckets.items(), key=lambda item: item[1], reverse=True)[:6]
            colours = [(k[0] * 32 + 16, k[1] * 32 + 16, k[2] * 32 + 16) for k, _ in top]
            return {
                "width": width,
                "height": height,
                "aspect": round(width / height, 3),
                "hash": bits,
                "colors": colours,
                "dominant": _dominant(colours),
            }
    except Exception:  # noqa: BLE001
        return None


def compare_signatures(left: dict | None, right: dict | None) -> float:
    """Similitude visuelle entre deux signatures (0..1)."""
    if not left or not right:
        return 0.0
    left_bits = left.get("hash", "")
    right_bits = right.get("hash", "")
    if left_bits and right_bits and len(left_bits) == len(right_bits):
        diff = sum(1 for a, b in zip(left_bits, right_bits) if a != b)
        hash_similarity = max(0.0, 1.0 - diff / len(left_bits))
    else:
        hash_similarity = 0.0

    aspect_delta = abs(float(left.get("aspect", 1.0)) - float(right.get("aspect", 1.0)))
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

    return round(0.45 * hash_similarity + 0.25 * aspect_score + 0.30 * color_score, 3)


async def signature_from_url(client: httpx.AsyncClient, url: str) -> dict | None:
    """Télécharge une image d'offre (taille bornée) et calcule sa signature."""
    if not url or Image is None:
        return None
    try:
        response = await client.get(url, timeout=6.0, follow_redirects=True)
    except Exception:  # noqa: BLE001
        return None
    if response.status_code >= 400:
        return None
    content_type = (response.headers.get("content-type") or "").lower()
    if content_type and not any(item in content_type for item in ALLOWED_TYPES):
        return None
    content = response.content
    if not MIN_IMAGE_BYTES <= len(content) <= MAX_IMAGE_BYTES:
        return None
    return signature_from_bytes(content)
