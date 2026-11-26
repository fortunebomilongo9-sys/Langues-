"""Point d'entrée de JF MARKET : FastAPI + frontend HTML/CSS/JS.

Un seul processus sert l'API (`/api/...`) et l'interface (fichiers statiques),
ce qui évite toute exposition de clé côté navigateur.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import account, listings, meta, search, uploads
from .config import get_settings
from .store.repository import Repository

logger = logging.getLogger("jfmarket")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

PAGES = ("/", "/recherche", "/annonce", "/compte", "/vendeur", "/favoris", "/a-propos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repository = Repository()
    app.state.repository = repository
    logger.info(
        "JF MARKET prêt — auth=%s stockage=%s frontend=%s",
        "firebase" if settings.firebase_enabled else "local",
        type(repository.backend).__name__,
        FRONTEND_DIR,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="JF MARKET",
        description=(
            "Moteur de recherche commercial intelligent : analyse de la demande, "
            "recherche d'offres réelles, images vérifiées et annonces locales."
        ),
        version=settings.version,
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # noqa: ANN001
        logger.exception("Erreur non gérée sur %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    "Une erreur technique est survenue. Réessayez dans un instant : "
                    "aucun résultat n'est inventé pour combler l'incident."
                )
            },
        )

    for module in (meta, search, listings, account, uploads):
        app.include_router(module.router)

    if (settings.uploads_dir).exists():
        app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")

    assets = FRONTEND_DIR
    if assets.exists():
        app.mount("/static", StaticFiles(directory=assets), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(assets / "index.html")

        @app.get("/recherche", include_in_schema=False)
        @app.get("/annonce/{offer_id}", include_in_schema=False)
        @app.get("/compte", include_in_schema=False)
        @app.get("/vendeur", include_in_schema=False)
        @app.get("/favoris", include_in_schema=False)
        @app.get("/a-propos", include_in_schema=False)
        async def spa(offer_id: str | None = None) -> FileResponse:  # noqa: ARG001
            return FileResponse(assets / "index.html")

        @app.get("/favicon.svg", include_in_schema=False)
        async def favicon() -> FileResponse:
            return FileResponse(assets / "favicon.svg")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    conf = get_settings()
    uvicorn.run("backend.app.main:app", host=conf.host, port=conf.port, reload=False)
