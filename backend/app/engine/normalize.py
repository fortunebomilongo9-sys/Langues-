"""Normalisation de texte pour JF MARKET.

Objectif : rendre comparables les formulations des utilisateurs kinois
(accents, apostrophes, pluriels, abréviations, fautes de frappe) et les
contenus récupérés sur le web.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

_APOSTROPHES = "'’`´ʼ"
_NON_WORD_RE = re.compile(r"[^a-z0-9\s]+")
_SPACES_RE = re.compile(r"\s+")
_CURRENCY_SYMBOLS = {"$": " usd ", "€": " eur ", "£": " gbp ", "fc": " fc "}


def fold(text: str | None) -> str:
    """Minuscules, sans accents, sans ponctuation, espaces normalisés."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = normalized.replace("œ", "oe").replace("æ", "ae")
    for apostrophe in _APOSTROPHES:
        normalized = normalized.replace(apostrophe, " ")
    normalized = _NON_WORD_RE.sub(" ", normalized)
    return _SPACES_RE.sub(" ", normalized).strip()


def fold_currency(text: str | None) -> str:
    """Comme :func:`fold` mais conserve les symboles monétaires sous forme de mots."""
    if not text:
        return ""
    prepared = str(text)
    for symbol, word in _CURRENCY_SYMBOLS.items():
        if symbol in prepared:
            prepared = prepared.replace(symbol, word)
    return fold(prepared)


def tokens(text: str | None) -> list[str]:
    """Tokens repliés d'un texte."""
    folded = fold(text)
    return [token for token in folded.split(" ") if token]


def compact(text: str | None) -> str:
    """Forme repliée sans espaces (utile pour « N'djili » / « ndjili »)."""
    return fold(text).replace(" ", "")


def singularize(token: str) -> str:
    """Réduction très simple du pluriel français."""
    if len(token) > 4 and token.endswith(("s", "x")):
        return token[:-1]
    return token


def stem_tokens(text: str | None) -> list[str]:
    """Tokens repliés et singularisés, sans doublons, ordre préservé."""
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens(text):
        base = singularize(token)
        if base and base not in seen:
            seen.add(base)
            result.append(base)
    return result


def similarity(left: str, right: str) -> float:
    """Ratio de similarité (0..1) entre deux chaînes."""
    return difflib.SequenceMatcher(None, left, right).ratio()


def correct_tokens(
    raw_tokens: list[str],
    vocabulary: set[str],
    cutoff: float = 0.86,
    min_length: int = 5,
) -> tuple[list[str], dict[str, str]]:
    """Corrige les fautes de frappe probables d'une requête.

    Un token n'est corrigé que s'il est absent du vocabulaire, suffisamment
    long, et qu'un candidat proche existe. Les corrections sont renvoyées pour
    être affichées à l'utilisateur (transparence, aucune invention).
    """
    corrected: list[str] = []
    changes: dict[str, str] = {}
    for token in raw_tokens:
        if token in vocabulary or len(token) < min_length or token.isdigit():
            corrected.append(token)
            continue
        candidates = difflib.get_close_matches(token, vocabulary, n=1, cutoff=cutoff)
        if candidates:
            changes[token] = candidates[0]
            corrected.append(candidates[0])
        else:
            corrected.append(token)
    return corrected, changes


def remove_phrases(text: str, phrases: list[tuple[str, str]]) -> str:
    """Applique les expressions composées (les plus longues d'abord)."""
    result = f" {text} "
    for phrase, replacement in sorted(phrases, key=lambda item: len(item[0]), reverse=True):
        folded_phrase = fold(phrase)
        if not folded_phrase:
            continue
        result = result.replace(f" {folded_phrase} ", f" {replacement} ")
    return _SPACES_RE.sub(" ", result).strip()


def parse_amount(raw: str | None) -> float | None:
    """Convertit un montant textuel (« 1 200 », « 1.200,50 », « 200 ») en nombre."""
    if not raw:
        return None
    cleaned = str(raw).replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
    cleaned = re.sub(r"[^\d.,]", "", cleaned)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 3 and len(parts[0]) >= 1:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            cleaned = cleaned.replace(".", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


def truncate(text: str | None, limit: int = 400) -> str:
    """Tronque proprement un texte destiné à l'affichage."""
    if not text:
        return ""
    collapsed = _SPACES_RE.sub(" ", str(text)).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def slugify(text: str | None, fallback: str = "jf") -> str:
    """Identifiant stable, lisible et sûr."""
    folded = fold(text)
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return slug[:60] or fallback


def token_overlap(left: str | None, right: str | None) -> float:
    """Proportion des tokens de ``left`` présents dans ``right`` (0..1)."""
    left_tokens = set(stem_tokens(left))
    right_tokens = set(stem_tokens(right))
    if not left_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)
