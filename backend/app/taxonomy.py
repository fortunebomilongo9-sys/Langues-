"""Taxonomie de JF MARKET : catégories, marques, communes de Kinshasa,
synonymes et expressions commerciales courantes (français / lingala / argot local).

Toutes les clés de dictionnaire sont écrites en forme « repliée »
(minuscules, sans accents, sans ponctuation) pour rester comparables aux
tokens produits par :mod:`app.engine.normalize`.
"""

from __future__ import annotations

CATEGORIES: list[dict] = [
    {
        "id": "telephones",
        "label": "Téléphones & accessoires",
        "icon": "📱",
        "keywords": [
            "telephone", "smartphone", "gsm", "portable", "mobile", "iphone", "samsung",
            "tecno", "infinix", "itel", "oppo", "xiaomi", "redmi", "nokia", "huawei",
            "chargeur", "ecouteur", "ecouteurs", "casque", "power bank", "coque",
            "batterie externe", "carte memoire", "telephone portable",
        ],
        "subcategories": [
            {"id": "smartphones", "label": "Smartphones", "keywords": ["smartphone", "telephone", "gsm", "iphone", "galaxy"]},
            {"id": "accessoires-telephone", "label": "Accessoires & chargeurs", "keywords": ["chargeur", "ecouteur", "casque", "coque", "power bank", "cable"]},
        ],
    },
    {
        "id": "informatique",
        "label": "Ordinateurs & informatique",
        "icon": "💻",
        "keywords": [
            "ordinateur", "laptop", "pc", "pc portable", "notebook", "macbook", "hp", "dell",
            "lenovo", "thinkpad", "ideapad", "asus", "acer", "toshiba", "imprimante",
            "scanner", "clavier", "souris", "ecran", "disque dur", "ssd", "ram", "processeur",
            "core i3", "core i5", "core i7", "ryzen", "onduleur",
        ],
        "subcategories": [
            {"id": "ordinateurs-portables", "label": "Ordinateurs portables", "keywords": ["laptop", "pc portable", "notebook", "macbook", "ideapad", "thinkpad"]},
            {"id": "ordinateurs-bureau", "label": "Ordinateurs de bureau", "keywords": ["ordinateur de bureau", "desktop", "unite centrale"]},
            {"id": "peripheriques", "label": "Périphériques & réseau", "keywords": ["imprimante", "scanner", "clavier", "souris", "routeur", "onduleur"]},
        ],
    },
    {
        "id": "televisions",
        "label": "Téléviseurs & électronique",
        "icon": "📺",
        "keywords": [
            "television", "tv", "televiseur", "ecran plat", "led", "oled", "smart tv",
            "home cinema", "decoder", "canal", "sony", "lg", "hisense", "tcl", "philips",
            "jbl", "barre de son", "enceinte", "groupe electrogene", "ventilateur",
        ],
        "subcategories": [
            {"id": "televiseurs", "label": "Téléviseurs", "keywords": ["television", "tv", "smart tv", "led tv"]},
            {"id": "audio-video", "label": "Audio & vidéo", "keywords": ["enceinte", "home cinema", "barre de son", "decoder"]},
        ],
    },
    {
        "id": "mode",
        "label": "Vêtements & chaussures",
        "icon": "👟",
        "keywords": [
            "vetement", "vetements", "habit", "chaussure", "chaussures", "sneakers", "basket",
            "nike", "adidas", "puma", "reebok", "jean", "chemise", "robe", "costume",
            "pantalon", "sac", "sac a main", "montre", "lunettes", "casquette",
        ],
        "subcategories": [
            {"id": "chaussures", "label": "Chaussures & sneakers", "keywords": ["chaussure", "sneakers", "basket", "nike", "adidas"]},
            {"id": "vetements", "label": "Vêtements", "keywords": ["vetement", "jean", "chemise", "robe", "costume", "pantalon"]},
            {"id": "accessoires-mode", "label": "Sacs, montres & lunettes", "keywords": ["sac", "montre", "lunettes", "casquette"]},
        ],
    },
    {
        "id": "vehicules",
        "label": "Véhicules & pièces auto",
        "icon": "🚗",
        "keywords": [
            "voiture", "vehicule", "auto", "camion", "moto", "scooter", "toyota", "mercedes",
            "nissan", "hyundai", "kia", "honda", "mitsubishi", "peugeot", "suzuki", "rav4",
            "prado", "hilux", "corolla", "pneus", "jante", "piece detachee", "batterie voiture",
        ],
        "subcategories": [
            {"id": "voitures", "label": "Voitures", "keywords": ["voiture", "toyota", "mercedes", "nissan", "hyundai"]},
            {"id": "motos", "label": "Motos & scooters", "keywords": ["moto", "scooter"]},
            {"id": "pieces-auto", "label": "Pièces & accessoires auto", "keywords": ["pneu", "jante", "piece detachee", "batterie"]},
        ],
    },
    {
        "id": "maison",
        "label": "Meubles & équipement domestique",
        "icon": "🛋️",
        "keywords": [
            "meuble", "meubles", "salon", "canape", "chaise", "table", "lit", "matelas",
            "armoire", "commode", "refrigerateur", "frigo", "congelateur", "cuisiniere",
            "micro onde", "climatiseur", "clim", "machine a laver", "ustensile", "vaisselle",
        ],
        "subcategories": [
            {"id": "meubles", "label": "Meubles", "keywords": ["meuble", "salon", "canape", "lit", "matelas", "armoire"]},
            {"id": "electromenager", "label": "Électroménager", "keywords": ["refrigerateur", "frigo", "cuisiniere", "micro onde", "climatiseur", "machine a laver"]},
        ],
    },
    {
        "id": "professionnel",
        "label": "Matériel professionnel",
        "icon": "🏭",
        "keywords": [
            "materiel professionnel", "machine", "compresseur", "soudeuse", "groupe electrogene",
            "malaxeur", "betonniere", "outillage", "coffre fort", "caisse enregistreuse",
            "imprimante thermique", "salon de coiffure", "materiel medical",
        ],
        "subcategories": [
            {"id": "btp", "label": "Matériel BTP", "keywords": ["malaxeur", "betonniere", "compresseur", "echafaudage"]},
            {"id": "atelier", "label": "Outillage & ateliers", "keywords": ["outillage", "soudeuse", "machine"]},
        ],
    },
    {
        "id": "alimentation",
        "label": "Produits alimentaires",
        "icon": "🍚",
        "keywords": [
            "alimentaire", "nourriture", "riz", "haricot", "farine", "huile", "sucre", "sel",
            "poisson", "poulet", "viande", "epices", "boisson", "eau", "jus", "lait",
        ],
        "subcategories": [
            {"id": "vivres", "label": "Vivres & épices", "keywords": ["riz", "haricot", "farine", "huile", "epices"]},
            {"id": "boissons", "label": "Boissons", "keywords": ["boisson", "eau", "jus", "lait"]},
        ],
    },
    {
        "id": "beaute",
        "label": "Beauté & soins",
        "icon": "💅",
        "keywords": [
            "beaute", "cosmetique", "parfum", "creme", "savon", "shampoo", "maquillage",
            "mascara", "rouge a levre", "perruque", "mousse", "lotion", "gel douche",
            "produit capillaire", "tresse", "ongle",
        ],
        "subcategories": [
            {"id": "soins", "label": "Soins de la peau", "keywords": ["creme", "lotion", "savon", "shampoo"]},
            {"id": "parfums", "label": "Parfums & maquillage", "keywords": ["parfum", "maquillage", "rouge a levre", "mascara"]},
        ],
    },
    {
        "id": "construction",
        "label": "Matériel de construction",
        "icon": "🧱",
        "keywords": [
            "construction", "ciment", "brique", "parpaing", "fer a beton", "toles", "tole",
            "carreaux", "carrelage", "peinture", "plomberie", "tuyau", "cable electrique",
            "portail", "fenetre", "aluminium", "vitre", "sable", "gravier",
        ],
        "subcategories": [
            {"id": "materiaux", "label": "Matériaux", "keywords": ["ciment", "brique", "parpaing", "fer a beton", "sable"]},
            {"id": "second-oeuvre", "label": "Toiture, carrelage & peinture", "keywords": ["tole", "carreaux", "peinture", "portail", "fenetre"]},
        ],
    },
]

