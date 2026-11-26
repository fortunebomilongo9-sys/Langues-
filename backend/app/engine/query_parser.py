"""Analyse intelligente des requêtes naturelles de JF MARKET.

Le parseur transforme une phrase comme « Je cherche un bon téléphone Samsung à
200 dollars » en intention structurée : produit, marque, modèle, budget, état,
commune. Il ne complète jamais une information absente : il la laisse vide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import settings
from ..models import SearchIntent
from ..taxonomy import (
    BRANDS,
    BRAND_ALIASES,
    CATEGORIES,
    CATEGORY_BY_ID,
    COMMUNES,
    COMMUNE_ALIASES,
    CONDITION_WORDS,
    CURRENCY_ALIASES,
    PHRASES,
    STOPWORDS,
    SYNONYMS,
    CITIES,
)
from .normalize import (
    compact,
    correct_tokens,
    fold,
    fold_currency,
    parse_amount,
    stem_tokens,
    token_overlap,
    tokens,
)

# Vocabulaire de référence pour la correction orthographique.
_VOCABULARY: set[str] = set()
for _alias in BRAND_ALIASES:
    _VOCABULARY.update(_alias.split())
for _category in CATEGORIES:
    for _keyword in _category["keywords"]:
        _VOCABULARY.update(fold(_keyword).split())
    for _sub in _category["subcategories"]:
        for _keyword in _sub["keywords"]:
            _VOCABULARY.update(fold(_keyword).split())
for _synonym in SYNONYMS:
    _VOCABULARY.update(fold(_synonym).split())
_VOCABULARY.update(COMMUNE_ALIASES)
_VOCABULARY.update({"pouces", "pouce", "inch", "original", "contrefacon", "prix", "budget"})
_VOCABULARY = {word for word in _VOCABULARY if word}

# Familles de produits reconnues comme « nom de modèle ».
MODEL_FAMILIES = {
    "galaxy", "camon", "spark", "hot", "note", "redmi", "poco", "iphone", "ipad",
    "macbook", "thinkpad", "ideapad", "pavilion", "probook", "elitebook", "latitude",
    "inspiron", "vostro", "vivobook", "zenbook", "aspire", "predator", "legion",
    "rav4", "prado", "hilux", "corolla", "tucson", "sportage", "xtrail", "x-trail",
    "crv", "cr-v", "air max", "jordan", "ultra", "smart tv", "soundcore",
}
MODEL_SUFFIXES = {"ultra", "pro", "max", "plus", "lite", "note", "se", "air", "neo", "mini", "prime"}

_MODEL_TOKEN_RE = re.compile(r"^[a-z]{0,4}\d{1,4}[a-z]{0,3}$")
_SIZE_RE = re.compile(r"(\d{2})\s*(?:pouces|pouce|inch|inches|\")")
_STORAGE_RE = re.compile(r"(\d{1,3})\s*(?:gb|go|g|tb|to)\b")
_CURRENCY_TOKEN_RE = re.compile(
    r"(dollars?|usd|euros?|eur|fc|cdf|francs?\s+congolais|francs?|bucks?)"
)
_BUDGET_BETWEEN_RE = re.compile(
    r"(?:entre|de)\s+(\d[\d\s.,]*)\s*(?:et|a|-)\s*(\d[\d\s.,]*)"
)
_BUDGET_MAX_RE = re.compile(
    r"(?:moins de|au plus|maximum|max|jusqu a|pas plus de|budget de|budget max|"
    r"inferieur a|en dessous de|a moins de)\s+(\d[\d\s.,]*)"
)
_BUDGET_MIN_RE = re.compile(
    r"(?:plus de|minimum|min|a partir de|superieur a|depuis)\s+(\d[\d\s.,]*)"
)
_BUDGET_AMOUNT_CUR_RE = re.compile(r"(\d[\d\s.,]*)\s*" + _CURRENCY_TOKEN_RE.pattern)
_BUDGET_LOOSE_RE = re.compile(r"\b(?:a|vers|environ|autour de|~)\s+(\d[\d\s.,]*)")


@dataclass(slots=True)
class _Budget:
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None


def _detect_currency(text: str) -> str | None:
    """Devise mentionnée dans la requête."""
    for match in _CURRENCY_TOKEN_RE.finditer(text):
        alias = " ".join(match.group(1).split())
        if alias in CURRENCY_ALIASES:
            return CURRENCY_ALIASES[alias]
    return None


def _extract_budget(text: str) -> _Budget:
    """Extrait un budget explicite. Aucune valeur n'est supposée par défaut."""
    budget = _Budget(currency=_detect_currency(text))

    between = _BUDGET_BETWEEN_RE.search(text)
    if between:
        low = parse_amount(between.group(1))
        high = parse_amount(between.group(2))
        if low and high and low < high:
            budget.price_min, budget.price_max = low, high
            return budget

    maximum = _BUDGET_MAX_RE.search(text)
    if maximum:
        value = parse_amount(maximum.group(1))
        if value:
            budget.price_max = value
            return budget

    minimum = _BUDGET_MIN_RE.search(text)
    if minimum:
        value = parse_amount(minimum.group(1))
        if value:
            budget.price_min = value
            return budget

    with_currency = _BUDGET_AMOUNT_CUR_RE.search(text)
    if with_currency:
        value = parse_amount(with_currency.group(1))
        if value:
            budget.price_max = value
            budget.currency = CURRENCY_ALIASES.get(
                " ".join(with_currency.group(2).split()), budget.currency
            )
            return budget

    loose = _BUDGET_LOOSE_RE.search(text)
    if loose:
        value = parse_amount(loose.group(1))
        if value and value >= 10:
            budget.price_max = value
    return budget


