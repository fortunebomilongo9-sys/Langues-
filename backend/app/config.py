"""Configuration centralisée de JF MARKET.

Toutes les clés sensibles sont lues depuis l'environnement du serveur.
Aucune clé n'est jamais renvoyée vers le navigateur : le frontend ne parle
qu'à l'API FastAPI.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

APP_NAME = "JF MARKET"
APP_VERSION = "1.0.0"
APP_TAGLINE = "Recherchez un article, retrouvez les offres et découvrez les vendeurs."


def _env(*names: str, default: str | None = None) -> str | None:
    """Retourne la première variable d'environnement non vide."""
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, default=str(default)) or default)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(_env(name, default=str(default)) or default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """Paramètres immuables du service."""

    app_name: str = APP_NAME
    version: str = APP_VERSION

    # Serveur
    host: str = field(default_factory=lambda: _env("HOST", default="0.0.0.0") or "0.0.0.0")
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    data_dir: Path = field(default_factory=lambda: Path(_env("JF_DATA_DIR", default="data") or "data"))

    # Firebase (optionnel : mode local si absent)
    firebase_api_key: str | None = field(default_factory=lambda: _env("FIREBASE_API_KEY", "FIREBASE_WEB_API_KEY"))
    firebase_project_id: str | None = field(default_factory=lambda: _env("FIREBASE_PROJECT_ID"))
    firebase_storage_bucket: str | None = field(default_factory=lambda: _env("FIREBASE_STORAGE_BUCKET"))

    # API de recherche commerciale (optionnelle)
    serpapi_key: str | None = field(default_factory=lambda: _env("SERPAPI_KEY", "SERP_API_KEY"))

    # Sécurité des sessions locales
    auth_secret: str = field(
        default_factory=lambda: _env("JF_AUTH_SECRET", default="") or secrets.token_hex(32)
    )
    auth_token_ttl_hours: int = field(default_factory=lambda: _env_int("JF_TOKEN_TTL_HOURS", 168))

    # Réseau / sources
    http_timeout: float = field(default_factory=lambda: _env_float("JF_HTTP_TIMEOUT", 9.0))
    http_total_budget: float = field(default_factory=lambda: _env_float("JF_HTTP_BUDGET", 16.0))
    http_max_pages: int = field(default_factory=lambda: _env_int("JF_MAX_PAGES", 8))
    http_concurrency: int = field(default_factory=lambda: _env_int("JF_HTTP_CONCURRENCY", 5))
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JF-MARKET/1.0"
    )

    # Cache
    cache_ttl_search: int = field(default_factory=lambda: _env_int("JF_CACHE_SEARCH_TTL", 300))
    cache_ttl_page: int = field(default_factory=lambda: _env_int("JF_CACHE_PAGE_TTL", 900))
    cache_max_entries: int = field(default_factory=lambda: _env_int("JF_CACHE_MAX", 400))

    # Limitation de débit (par client)
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("JF_RATE_LIMIT", 40))

    # Taux de conversion indicatif CDF -> USD (uniquement pour comparer un budget)
    usd_cdf_rate: float = field(default_factory=lambda: _env_float("JF_USD_CDF_RATE", 2800.0))

    # Pertinence
    min_results_before_expanding: int = field(default_factory=lambda: _env_int("JF_MIN_RESULTS", 6))
    max_results_hard: int = field(default_factory=lambda: _env_int("JF_MAX_RESULTS", 60))
    image_min_score: float = field(default_factory=lambda: _env_float("JF_IMAGE_MIN_SCORE", 0.45))

    # Upload d'images pour les annonces vendeurs
    upload_max_bytes: int = field(default_factory=lambda: _env_int("JF_UPLOAD_MAX_BYTES", 4 * 1024 * 1024))

    @property
    def firebase_enabled(self) -> bool:
        return bool(self.firebase_api_key and self.firebase_project_id)

    @property
    def storage_enabled(self) -> bool:
        return bool(self.firebase_enabled and self.firebase_storage_bucket)

    @property
    def serpapi_enabled(self) -> bool:
        return bool(self.serpapi_key)

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