CATEGORY_BY_ID: dict[str, dict] = {category["id"]: category for category in CATEGORIES}

# Marques connues : nom canonique -> (alias repliés, domaines officiels pour l'image)
BRANDS: dict[str, dict] = {
    "Samsung": {"aliases": ["samsung", "galaxy", "samsun", "samung"], "domains": ["samsung.com"]},
    "Apple": {"aliases": ["apple", "iphone", "ipad", "macbook", "airpods"], "domains": ["apple.com"]},
    "Tecno": {"aliases": ["tecno", "tecno mobile"], "domains": ["tecno-mobile.com"]},
    "Infinix": {"aliases": ["infinix"], "domains": ["infinixmobility.com"]},
    "Itel": {"aliases": ["itel"], "domains": ["itel-mobile.com"]},
    "Xiaomi": {"aliases": ["xiaomi", "redmi", "poco", "mi"], "domains": ["mi.com"]},
    "Oppo": {"aliases": ["oppo"], "domains": ["oppo.com"]},
    "Nokia": {"aliases": ["nokia"], "domains": ["nokia.com"]},
    "Huawei": {"aliases": ["huawei"], "domains": ["huawei.com"]},
    "HP": {"aliases": ["hp", "hewlett packard", "pavilion", "probook", "elitebook"], "domains": ["hp.com"]},
    "Dell": {"aliases": ["dell", "latitude", "inspiron", "vostro", "xps"], "domains": ["dell.com"]},
    "Lenovo": {"aliases": ["lenovo", "thinkpad", "ideapad", "legion"], "domains": ["lenovo.com"]},
    "Asus": {"aliases": ["asus", "vivobook", "zenbook"], "domains": ["asus.com"]},
    "Acer": {"aliases": ["acer", "aspire", "predator"], "domains": ["acer.com"]},
    "Toshiba": {"aliases": ["toshiba"], "domains": ["toshiba.com"]},
    "Sony": {"aliases": ["sony", "playstation", "ps5", "ps4"], "domains": ["sony.com"]},
    "LG": {"aliases": ["lg"], "domains": ["lg.com"]},
    "Hisense": {"aliases": ["hisense"], "domains": ["hisense.com"]},
    "TCL": {"aliases": ["tcl"], "domains": ["tcl.com"]},
    "Philips": {"aliases": ["philips"], "domains": ["philips.com"]},
    "JBL": {"aliases": ["jbl"], "domains": ["jbl.com"]},
    "Anker": {"aliases": ["anker", "soundcore"], "domains": ["anker.com"]},
    "Nike": {"aliases": ["nike", "air max", "jordan"], "domains": ["nike.com"]},
    "Adidas": {"aliases": ["adidas", "yeezy"], "domains": ["adidas.com"]},
    "Puma": {"aliases": ["puma"], "domains": ["puma.com"]},
    "Reebok": {"aliases": ["reebok"], "domains": ["reebok.com"]},
    "Toyota": {"aliases": ["toyota", "rav4", "prado", "hilux", "corolla", "land cruiser"], "domains": ["toyota.com"]},
    "Mercedes": {"aliases": ["mercedes", "mercedes benz", "benz"], "domains": ["mercedes-benz.com"]},
    "Nissan": {"aliases": ["nissan", "x-trail", "xtrail"], "domains": ["nissan-global.com"]},
    "Hyundai": {"aliases": ["hyundai", "tucson"], "domains": ["hyundai.com"]},
    "Kia": {"aliases": ["kia", "sportage"], "domains": ["kia.com"]},
    "Honda": {"aliases": ["honda", "crv", "cr-v"], "domains": ["honda.com"]},
    "Mitsubishi": {"aliases": ["mitsubishi"], "domains": ["mitsubishi-motors.com"]},
    "Peugeot": {"aliases": ["peugeot"], "domains": ["peugeot.com"]},
    "Suzuki": {"aliases": ["suzuki"], "domains": ["globalsuzuki.com"]},
    "Canon": {"aliases": ["canon"], "domains": ["canon.com"]},
    "Epson": {"aliases": ["epson"], "domains": ["epson.com"]},
    "Bosch": {"aliases": ["bosch"], "domains": ["bosch.com"]},
}