def _to_usd(amount: float | None, currency: str | None) -> float | None:
    """Équivalent USD approximatif, uniquement pour comparer un budget."""
    if amount is None:
        return None
    if currency == "CDF":
        return round(amount / max(settings.usd_cdf_rate, 1.0), 2)
    if currency == "EUR":
        return round(amount * 1.08, 2)
    return amount


def _match_commune(text: str) -> str | None:
    """Commune de Kinshasa explicitement citée dans la requête."""
    padded = f" {text} "
    for alias in sorted(COMMUNE_ALIASES, key=len, reverse=True):
        if f" {alias} " in padded:
            return COMMUNE_ALIASES[alias]
    compacted = compact(text)
    for alias, commune in COMMUNE_ALIASES.items():
        if len(alias) >= 5 and alias.replace(" ", "") in compacted:
            return commune
    return None


def _match_city(text: str) -> str | None:
    """Ville explicitement citée."""
    padded = f" {text} "
    for alias, city in sorted(CITIES.items(), key=lambda item: len(item[0]), reverse=True):
        if f" {alias} " in padded:
            return city
    return None


def _match_brand(text: str, raw_tokens: list[str]) -> tuple[str | None, list[str]]:
    """Marque la plus spécifique détectée (alias multi-mots prioritaires)."""
    padded = f" {text} "
    best: tuple[int, str] | None = None
    for alias, brand in BRAND_ALIASES.items():
        alias_tokens = alias.split()
        if len(alias_tokens) > 1:
            found = f" {alias} " in padded
        else:
            found = alias in raw_tokens
        if found:
            weight = len(alias)
            if best is None or weight > best[0]:
                best = (weight, brand)
    return (best[1] if best else None), raw_tokens


def _match_category(text: str) -> tuple[str | None, str | None, str | None]:
    """Catégorie et sous-catégorie les plus probables."""
    padded = f" {text} "
    best: tuple[float, str, str | None] = (0.0, "", None)
    for category in CATEGORIES:
        score = 0.0
        for keyword in category["keywords"]:
            folded_keyword = fold(keyword)
            if not folded_keyword:
                continue
            if " " in folded_keyword:
                if f" {folded_keyword} " in padded:
                    score += 1.4
            elif f" {folded_keyword} " in padded:
                score += 1.0
        sub_id: str | None = None
        for sub in category["subcategories"]:
            sub_score = 0.0
            for keyword in sub["keywords"]:
                folded_keyword = fold(keyword)
                if folded_keyword and f" {folded_keyword} " in padded:
                    sub_score += 1.0
            if sub_score > 0 and sub_score >= score * 0.6:
                if sub_id is None or sub_score > 0:
                    sub_id = sub["id"]
        if score > best[0]:
            best = (score, category["id"], sub_id)
    if best[0] <= 0:
        return None, None, None
    return best[1], CATEGORY_BY_ID[best[1]]["label"], best[2]


def _detect_condition(raw_tokens: list[str]) -> str:
    for token in raw_tokens:
        if token in CONDITION_WORDS:
            return CONDITION_WORDS[token]
    return "inconnu"


