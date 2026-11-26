"""Tests du moteur : analyse de requête, déduplication, composition, pertinence."""

from __future__ import annotations

from backend.app.engine.compose import compose_offer, offer_from_listing
from backend.app.engine.dedupe import dedupe_offers, normalize_url
from backend.app.engine.normalize import fold
from backend.app.engine.query_parser import build_search_query, parse_query
from backend.app.engine.scoring import rank_offers
from backend.app.models import Listing
from backend.app.sources.base import RawOffer


def _raw(title: str, url: str, **kwargs) -> RawOffer:
    data = {
        "title": title,
        "url": url,
        "source_id": "test",
        "source_name": "Source de test",
        "snippet": kwargs.pop("snippet", ""),
    }
    data.update(kwargs)
    return RawOffer(**data)


def test_fold_supprime_accents_et_casse():
    assert fold("Télévision SAMSUNG à Limete") == "television samsung a limete"


def test_analyse_requete_naturelle_samsung_budget():
    intent = parse_query("Je cherche un bon téléphone Samsung à 200 dollars.")
    assert intent.brand == "Samsung"
    assert intent.category == "telephones"
    assert intent.price_max == 200.0
    assert intent.currency == "USD"
    assert "telephone" in intent.normalized_query


def test_analyse_requete_informatique_modele():
    intent = parse_query("Ordinateur Core i5 pas trop cher")
    assert intent.category == "informatique"
    assert intent.product_model is not None
    assert "i5" in intent.product_model.lower()


def test_analyse_requete_television_pouces():
    intent = parse_query("Je veux acheter une télévision de 43 pouces")
    assert intent.category == "televisions"
    assert intent.product_model is not None
    assert "43" in intent.product_model


def test_analyse_requete_vehicule_ville():
    intent = parse_query("Trouve-moi une voiture Toyota à Kinshasa")
    assert intent.brand == "Toyota"
    assert intent.category == "vehicules"
    assert (intent.city or "").lower().startswith("kinshasa")


def test_analyse_requete_faute_et_commune():
    intent = parse_query("telephone samsun occasion a Limete")
    assert intent.brand == "Samsung"  # corrigé depuis "samsun"
    assert intent.condition == "occasion"
    assert intent.commune == "Limete"


def test_analyse_requete_originale_corrigee():
    intent = parse_query("Cherche une chaussure Nike originale")
    assert intent.brand == "Nike"
    assert intent.category == "mode"
    assert intent.corrections.get("originale") == "original"


def test_build_search_query_contient_marque_et_produit():
    intent = parse_query("téléphone Samsung Galaxy")
    query = build_search_query(intent)
    assert "samsung" in query.lower()
    assert "kinshasa" in query.lower() or "telephone" in query.lower()


def test_normalize_url_supprime_parametres_de_suivi():
    left = normalize_url("https://exemple.cd/produit/123?utm_source=fb&fbclid=abc")
    right = normalize_url("https://exemple.cd/produit/123")
    assert left == right


def test_dedupe_par_url_et_par_titre():
    offers = [
        _raw("Samsung Galaxy S24 Ultra 256Go", "https://boutique-a.cd/p/1?utm_source=x"),
        _raw("Samsung Galaxy S24 Ultra 256Go", "https://boutique-a.cd/p/1"),
        _raw("Samsung Galaxy S24 Ultra 256Go", "https://boutique-b.cd/annonce/99"),
    ]
    composed = [compose_offer(item, parse_query("samsung galaxy s24 ultra")) for item in offers]
    unique = dedupe_offers(composed)
    assert len(unique) == 2


def test_composition_offre_ne_devine_ni_prix_ni_vendeur():
    intent = parse_query("téléphone Samsung")
    raw = _raw(
        "Samsung Galaxy A15 128Go",
        "https://exemple.cd/galaxy-a15",
        snippet="Disponible à Kinshasa, Gombe. Prix : 185 USD.",
    )
    offer = compose_offer(raw, intent)
    assert offer.title.startswith("Samsung Galaxy A15")
    assert offer.price == 185.0
    assert offer.currency == "USD"
    assert offer.commune == "Gombe"
    assert offer.seller_name is None
    assert offer.seller_type == "inconnu"
    assert offer.contact.phone is None


def test_composition_sans_prix_affiche_non_renseigne():
    intent = parse_query("téléphone Samsung")
    offer = compose_offer(_raw("Samsung Galaxy A05", "https://exemple.cd/a05"), intent)
    assert offer.price is None
    assert offer.price_display == "Non renseigné"


def test_annonce_locale_devient_une_offre_recherchable():
    listing = Listing(
        id="lst-1",
        seller_uid="uid-1",
        seller_name="Boutique Kin",
        seller_type="boutique",
        title="iPhone 13 128Go occasion",
        description="Bon état, livraison à Ngaliema.",
        price=520,
        currency="USD",
        condition="occasion",
        category="telephones",
        brand="Apple",
        commune="Ngaliema",
        images=["https://exemple.cd/iphone13.jpg"],
        contact_phone="+243000000000",
    )
    offer = offer_from_listing(listing, parse_query("iphone 13 occasion"))
    assert offer.is_user_listing is True
    assert offer.seller_name == "Boutique Kin"
    assert offer.seller_type == "boutique"
    assert offer.commune == "Ngaliema"
    assert offer.price == 520
    assert offer.source_url.endswith("lst-1")


def test_pertinence_ecarte_offre_hors_sujet():
    intent = parse_query("téléphone Samsung")
    pertinent = compose_offer(
        _raw("Samsung Galaxy S23 neuf", "https://exemple.cd/s23", snippet="Samsung Galaxy S23"),
        intent,
    )
    hors_sujet = compose_offer(
        _raw("Toyota Corolla 2015 essence", "https://exemple.cd/corolla", snippet="Voiture Toyota"),
        intent,
    )
    ranked = rank_offers([pertinent, hors_sujet], intent)
    titles = [offer.title for offer in ranked]
    assert "Samsung Galaxy S23 neuf" in titles
    assert "Toyota Corolla 2015 essence" not in titles