# Forme repliée -> marque canonique (les alias multi-mots restent utilisables
# par recherche de séquence dans :func:`app.engine.query_parser.parse_query`).
BRAND_ALIASES: dict[str, str] = {}
for _brand, _info in BRANDS.items():
    BRAND_ALIASES[_brand.lower()] = _brand
    for _alias in _info["aliases"]:
        BRAND_ALIASES[_alias] = _brand

# Communes de Kinshasa (référentiel de la première version).
COMMUNES: list[str] = [
    "Gombe", "Limete", "Ngaliema", "Kintambo", "Bandalungwa", "Kalamu", "Barumbu",
    "Lingwala", "Lemba", "Matete", "Ngaba", "Masina", "N'djili", "Kimbanseke",
    "Mont-Ngafula", "Selembao", "Bumbu", "Makala", "Kisenso", "Nsele",
]

COMMUNE_ALIASES: dict[str, str] = {
    "gombe": "Gombe",
    "limete": "Limete",
    "limette": "Limete",
    "ngaliema": "Ngaliema",
    "kintambo": "Kintambo",
    "bandal": "Bandalungwa",
    "bandalungwa": "Bandalungwa",
    "kalamu": "Kalamu",
    "barumbu": "Barumbu",
    "lingwala": "Lingwala",
    "lemba": "Lemba",
    "matete": "Matete",
    "ngaba": "Ngaba",
    "masina": "Masina",
    "ndjili": "N'djili",
    "ndjili": "N'djili",
    "kimbanseke": "Kimbanseke",
    "mont ngafula": "Mont-Ngafula",
    "montngafula": "Mont-Ngafula",
    "ngafula": "Mont-Ngafula",
    "selembao": "Selembao",
    "bumbu": "Bumbu",
    "makala": "Makala",
    "kisenso": "Kisenso",
    "nsele": "Nsele",
}