def _extract_model(raw_tokens: list[str], brand: str | None) -> tuple[str | None, str | None]:
    """Modèle / référence à partir des tokens significatifs."""
    brand_tokens = set()
    if brand:
        brand_tokens = set(fold(brand).split())
        for alias in BRANDS.get(brand, {}).get("aliases", []):
            brand_tokens.update(fold(alias).split())

    model_parts: list[str] = []
    reference: str | None = None
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        if token in brand_tokens or token in STOPWORDS:
            index += 1
            continue
        is_family = token in MODEL_FAMILIES
        is_code = bool(_MODEL_TOKEN_RE.match(token)) and any(ch.isdigit() for ch in token)
        if is_family or is_code:
            model_parts.append(token)
            if is_code and reference is None:
                reference = token
            # suffixe éventuel (ultra, pro, max…)
            if index + 1 < len(raw_tokens) and raw_tokens[index + 1] in MODEL_SUFFIXES:
                model_parts.append(raw_tokens[index + 1])
                index += 1
        index += 1

    if not model_parts:
        return None, reference
    # dédoublonne en conservant l'ordre
    seen: set[str] = set()
    cleaned = [part for part in model_parts if not (part in seen or seen.add(part))]
    return " ".join(cleaned)[:80], reference


def _expand_terms(raw_tokens: list[str], corrected: list[str]) -> list[str]:
    """Ajoute synonymes et variantes utiles pour la recherche progressive."""
    expanded: list[str] = []
    for token in corrected:
        expanded.append(token)
        synonym = SYNONYMS.get(token)
        if synonym and synonym not in expanded:
            expanded.extend(synonym.split())
    for index in range(len(raw_tokens) - 1):
        pair = f"{raw_tokens[index]} {raw_tokens[index + 1]}"
        if pair in SYNONYMS:
            expanded.extend(SYNONYMS[pair].split())
    seen: set[str] = set()
    result: list[str] = []
    for term in expanded:
        if term and term not in seen and term not in STOPWORDS:
            seen.add(term)
            result.append(term)
    return result


def parse_query(raw_query: str) -> SearchIntent:
    """Analyse une requête libre et renvoie l'intention structurée."""
    raw_query = " ".join((raw_query or "").split())[:300]
    prepared = fold_currency(raw_query)
    stripped = " ".join(
        part for part in (prepared.replace(" usd ", " "), prepared) if part
    )
    text = stripped if len(stripped) >= len(prepared) - 8 else prepared

    # 1. Expressions composées (salutations, « pas trop cher », lingala…)
    working = " " + text + " "
    working = _apply_phrases(working)
    working = " ".join(working.split())

    raw_tokens = tokens(working)

    # 2. Correction orthographique (uniquement sur des tokens inconnus)
    corrected_tokens, corrections = correct_tokens(raw_tokens, _VOCABULARY, cutoff=0.85)

    # 3. Devise et budget (calculés sur le texte replié complet)
    budget_text = fold_currency(raw_query)
    budget = _extract_budget(budget_text)

    # 4. Marque, catégorie, état, localisation
    brand, _ = _match_brand(" ".join(corrected_tokens), corrected_tokens)
    category_id, category_label, subcategory = _match_category(" ".join(corrected_tokens))
    condition = _detect_condition(corrected_tokens)
    commune = _match_commune(" ".join(corrected_tokens))
    city = _match_city(" ".join(corrected_tokens))
    model, reference = _extract_model(corrected_tokens, brand)

    # 5. Termes produit : on retire le bruit conversationnel
    budget_numbers: set[str] = set()
    for match in _BUDGET_AMOUNT_CUR_RE.finditer(budget_text):
        amount = parse_amount(match.group(1))
        if amount is not None:
            budget_numbers.add(str(int(amount)))
    for match in _BUDGET_BETWEEN_RE.finditer(budget_text):
        for group in (1, 2):
            amount = parse_amount(match.group(group))
            if amount is not None:
                budget_numbers.add(str(int(amount)))

    product_terms: list[str] = []
    for token in corrected_tokens:
        if token in STOPWORDS or token in CONDITION_WORDS or token in {"budget", "reduit", "cher"}:
            continue
        if token in {"dollar", "dollars", "usd", "euro", "euros", "eur", "fc", "cdf", "franc", "francs"}:
            continue
        if token in budget_numbers or (token.isdigit() and len(token) >= 2 and token in budget_numbers):
            continue
        if token in COMMUNE_ALIASES or token in CITIES:
            continue
        if token not in product_terms:
            product_terms.append(token)

    attributes: dict[str, str] = {}
    size_match = _SIZE_RE.search(text)
    if size_match:
        attributes["taille_pouces"] = size_match.group(1)
    storage_match = _STORAGE_RE.search(text)
    if storage_match:
        attributes["stockage"] = storage_match.group(1)
    if "original" in corrected_tokens or "original" in raw_tokens:
        attributes["authenticite"] = "original"
    if "contrefacon" in corrected_tokens:
        attributes["authenticite"] = "contrefacon"

    notes: list[str] = []
    if corrections:
        notes.append(
            "Orthographe corrigée : "
            + ", ".join(f"« {bad} » → « {good} »" for bad, good in corrections.items())
        )
    if budget.price_max is None and budget.price_min is None and budget.currency:
        notes.append(f"Devise détectée ({budget.currency}) sans montant exploitable.")
    if budget.price_max is not None or budget.price_min is not None:
        currency = budget.currency or "USD"
        low = f"{budget.price_min:g} " if budget.price_min else ""
        high = f"{budget.price_max:g} " if budget.price_max else ""
        notes.append(f"Budget compris : {low}{'— ' if low and high else ''}{high}{currency}".strip())
    if not product_terms and not brand:
        notes.append("Requête très générale : la recherche sera élargie par catégorie.")

    expanded = _expand_terms(raw_tokens, corrected_tokens)

    return SearchIntent(
        raw_query=raw_query,
        normalized_query=" ".join(corrected_tokens),
        product_terms=product_terms,
        expanded_terms=expanded,
        corrections=corrections,
        brand=brand,
        product_model=model,
        product_reference=reference,
        category=category_id,
        category_label=category_label,
        subcategory=subcategory,
        price_min=budget.price_min,
        price_max=budget.price_max,
        currency=budget.currency,
        budget_usd=_to_usd(budget.price_max, budget.currency),
        condition=condition,  # type: ignore[arg-type]
        commune=commune,
        city=city,
        attributes=attributes,
        notes=notes,
    )


