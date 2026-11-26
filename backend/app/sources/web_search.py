"""Recherche web multi-moteurs (SERP) pour JF MARKET.

Chaque moteur est un simple couple « construire l'URL » / « lire la page ».
Les pannes sont isolées : si un moteur bloque l'accès, les autres continuent et
l'utilisateur voit précisément quelles sources ont échoué.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from .base import SerpResult
from .html_utils import clean_text, make_soup, sanitize_url

USER_AGENT_FALLBACK = "Mozilla/5.0 (compatible; JF-MARKET/1.0; +https://jfmarket.app)"
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
    "Cache-Control": "no-cache",
}
_BLOCKED_HOSTS = {
    "duckduckgo.com",
    "bing.com",
    "www.bing.com",
    "mojeek.com",
}


@dataclass(frozen=True)
class EngineSpec:
    """Description d'un moteur de recherche web."""

    id: str
    label: str
    trust: float
    build_url: Callable[[str], str]
    parse: Callable[[BeautifulSoup, str], list[SerpResult]]


def _results_duckduckgo_html(soup: BeautifulSoup, _base: str) -> list[SerpResult]:
    results: list[SerpResult] = []
    for position, block in enumerate(soup.select("div.result"), start=1):
        link = block.select_one("a.result__a")
        if link is None:
            continue
        href = sanitize_url(_decode_duckduckgo(link.get("href") or ""))
        title = clean_text(link.get_text(" ", strip=True), 200)
        if not href or not title:
            continue
        snippet_node = block.select_one(".result__snippet")
        snippet = clean_text(snippet_node.get_text(" ", strip=True), 400) if snippet_node else None
        results.append(
            SerpResult(title=title, url=href, snippet=snippet, engine="duckduckgo", position=position)
        )
    return results


def _results_duckduckgo_lite(soup: BeautifulSoup, _base: str) -> list[SerpResult]:
    results: list[SerpResult] = []
    for position, link in enumerate(soup.select("a.result-link"), start=1):
        href = sanitize_url(_decode_duckduckgo(link.get("href") or ""))
        title = clean_text(link.get_text(" ", strip=True), 200)
        if not href or not title:
            continue
        snippet = None
        row = link.find_parent("tr")
        if row is not None:
            snippet_node = row.select_one(".result-snippet")
            if snippet_node:
                snippet = clean_text(snippet_node.get_text(" ", strip=True), 400)
        results.append(
            SerpResult(title=title, url=href, snippet=snippet, engine="duckduckgo-lite", position=position)
        )
    return results


def _results_bing(soup: BeautifulSoup, _base: str) -> list[SerpResult]:
    results: list[SerpResult] = []
    for position, block in enumerate(soup.select("li.b_algo"), start=1):
        link = block.select_one("h2 a")
        if link is None:
            continue
        href = sanitize_url(link.get("href") or "")
        title = clean_text(link.get_text(" ", strip=True), 200)
        if not href or not title:
            continue
        snippet_node = block.select_one("p")
        snippet = clean_text(snippet_node.get_text(" ", strip=True), 400) if snippet_node else None
        results.append(SerpResult(title=title, url=href, snippet=snippet, engine="bing", position=position))
    return results


def _results_mojeek(soup: BeautifulSoup, _base: str) -> list[SerpResult]:
    results: list[SerpResult] = []
    blocks = soup.select("ul.results-standard li") or soup.select("li.standard")
    for position, block in enumerate(blocks, start=1):
        link = block.select_one("h2 a")
        if link is None:
            continue
        href = sanitize_url(link.get("href") or "")
        title = clean_text(link.get_text(" ", strip=True), 200)
        if not href or not title:
            continue
        snippet_node = block.select_one("p.s") or block.select_one("p")
        snippet = clean_text(snippet_node.get_text(" ", strip=True), 400) if snippet_node else None
        results.append(SerpResult(title=title, url=href, snippet=snippet, engine="mojeek", position=position))
    return results


def _decode_duckduckgo(url: str) -> str:
    """Décode les liens de redirection DuckDuckGo (``/l/?uddg=...``)."""
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = parse_qs(parsed.query)
        target = params.get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


ENGINES: tuple[EngineSpec, ...] = (
    EngineSpec(
        id="duckduckgo",
        label="DuckDuckGo",
        trust=0.72,
        build_url=lambda query: "https://html.duckduckgo.com/html/?q="
        + quote_plus(query)
        + "&kl=cd-fr",
        parse=_results_duckduckgo_html,
    ),
    EngineSpec(
        id="bing",
        label="Bing",
        trust=0.68,
        build_url=lambda query: "https://www.bing.com/search?q="
        + quote_plus(query)
        + "&setlang=fr&cc=CD&count=20",
        parse=_results_bing,
    ),
    EngineSpec(
        id="mojeek",
        label="Mojeek",
        trust=0.55,
        build_url=lambda query: "https://www.mojeek.com/search?q=" + quote_plus(query),
        parse=_results_mojeek,
    ),
    EngineSpec(
        id="duckduckgo-lite",
        label="DuckDuckGo Lite",
        trust=0.6,
        build_url=lambda query: "https://lite.duckduckgo.com/lite/?q=" + quote_plus(query),
        parse=_results_duckduckgo_lite,
    ),
)


def engine_headers() -> dict[str, str]:
    """En-têtes HTTP communs aux moteurs (pas de cookie, pas d'identité secrète)."""
    return dict(_HEADERS)


async def _run_engine(
    client, engine: EngineSpec, query: str, per_engine: int
) -> tuple[list[SerpResult], str | None]:
    url = engine.build_url(query)
    try:
        response = await client.get(url, headers=engine_headers(), follow_redirects=True)
    except Exception as exc:  # noqa: BLE001 - une panne réseau ne doit rien bloquer
        return [], f"{engine.label} : {type(exc).__name__}"
    if response.status_code >= 400:
        return [], f"{engine.label} : HTTP {response.status_code}"
    soup = make_soup(response.content)
    results = engine.parse(soup, url)
    if not results and response.status_code in {200, 202}:
        return [], f"{engine.label} : page sans résultat exploitable (protection anti-robot probable)"
    filtered = [
        result
        for result in results
        if not any(host in urlparse(result.url).netloc for host in _BLOCKED_HOSTS)
    ]
    return filtered[:per_engine], None


async def search_web(
    client,
    query: str,
    *,
    per_engine: int = 10,
    engines: tuple[EngineSpec, ...] | None = None,
) -> tuple[list[SerpResult], list[str]]:
    """Interroge plusieurs moteurs en parallèle et déduplique les résultats."""
    selected = engines or ENGINES
    tasks = [asyncio.create_task(_run_engine(client, engine, query, per_engine)) for engine in selected]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    ordered: list[SerpResult] = []
    errors: list[str] = []
    for engine, outcome in zip(selected, gathered):
        if isinstance(outcome, BaseException):
            errors.append(f"{engine.label} : erreur inattendue")
            continue
        results, error = outcome
        if error:
            errors.append(error)
        for result in results:
            if any(host in urlparse(result.url).netloc for host in _BLOCKED_HOSTS):
                continue
            ordered.append(result)

    seen: set[str] = set()
    unique: list[SerpResult] = []
    for result in ordered:
        key = result.url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique, errors