CITIES: dict[str, str] = {
    "kinshasa": "Kinshasa",
    "kin": "Kinshasa",
    "kin la belle": "Kinshasa",
    "kinshasa la belle": "Kinshasa",
    "lubumbashi": "Lubumbashi",
    "goma": "Goma",
    "bukavu": "Bukavu",
    "matadi": "Matadi",
    "kolwezi": "Kolwezi",
    "kananga": "Kananga",
    "mbuji mayi": "Mbuji-Mayi",
    "kisangani": "Kisangani",
}

# Synonymes et expressions locales. Clé repliée -> remplacement canonique.
SYNONYMS: dict[str, str] = {
    # Lingala / argot de Kinshasa
    "motuka": "voiture",
    "mutuka": "voiture",
    "bilamba": "vetements",
    "elamba": "vetement",
    "bapato": "chaussures",
    "pato": "chaussure",
    "sapato": "chaussures",
    "kiti": "chaise",
    "ndaku": "maison",
    "mbongo": "argent",
    "ya solo": "original",
    "solo": "original",
    "talatale": "cher",
    # Vocabulaire commercial francophone
    "portable": "smartphone",
    "gsm": "smartphone",
    "cellulaire": "smartphone",
    "telephone": "smartphone",
    "telephone mobile": "smartphone",
    "tele": "television",
    "tv": "television",
    "televiseur": "television",
    "ordi": "ordinateur",
    "laptop": "ordinateur portable",
    "notebook": "ordinateur portable",
    "pc": "ordinateur",
    "unite centrale": "ordinateur de bureau",
    "frigo": "refrigerateur",
    "frigidaire": "refrigerateur",
    "congelo": "congelateur",
    "clim": "climatiseur",
    "sneakers": "chaussures",
    "basket": "chaussures",
    "baskets": "chaussures",
    "souliers": "chaussures",
    "habit": "vetement",
    "fringues": "vetements",
    "meubles": "meuble",
    "cuisiniere": "cuisiniere",
    "piece detachee": "pieces auto",
    "pieces detachees": "pieces auto",
    "auto": "voiture",
    "vehicule": "voiture",
    "bagnole": "voiture",
    "okaz": "occasion",
    "seconde main": "occasion",
    "deuxieme main": "occasion",
    "2eme main": "occasion",
    "usage": "occasion",
    "usable": "occasion",
    "refurb": "reconditionne",
    "reconditionne": "reconditionne",
    "brand new": "neuf",
    "scelle": "neuf",
    "emballe": "neuf",
    "jamais utilise": "neuf",
    "nouveau": "neuf",
    "copie": "contrefacon",
    "fake": "contrefacon",
    "magasin": "boutique",
    "shop": "boutique",
}