def _apply_phrases(text: str) -> str:
    """Remplace les expressions conversationnelles par leur forme utile."""
    result = text
    for phrase, replacement in sorted(PHRASES, key=lambda item: len(item[0]), reverse=True):
        folded_phrase = fold(phrase)
        if not folded_phrase:
            continue
        result = result.replace(f" {folded_phrase} ", f" {replacement} ")
    return result


def build_search_query(intent: SearchIntent, extra_terms: list[str] | None = None) -> str:
    """Construit une requête lisible pour les moteurs de recherche externes."""
    parts: list[str] = []
    if intent.brand:
        parts.append(intent.brand)
    if intent.product_model:
        parts.append(intent.product_model)
    for term in intent.product_terms:
        if term not in parts:
            parts.append(term)
    for term in extra_terms or []:
        if term not in parts:
            parts.append(term)
    location = intent.commune or intent.city or "Kinshasa"
    if location and location.lower() not in [part.lower() for part in parts]:
        parts.append(location)
    query = " ".join(part for part in parts if part).strip()
    return query or intent.normalized_query or intent.raw_query


def intent_matches_offer(intent: SearchIntent, title: str, description: str | None = None) -> bool:
    """Vérification de cohérence minimale entre une intention et un texte d'offre."""
    haystack = f"{title} {description or ''}"
    if intent.brand:
        brand_tokens = set(fold(intent.brand).split())
        for alias in BRANDS.get(intent.brand, {}).get("aliases", []):
            brand_tokens.update(fold(alias).split())
        if not brand_tokens & set(stem_tokens(haystack)):
            return False
    if intent.product_model:
        model_tokens = [token for token in stem_tokens(intent.product_model) if any(ch.isdigit() for ch in token)]
        if model_tokens and not all(token in stem_tokens(haystack) for token in model_tokens):
            return False
    if intent.product_terms:
        core = [term for term in intent.product_terms if len(term) > 3]
        if core and token_overlap(" ".join(core), haystack) < 0.34:
            return False
    return True


def all_communes() -> list[str]:
    """Référentiel des communes de Kinshasa."""
    return list(COMMUNES)
