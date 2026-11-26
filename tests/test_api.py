"""Tests de l'API : catalogue, comptes, favoris, annonces, validations."""

from __future__ import annotations

import io


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _offer_payload() -> dict:
    return {
        "id": "offre-test-1",
        "title": "Samsung Galaxy A15 128Go",
        "description": "Neuf, scellé",
        "brand": "Samsung",
        "price": 185.0,
        "currency": "USD",
        "price_display": "185 USD",
        "condition": "neuf",
        "availability": "disponible",
        "seller_name": "Boutique Kin",
        "seller_type": "boutique",
        "commune": "Gombe",
        "city": "Kinshasa",
        "source_id": "test",
        "source_name": "Source de test",
        "source_url": "https://exemple.cd/galaxy-a15",
        "site_domain": "exemple.cd",
        "relevance_score": 0.9,
    }


def test_health_indique_le_mode_de_stockage(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "JF MARKET"
    assert body["status"] == "ok"
    assert body["auth_provider"] in {"local", "firebase"}
    assert body["storage"] in {"local", "firestore"}


def test_taxonomie_expose_les_communes_de_kinshasa(client):
    response = client.get("/api/taxonomy")
    assert response.status_code == 200
    body = response.json()
    assert len(body["categories"]) >= 10
    assert "Gombe" in body["communes"]
    assert "Limete" in body["communes"]
    assert len(body["communes"]) == 20
    assert body["trending"]
    assert body["brands"]


def test_sources_declare_les_adaptateurs(client):
    response = client.get("/api/sources")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert all("name" in source for source in body["sources"])


def test_suggestions_reformulent_une_requete_partielle(client):
    response = client.get("/api/suggest", params={"q": "telephone samsun"})
    assert response.status_code == 200
    body = response.json()
    assert body["brand"] == "Samsung"
    assert isinstance(body["suggestions"], list)


def test_inscription_connexion_et_profil(client, buyer):
    assert buyer["user"]["role"] == "acheteur"
    assert buyer["token"]
    me = client.get("/api/auth/me", headers=_auth(buyer["token"]))
    assert me.status_code == 200
    assert me.json()["email"] == buyer["user"]["email"]

    signin = client.post(
        "/api/auth/signin",
        json={"email": buyer["user"]["email"], "password": "motdepasse123"},
    )
    assert signin.status_code == 200
    assert signin.json()["token"]


def test_mot_de_passe_incorrect_refuse(client, buyer):
    response = client.post(
        "/api/auth/signin",
        json={"email": buyer["user"]["email"], "password": "mauvais-mot-de-passe"},
    )
    assert response.status_code == 401


def test_acces_protege_sans_jeton(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/favorites").status_code == 401


def test_favoris_cycle_complet(client, buyer):
    headers = _auth(buyer["token"])
    created = client.post("/api/favorites", json={"offer": _offer_payload()}, headers=headers)
    assert created.status_code == 200, created.text
    favorite = created.json()["favorite"]
    assert favorite["offer"]["title"] == "Samsung Galaxy A15 128Go"

    listed = client.get("/api/favorites", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    removed = client.delete(f"/api/favorites/{favorite['id']}", headers=headers)
    assert removed.status_code == 200
    assert client.get("/api/favorites", headers=headers).json()["count"] == 0


def test_historique_de_recherche(client, buyer):
    headers = _auth(buyer["token"])
    created = client.post(
        "/api/history",
        json={"query": "téléphone samsung", "intent_summary": "Téléphones · Samsung", "results": 4},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    history = client.get("/api/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["count"] >= 1


def test_acheteur_ne_peut_pas_publier(client, buyer):
    response = client.post(
        "/api/listings",
        json={"title": "Téléphone à vendre", "price": 100},
        headers=_auth(buyer["token"]),
    )
    assert response.status_code == 403


def test_vendeur_publie_modifie_et_supprime(client, seller):
    headers = _auth(seller["token"])
    payload = {
        "title": "Télévision Samsung 43 pouces",
        "description": "Smart TV neuve, garantie boutique.",
        "price": 320,
        "currency": "USD",
        "condition": "neuf",
        "category": "televisions",
        "brand": "Samsung",
        "product_model": "43 pouces",
        "commune": "Limete",
        "contact_whatsapp": "+243000000000",
    }
    created = client.post("/api/listings", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    listing = created.json()["listing"]
    assert listing["seller_name"] == "Boutique Test"
    assert listing["commune"] == "Limete"

    mine = client.get("/api/listings/mine", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["count"] == 1

    public = client.get("/api/listings")
    assert public.status_code == 200
    assert any(item["id"] == listing["id"] for item in public.json()["listings"])

    local = client.get("/api/listings/search/local", params={"q": "television"})
    assert local.status_code == 200
    assert any(item["id"] == listing["id"] for item in local.json()["listings"])

    updated = client.patch(
        f"/api/listings/{listing['id']}", json={"price": 300}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["listing"]["price"] == 300

    deleted = client.delete(f"/api/listings/{listing['id']}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/listings/{listing['id']}").status_code == 404


def test_annonce_non_modifiable_par_un_autre_vendeur(client, seller):
    headers = _auth(seller["token"])
    created = client.post(
        "/api/listings",
        json={"title": "Ordinateur portable HP", "price": 250},
        headers=headers,
    ).json()["listing"]

    import uuid

    other = client.post(
        "/api/auth/signup",
        json={
            "email": f"autre-{uuid.uuid4().hex[:8]}@example.cd",
            "password": "motdepasse123",
            "role": "vendeur",
            "display_name": "Autre Boutique",
        },
    ).json()

    response = client.patch(
        f"/api/listings/{created['id']}",
        json={"price": 1},
        headers=_auth(other["token"]),
    )
    assert response.status_code == 403


def test_recherche_refuse_une_requete_vide(client):
    assert client.post("/api/search", json={"query": "   "}).status_code == 422
    assert client.post("/api/search", json={}).status_code == 422


def test_recherche_image_refuse_un_fichier_non_image(client):
    response = client.post(
        "/api/search/image",
        files={"file": ("notes.txt", io.BytesIO(b"pas une image"), "text/plain")},
    )
    assert response.status_code in {400, 415}