# Expressions complètes à traiter avant la tokenisation.
PHRASES: list[tuple[str, str]] = [
    ("pas trop cher", "budget reduit"),
    ("pas cher", "budget reduit"),
    ("bon prix", "budget reduit"),
    ("petit prix", "budget reduit"),
    ("mbongo mingi te", "budget reduit"),
    ("pas trop de mbongo", "budget reduit"),
    ("je cherche", ""),
    ("je recherche", ""),
    ("je veux acheter", ""),
    ("je veux", ""),
    ("j'aimerais", ""),
    ("trouve moi", ""),
    ("trouvez moi", ""),
    ("cherche moi", ""),
    ("cherche", ""),
    ("recherche", ""),
    ("je suis a la recherche de", ""),
    ("quelqu'un vend", ""),
    ("qui vend", ""),
    ("a vendre", ""),
    ("en vente", ""),
    ("prix de", ""),
    ("combien coute", ""),
    ("donne moi", ""),
]

STOPWORDS: set[str] = {
    "a", "au", "aux", "avec", "bon", "bonne", "bien", "c", "ca", "ce", "ces", "cet",
    "cette", "comme", "d", "dans", "de", "dee", "des", "du", "elle", "en", "et", "eu",
    "fait", "il", "j", "je", "l", "la", "le", "les", "leur", "lui", "ma", "mais", "me",
    "meme", "mes", "moi", "mon", "ne", "nos", "notre", "nous", "on", "ou", "par", "pas",
    "plus", "pour", "pouvoir", "prix", "qu", "que", "qui", "s", "sa", "se", "selon",
    "ses", "si", "son", "sont", "sur", "t", "ta", "te", "tes", "toi", "ton", "tous",
    "tout", "toute", "tu", "un", "une", "vos", "votre", "vous", "y", "svp", "stp",
    "merci", "s il", "plait", "svp", "acheter", "achat", "vendre", "vente", "vends",
    "cherche", "chercher", "recherche", "rechercher", "trouve", "trouver", "veux",
    "vouloir", "souhaite", "aimerais", "besoin", "envie", "article", "articles",
    "produit", "produits", "disponible", "disponibles", "vendu", "vendue",
}

# État du produit : forme repliée -> état normalisé.
CONDITION_WORDS: dict[str, str] = {
    "neuf": "neuf",
    "neuve": "neuf",
    "nouveau": "neuf",
    "nouvelle": "neuf",
    "scelle": "neuf",
    "emballe": "neuf",
    "occasion": "occasion",
    "occase": "occasion",
    "okaz": "occasion",
    "usage": "occasion",
    "usee": "occasion",
    "reconditionne": "reconditionne",
    "reconditionnee": "reconditionne",
    "refurbished": "reconditionne",
    "refurb": "reconditionne",
    "restaure": "reconditionne",
}

AVAILABILITY_WORDS: dict[str, str] = {
    "disponible": "disponible",
    "en stock": "disponible",
    "stock": "disponible",
    "en vente": "disponible",
    "rupture": "non confirmee",
    "non disponible": "non confirmee",
    "vendu": "non confirmee",
    "epuise": "non confirmee",
}

# Devises reconnues dans une requête ou sur une page.
CURRENCY_ALIASES: dict[str, str] = {
    "dollar": "USD", "dollars": "USD", "usd": "USD", "us$": "USD", "$": "USD",
    "buck": "USD", "bucks": "USD",
    "euro": "EUR", "euros": "EUR", "eur": "EUR", "€": "EUR",
    "fc": "CDF", "cdf": "CDF", "franc": "CDF", "francs": "CDF",
    "franc congolais": "CDF", "francs congolais": "CDF", "congolais": "CDF",
}

# Signaux commerciaux : un lien trouvé sur le web n'est retenu comme offre que
# s'il présente au moins un de ces indices (titre, extrait ou page).
COMMERCIAL_SIGNALS: tuple[str, ...] = (
    "prix", "price", "acheter", "achat", "vente", "vendre", "boutique", "magasin",
    "shop", "commander", "panier", "cart", "stock", "livraison", "annonce", "occasion",
    "neuf", "fc", "cdf", "usd", "promo", "promotion", "deal", "oferta",
)

