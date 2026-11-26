# JF MARKET — moteur intelligent de recherche commerciale

**Recherchez un article, retrouvez les offres et découvrez les vendeurs.**

JF MARKET interroge de vraies sources commerciales sur Internet, analyse la demande
en langage naturel, associe des images cohérentes aux produits et présente les offres
dans une interface unique. Aucun résultat n'est fabriqué : quand aucune offre fiable
n'existe, l'application l'indique clairement.

Zone de départ : **Kinshasa** (20 communes), architecture prête pour les autres villes de la RDC.

---

## 1. Architecture

```
backend/
  app/
    main.py            FastAPI : sert l'API /api/... et le frontend statique
    config.py          Configuration centralisée (clés lues côté serveur uniquement)
    models.py          Modèles Pydantic (Offer, Listing, AuthUser, SearchIntent...)
    auth.py            Inscription/connexion (Firebase Auth si configuré, sinon local)
    api/               meta, search, listings, account, uploads, deps (auth, rate limit)
    engine/
      query_parser.py  Compréhension de la requête naturelle (produit, marque, modèle,
                       budget, état, commune, ville, fautes, synonymes)
      normalize.py     Normalisation, repli des accents, expansion des termes
      compose.py       Fiche commerciale normalisée + prix/état/commune vérifiables
      scoring.py       Pertinence, budget, cohérence produit/image, tri
      dedupe.py        Anti-doublons (URL normalisée + titre)
      pipeline.py      Recherche progressive : reformulation, synonymes, marque, sources
      cache.py         Cache TTL raisonnable (recherches et pages)
    sources/           Adaptateurs réels : recherche web (DuckDuckGo, Bing, Mojeek),
                       marketplaces, SerpAPI Google Shopping (si clé fournie),
                       extraction JSON-LD / OpenGraph / prix / contacts
    images/            Sélection d'images indépendante + cohérence visuelle produit
    store/             Firestore REST si configuré, sinon persistance locale JSON
frontend/
  index.html           Interface unique (accueil, résultats, annonce, compte, vendeur, favoris)
  styles.css           Design responsive, mode jour / mode nuit
  app.js               Routage client, appels API, filtres, favoris, publication
tests/                 pytest : moteur, composition, déduplication, API complète
```

Un seul processus sert l'interface et l'API : **aucune clé n'est exposée au navigateur**.

## 2. Lancer en local

```bash
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
# http://localhost:8000
```

Tests :

```bash
python3 -m pytest tests -q
```

## 3. Configuration (variables d'environnement, côté serveur)

| Variable | Rôle |
| --- | --- |
| `PORT` / `HOST` | Port et interface d'écoute (défaut `8000` / `0.0.0.0`) |
| `FIREBASE_API_KEY`, `FIREBASE_PROJECT_ID` | Active Firebase Authentication + Firestore |
| `FIREBASE_STORAGE_BUCKET` | Active Firebase Storage pour les images |
| `SERPAPI_KEY` | Active Google Shopping (API commerciale) en complément |
| `JF_AUTH_SECRET` | Secret de signature des sessions locales |
| `JF_DATA_DIR` | Répertoire des données locales (annonces, comptes, uploads) |
| `JF_HTTP_TIMEOUT`, `JF_HTTP_BUDGET`, `JF_MAX_PAGES` | Délais et volume de collecte |
| `JF_CACHE_SEARCH_TTL`, `JF_CACHE_PAGE_TTL`, `JF_RATE_LIMIT` | Cache et limitation de débit |
| `JF_MIN_RESULTS`, `JF_MAX_RESULTS`, `JF_IMAGE_MIN_SCORE` | Seuils de pertinence |

Sans Firebase ni SerpAPI, l'application fonctionne en **mode local** (stockage JSON,
authentification locale signée) et s'appuie sur la recherche web réelle : le moteur
reste pleinement opérationnel, ces clés ajoutent Firestore/Storage et une source payante.

## 4. API principale

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/health` | État du service, des sources et des backends |
| GET | `/api/taxonomy` | Catégories, marques, communes, recherches populaires |
| GET | `/api/sources` | Sources commerciales et leur disponibilité |
| GET | `/api/suggestions?q=` | Reformulations et suggestions de recherche |
| POST | `/api/search` | Recherche commerciale complète (analyse + offres + images) |
| POST | `/api/search/image` | Recherche par image (similarité visuelle) |
| GET | `/api/listings`, `/api/listings/{id}` | Annonces publiées sur JF MARKET |
| GET | `/api/listings/search/local?q=` | Recherche dans les annonces locales |
| POST/PATCH/DELETE | `/api/listings` | Publication, modification, suppression (vendeur) |
| POST | `/api/auth/signup`, `/api/auth/signin` | Comptes acheteur / vendeur |
| GET | `/api/auth/me` | Profil connecté |
| GET/POST/DELETE | `/api/favorites` | Favoris de l'acheteur |
| GET/POST | `/api/history` | Historique de recherche |
| POST | `/api/uploads/image` | Envoi d'image pour une annonce |

## 5. Garanties de fiabilité

- **Aucune invention** : prix, vendeur, adresse, téléphone, disponibilité et description
  proviennent uniquement de la source ; sinon la fiche affiche « Non renseigné ».
- **Images vérifiées** : l'image doit correspondre à la marque/modèle/catégorie détectés ;
  une image illustrative est explicitement étiquetée, jamais présentée comme photo du vendeur.
- **Recherche progressive** : reformulation, synonymes, variantes de nom, marque/référence,
  élargissement des sources — puis arrêt honnête si rien de fiable n'est trouvé.
- **Résilience** : délais, erreurs, sources indisponibles, doublons, cache et limitation de
  débit sont gérés ; une erreur technique ne bloque jamais toute l'application.
- **Vendeurs** : distinction entre vendeur indépendant et boutique commerciale, choisie par
  le vendeur à l'inscription ; un domaine `.cd` n'est jamais considéré comme vérifié.

## 6. Évolution prévue

Ajout de villes et provinces de la RDC, nouvelles sources commerciales, boutiques
partenaires, comptes vendeurs avancés et mise en avant commerciale.
