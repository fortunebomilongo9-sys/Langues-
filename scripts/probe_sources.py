"""Sonde de disponibilité des sources externes de JF MARKET.

Usage : python scripts/probe_sources.py
Ce script ne sert qu'au diagnostic : il effectue une seule requête par source
et indique si la page renvoyée contient des indices de produits exploitables.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

TARGETS = [
    ("duckduckgo-html", "https://html.duckduckgo.com/html/?q=samsung+galaxy+s24"),
    ("duckduckgo-lite", "https://lite.duckduckgo.com/lite/?q=samsung+galaxy+s24"),
    ("mojeek", "https://www.mojeek.com/search?q=samsung+galaxy+s24"),
    ("bing", "https://www.bing.com/search?q=samsung+galaxy+s24+prix"),
    ("jumia-cd", "https://www.jumia.cd/catalog/?q=samsung"),
    ("startpage", "https://www.startpage.com/sp/search?query=samsung+galaxy+s24"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
}

MARKERS = ("result__a", "b_algo", "prd", "price", "prix", "galaxy", "samsung", "href")


async def probe() -> int:
    ok = 0
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15.0) as client:
        for name, url in TARGETS:
            try:
                response = await client.get(url)
                body = response.text
                hits = [marker for marker in MARKERS if marker in body.lower()]
                print(
                    f"{name:20s} status={response.status_code} bytes={len(body):7d} "
                    f"markers={','.join(hits[:5])}"
                )
                if response.status_code == 200 and len(body) > 3000:
                    ok += 1
            except Exception as exc:  # pragma: no cover - diagnostic uniquement
                print(f"{name:20s} ERREUR {type(exc).__name__}: {exc}")
    print(f"\nSources exploitables: {ok}/{len(TARGETS)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(probe()))