# Sources connues avec sélecteurs de cartes produit (config-driven, extensible).
SITE_CONFIGS: list[dict] = [
    {
        "id": "jumia-cd",
        "label": "Jumia RDC",
        "domains": ["jumia.cd"],
        "search_url": "https://www.jumia.cd/catalog/?q={query}",
        "card_selector": "article.prd, article._fb",
        "title_selector": "h3.name, .name",
        "price_selector": ".prc, .price",
        "image_selector": "img.img, img",
        "link_selector": "a.core, a",
        "seller_selector": ".badge, .seller",
        "currency": "CDF",
        "trust": 0.75,
    },
    {
        "id": "jumia-ke",
        "label": "Jumia Kenya",
        "domains": ["jumia.co.ke"],
        "search_url": "https://www.jumia.co.ke/catalog/?q={query}",
        "card_selector": "article.prd, article._fb",
        "title_selector": "h3.name, .name",
        "price_selector": ".prc, .price",
        "image_selector": "img.img, img",
        "link_selector": "a.core, a",
        "seller_selector": ".badge, .seller",
        "currency": "KES",
        "trust": 0.7,
    },
]

SITE_CONFIG_BY_DOMAIN: dict[str, dict] = {
    domain: config for config in SITE_CONFIGS for domain in config["domains"]
}

# Marchés/petites annonces considérés comme sources « boutique ».
MARKETPLACE_DOMAINS: set[str] = {
    "jumia.cd", "jumia.co.ke", "amazon.com", "amazon.fr", "aliexpress.com",
    "alibaba.com", "ebay.com", "cdiscount.com", "fnac.com", "konga.com",
    "jumia.com.ng", "pricecheck.co.za", "ubuy.co.cd", "ubuy.cd",
}

# Recherches populaires proposées en page d'accueil (contenu éditorial, pas un
# résultat commercial : aucun prix ni vendeur n'y est inventé).
TRENDING_SEARCHES_2026: list[dict] = [
    {"label": "Samsung Galaxy S24 Ultra", "query": "Samsung Galaxy S24 Ultra", "category": "telephones"},
    {"label": "iPhone 13", "query": "iPhone 13", "category": "telephones"},
    {"label": "Tecno Camon 30", "query": "Tecno Camon 30", "category": "telephones"},
    {"label": "PC portable Core i5", "query": "ordinateur portable Core i5", "category": "informatique"},
    {"label": "MacBook Air M2", "query": "MacBook Air M2", "category": "informatique"},
    {"label": "Téléviseur 43 pouces", "query": "television 43 pouces", "category": "televisions"},
    {"label": "Chaussures Nike Air Max", "query": "chaussures Nike Air Max", "category": "mode"},
    {"label": "Toyota RAV4", "query": "Toyota RAV4", "category": "vehicules"},
    {"label": "Groupe électrogène", "query": "groupe electrogene", "category": "professionnel"},
    {"label": "Salon 7 places", "query": "salon 7 places", "category": "maison"},
    {"label": "Ciment", "query": "ciment", "category": "construction"},
    {"label": "Parfum original", "query": "parfum original", "category": "beaute"},
]

POPULAR_BRANDS: list[str] = [
    "Samsung", "Apple", "Tecno", "Infinix", "Xiaomi", "HP", "Dell", "Lenovo",
    "Hisense", "LG", "Sony", "Nike", "Adidas", "Toyota", "Mercedes", "Nissan",
]

IMAGE_SOURCE_LABELS: dict[str, str] = {
    "vendeur": "Image publiée par le vendeur",
    "fabricant": "Image du site officiel du fabricant",
    "commercial": "Image d'une source commerciale fiable",
    "illustratif": "Image illustrative (non vérifiée)",
}

CONDITION_LABELS: dict[str, str] = {
    "neuf": "Neuf",
    "occasion": "Occasion",
    "reconditionne": "Reconditionné",
    "inconnu": "Non renseigné",
}

SELLER_TYPE_LABELS: dict[str, str] = {
    "boutique": "Boutique",
    "particulier": "Vendeur indépendant",
    "inconnu": "Non renseigné",
}

NOT_PROVIDED = "Non renseigné"
