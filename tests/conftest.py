"""Configuration pytest : environnement isolé avant l'import de l'application."""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="jf-market-tests-")
os.environ["JF_DATA_DIR"] = _TMP
os.environ["JF_AUTH_SECRET"] = "secret-de-test-jf-market-uniquement"
os.environ["JF_RATE_LIMIT"] = "100000"
os.environ["JF_HTTP_TIMEOUT"] = "3"
for _name in ("FIREBASE_API_KEY", "FIREBASE_WEB_API_KEY", "FIREBASE_PROJECT_ID",
              "FIREBASE_STORAGE_BUCKET", "SERPAPI_KEY", "SERP_API_KEY"):
    os.environ.pop(_name, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def seller(client: TestClient) -> dict:
    """Crée un compte vendeur et renvoie {token, user}."""
    import uuid

    email = f"vendeur-{uuid.uuid4().hex[:8]}@example.cd"
    response = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "motdepasse123",
            "role": "vendeur",
            "display_name": "Boutique Test",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def buyer(client: TestClient) -> dict:
    import uuid

    email = f"acheteur-{uuid.uuid4().hex[:8]}@example.cd"
    response = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "motdepasse123",
            "role": "acheteur",
            "display_name": "Acheteur Test",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()
