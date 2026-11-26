/**
 * JF MARKET — logique de l'interface.
 *
 * Aucune clé n'est présente ici : toutes les requêtes passent par l'API
 * Python du même domaine, qui seule contacte les sources commerciales.
 */

const API = "/api";
const TOKEN_KEY = "jf:token";
const THEME_KEY = "jf:theme";

const CONDITION_LABELS = {
  neuf: "Neuf",
  occasion: "Occasion",
  reconditionne: "Reconditionné",
  inconnu: "État non renseigné",
};

const SELLER_LABELS = {
  particulier: "Vendeur indépendant",
  boutique: "Boutique commerciale",
  inconnu: "Type de vendeur non renseigné",
};

const AVAILABILITY_LABELS = {
  disponible: "Disponible",
  "non confirmee": "Disponibilité non confirmée",
  non_confirme: "Disponibilité non confirmée",
  indisponible: "Indisponible",
  inconnu: "Disponibilité non confirmée",
};

const IMAGE_TYPE_LABELS = {
  original: "Photo du vendeur",
  fabricant: "Image fabricant",
  commercial: "Image commerciale",
  illustratif: "Image illustrative",
};

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  user: null,
  taxonomy: null,
  offers: new Map(),
  lastResponse: null,
  busy: false,
};

/* ------------------------------------------------------------------ */
/* Utilitaires                                                         */
/* ------------------------------------------------------------------ */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function label(map, key, fallback = "Non renseigné") {
  if (!key) return fallback;
  return map[key] || key.charAt(0).toUpperCase() + key.slice(1);
}

function money(offer) {
  if (offer.price_display && offer.price_display !== "Non renseigné") {
    return esc(offer.price_display);
  }
  if (typeof offer.price === "number") {
    const amount = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(offer.price);
    return `${amount}<span class="currency">${esc(offer.currency || "")}</span>`;
  }
  return "Prix non renseigné";
}

function hostOf(offer) {
  return offer.site_domain || offer.source_name || "source inconnue";
}

function toast(message, kind = "ok") {
  const stack = $("[data-toasts]");
  if (!stack) return;
  const node = document.createElement("div");
  node.className = `toast ${kind === "ok" ? "" : kind}`.trim();
  node.textContent = message;
  stack.appendChild(node);
  setTimeout(() => node.remove(), 5200);
}

function setBusy(value) {
  state.busy = value;
  const buttons = $$("form button[type=submit]");
  buttons.forEach((btn) => { btn.disabled = value; });
}

async function api(path, { method = "GET", body, form, auth = false } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && state.token) headers["Authorization"] = `Bearer ${state.token}`;

  let response;
  try {
    response = await fetch(`${API}${path}`, {
      method,
      headers,
      body: form ? form : body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    throw new Error("Connexion impossible. Connectez-vous à Internet pour effectuer vos recherches.");
  }

  let payload = null;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    try { payload = await response.json(); } catch { payload = null; }
  }

  if (!response.ok) {
    const detail = payload && payload.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || "").join(" · ")
      : detail || `Erreur ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return payload;
}

/* ------------------------------------------------------------------ */
/* Thème                                                               */
/* ------------------------------------------------------------------ */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
  const icon = $("[data-theme-icon]");
  if (icon) icon.textContent = theme === "dark" ? "☀️" : "🌙";
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
  $("[data-theme-toggle]")?.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

/* ------------------------------------------------------------------ */
/* Navigation                                                          */
/* ------------------------------------------------------------------ */

function navigate(path, { replace = false } = {}) {
  if (replace) history.replaceState({}, "", path);
  else history.pushState({}, "", path);
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-link]");
  if (!link) return;
  const href = link.getAttribute("href");
  if (!href || href.startsWith("http")) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey) return;
  event.preventDefault();
  navigate(href);
});

window.addEventListener("popstate", render);

/* ------------------------------------------------------------------ */
/* Compte utilisateur                                                  */
/* ------------------------------------------------------------------ */

async function loadUser() {
  if (!state.token) return null;
  try {
    state.user = await api("/auth/me", { auth: true });
  } catch (error) {
    if (error.status === 401) {
      state.token = "";
      state.user = null;
      localStorage.removeItem(TOKEN_KEY);
    }
  }
  updateAccountButton();
  return state.user;
}

function updateAccountButton() {
  const btn = $("[data-account-button]");
  if (!btn) return;
  if (state.user) {
    btn.textContent = state.user.display_name.split(" ")[0];
    btn.dataset.accountState = "in";
  } else {
    btn.textContent = "Se connecter";
    btn.dataset.accountState = "out";
  }
}

function openAuthModal(mode = "signin") {
  const modal = $("[data-auth-modal]");
  if (!modal) return;
  modal.hidden = false;
  setAuthMode(mode);
  setTimeout(() => $("[data-auth-form] input[name=email]")?.focus(), 40);
}

function closeAuthModal() {
  const modal = $("[data-auth-modal]");
  if (modal) modal.hidden = true;
}

function setAuthMode(mode) {
  const signup = mode === "signup";
  $("[data-auth-title]").textContent = signup ? "Créer un compte" : "Se connecter";
  $("[data-auth-submit]").textContent = signup ? "Créer mon compte" : "Se connecter";
  $$("[data-auth-mode]").forEach((tab) => {
    const active = tab.dataset.authMode === mode;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  const signupFields = $(".signup-only");
  if (signupFields) signupFields.hidden = !signup;
  const form = $("[data-auth-form]");
  if (form) form.dataset.mode = mode;
  const error = $("[data-auth-error]");
  if (error) error.hidden = true;
}

function initAuth() {
  $("[data-account-button]")?.addEventListener("click", () => {
    if (state.user) navigate("/compte");
    else openAuthModal("signin");
  });
  $$("[data-close-modal]").forEach((el) => el.addEventListener("click", closeAuthModal));
  $$("[data-auth-mode]").forEach((tab) =>
    tab.addEventListener("click", () => setAuthMode(tab.dataset.authMode))
  );
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAuthModal();
  });

  $("[data-auth-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const mode = form.dataset.mode || "signin";
    const errorBox = $("[data-auth-error]");
    errorBox.hidden = true;

    const payload = {
      email: String(data.get("email") || "").trim(),
      password: String(data.get("password") || ""),
    };
    if (mode === "signup") {
      payload.display_name = String(data.get("display_name") || "").trim() || payload.email.split("@")[0];
      payload.role = String(data.get("role") || "acheteur");
      payload.seller_type = String(data.get("seller_type") || "particulier");
    }

    setBusy(true);
    try {
      const result = await api(mode === "signup" ? "/auth/signup" : "/auth/signin", {
        method: "POST",
        body: payload,
      });
      state.token = result.token;
      state.user = result.user;
      localStorage.setItem(TOKEN_KEY, result.token);
      updateAccountButton();
      closeAuthModal();
      toast(`Bienvenue ${result.user.display_name} — ${result.provider === "firebase" ? "compte Firebase" : "compte JF MARKET"}.`);
      render();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
    } finally {
      setBusy(false);
    }
  });
}

function logout() {
  state.token = "";
  state.user = null;
  localStorage.removeItem(TOKEN_KEY);
  updateAccountButton();
  toast("Vous êtes déconnecté.");
  navigate("/");
}

/* ------------------------------------------------------------------ */
/* Rendu des offres                                                    */
/* ------------------------------------------------------------------ */

function rememberOffers(offers) {
  offers.forEach((offer) => state.offers.set(offer.id, offer));
  try {
    sessionStorage.setItem("jf:offers", JSON.stringify(offers.slice(0, 60)));
  } catch { /* stockage plein : sans conséquence */ }
}

function recallOffer(id) {
  if (state.offers.has(id)) return state.offers.get(id);
  try {
    const stored = JSON.parse(sessionStorage.getItem("jf:offers") || "[]");
    const found = stored.find((item) => item.id === id);
    if (found) {
      state.offers.set(found.id, found);
      return found;
    }
  } catch { /* ignore */ }
  return null;
}

function imageBadge(image) {
  if (!image) return "";
  const type = image.source_type || "illustratif";
  const text = IMAGE_TYPE_LABELS[type] || image.source_label || "Image";
  const extra = type === "illustratif" ? " — non contractuelle" : "";
  return `<span class="image-badge ${type === "illustratif" ? "illustrative" : ""}">${esc(text + extra)}</span>`;
}

function offerCard(offer) {
  const image = offer.image;
  const media = image && image.url
    ? `<img src="${esc(image.url)}" alt="${esc(image.alt || offer.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentElement.innerHTML='<div class=&quot;no-image&quot;><span>🖼️</span>Image indisponible</div>'" />${imageBadge(image)}`
    : `<div class="no-image"><span>🖼️</span>Photo non disponible pour cette annonce</div>`;

  const condition = offer.condition && offer.condition !== "inconnu"
    ? `<span class="tag ${esc(offer.condition)}">${esc(label(CONDITION_LABELS, offer.condition))}</span>`
    : "";
  const commune = offer.commune ? `<span class="tag">${esc(offer.commune)}</span>` : "";
  const seller = offer.seller_name
    ? `<span>${esc(offer.seller_name)}</span>`
    : `<span>Vendeur non renseigné</span>`;

  return `
    <article class="offer-card" data-offer-id="${esc(offer.id)}">
      <a class="offer-media" href="/annonce/${encodeURIComponent(offer.id)}" data-link aria-label="${esc(offer.title)}">${media}</a>
      <div class="offer-body">
        <h3 class="offer-title">
          <a href="/annonce/${encodeURIComponent(offer.id)}" data-link>${esc(offer.title)}</a>
        </h3>
        <p class="offer-price">${money(offer)}</p>
        <div class="offer-meta">${condition}${commune}<span class="tag">${esc(hostOf(offer))}</span></div>
        <p class="offer-seller">${seller}<span>${esc(label(SELLER_LABELS, offer.seller_type, ""))}</span></p>
        <div class="offer-actions">
          <a class="btn btn-dark btn-sm" href="${esc(offer.source_url)}" target="_blank" rel="noopener noreferrer">Voir l'annonce</a>
          ${offer.contact ? `<a class="btn btn-outline btn-sm" href="${contactHref(offer.contact)}" ${offer.contact.type === "page" ? 'target="_blank" rel="noopener noreferrer"' : ""}>Contacter</a>` : ""}
          <button class="btn btn-ghost btn-sm" type="button" data-favorite="${esc(offer.id)}" title="Ajouter aux favoris">☆ Favori</button>
        </div>
      </div>
    </article>`;
}

function contactHref(contact) {
  if (!contact) return "#";
  const value = String(contact.value || "");
  if (contact.type === "telephone") return `tel:${value.replace(/[^\d+]/g, "")}`;
  if (contact.type === "whatsapp") return `https://wa.me/${value.replace(/[^\d]/g, "")}`;
  if (contact.type === "email") return `mailto:${value}`;
  return value;
}

/* ------------------------------------------------------------------ */
/* Page d'accueil                                                      */
/* ------------------------------------------------------------------ */

const EXAMPLE_QUERIES = [
  "Je cherche un bon téléphone Samsung à 200 dollars",
  "Ordinateur Core i5 pas trop cher",
  "Télévision 43 pouces",
  "Voiture Toyota à Kinshasa",
  "Chaussure Nike originale",
];

function renderHome() {
  const tax = state.taxonomy || {};
  const categories = (tax.categories || []).map((cat) => `
    <button class="cat-card" type="button" data-category="${esc(cat.id)}">
      <span class="cat-icon" aria-hidden="true">${esc(cat.icon || "🛍️")}</span>
      <span>
        <strong>${esc(cat.label)}</strong>
        <small>${(cat.subcategories || []).length} sous-catégories</small>
      </span>
    </button>`).join("");

  const brands = (tax.popular_brands || []).map((brand) => `
    <button class="chip" type="button" data-brand="${esc(brand)}">${esc(brand)}</button>`).join("");

  const trending = (tax.trending || []).slice(0, 10).map((item) => {
    const query = typeof item === "string" ? item : item.query || item.label || "";
    const detail = typeof item === "string" ? "" : item.note || item.category || "";
    return `<button class="chip" type="button" data-query="${esc(query)}" title="${esc(detail)}">${esc(query)}</button>`;
  }).join("");

  const examples = EXAMPLE_QUERIES.map((query) =>
    `<button type="button" data-query="${esc(query)}">${esc(query)}</button>`).join("");

  return `
    <section class="hero">
      <h1>Recherchez un article, retrouvez les offres et découvrez les vendeurs.</h1>
      <p class="lead">
        Décrivez ce que vous cherchez comme vous le diriez à un ami : JF MARKET comprend le produit,
        la marque, le budget, l'état et la commune, puis interroge les sources commerciales réelles.
      </p>
      <form class="hero-search" data-search-form role="search">
        <div class="search-box">
          <label class="sr-only" for="q-home">Votre recherche</label>
          <input id="q-home" name="q" type="search" autocomplete="off"
                 placeholder="Ex. Je cherche un bon téléphone Samsung à 200 dollars" />
        </div>
        <button class="btn btn-primary" type="submit">Rechercher</button>
        <label class="btn btn-ghost" style="background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.25);color:#eaf2ff;cursor:pointer">
          📷 Recherche par image
          <input type="file" accept="image/*" data-image-input hidden />
        </label>
      </form>
      <div class="hero-badges">
        <span>Kinshasa en priorité</span>
        <span>Offres réelles, jamais simulées</span>
        <span>Images vérifiées</span>
        <span>Mode jour / nuit</span>
      </div>
      <div class="hero-examples">${examples}</div>
    </section>

    <section class="section" id="categories">
      <div class="section-head">
        <h2>Catégories de produits</h2>
        <span class="muted small">Toutes les familles commercialisées à Kinshasa</span>
      </div>
      <div class="grid grid-cats">${categories}</div>
    </section>

    <section class="section" id="marques">
      <div class="section-head">
        <h2>Marques populaires</h2>
        <span class="muted small">Cliquez pour lancer une recherche directe</span>
      </div>
      <div class="row">${brands}</div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Articles les plus recherchés en 2026</h2>
      </div>
      <div class="row">${trending}</div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Dernières publications des vendeurs</h2>
        <a href="/vendeur" data-link>Publier un article</a>
      </div>
      <div data-latest-listings>
        <div class="loading-block"><div class="spinner" aria-hidden="true"></div><p>Chargement des annonces…</p></div>
      </div>
    </section>`;
}

async function hydrateLatestListings() {
  const container = $("[data-latest-listings]");
  if (!container) return;
  try {
    const data = await api("/listings?limit=8");
    const listings = data.listings || [];
    if (!listings.length) {
      container.innerHTML = `
        <div class="empty-state">
          <span class="emoji">🏪</span>
          <p><strong>Aucune annonce publiée pour le moment.</strong></p>
          <p class="muted small">Les vendeurs JF MARKET peuvent publier gratuitement leurs articles : ils apparaîtront ici et dans les recherches pertinentes.</p>
          <a class="btn btn-primary btn-sm" href="/vendeur" data-link>Publier le premier article</a>
        </div>`;
      return;
    }
    container.innerHTML = `<div class="grid grid-offers">${listings.map(listingCard).join("")}</div>`;
  } catch (error) {
    container.innerHTML = `<p class="notice error">${esc(error.message)}</p>`;
  }
}

function listingCard(listing) {
  const image = (listing.images || [])[0];
  const media = image
    ? `<img src="${esc(image)}" alt="${esc(listing.title)}" loading="lazy" />`
    : `<div class="no-image"><span>🏪</span>Photo non fournie</div>`;
  return `
    <article class="offer-card">
      <a class="offer-media" href="/annonce/${encodeURIComponent(listing.id)}" data-link>${media}
        <span class="image-badge">Annonce JF MARKET</span>
      </a>
      <div class="offer-body">
        <h3 class="offer-title"><a href="/annonce/${encodeURIComponent(listing.id)}" data-link>${esc(listing.title)}</a></h3>
        <p class="offer-price">${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(listing.price)}<span class="currency">${esc(listing.currency)}</span></p>
        <div class="offer-meta">
          <span class="tag ${esc(listing.condition)}">${esc(label(CONDITION_LABELS, listing.condition))}</span>
          ${listing.commune ? `<span class="tag">${esc(listing.commune)}</span>` : ""}
          <span class="tag">${esc(listing.city || "Kinshasa")}</span>
        </div>
        <p class="offer-seller"><span>${esc(listing.seller_name)}</span><span>${esc(label(SELLER_LABELS, listing.seller_type, ""))}</span></p>
        <div class="offer-actions">
          <a class="btn btn-dark btn-sm" href="/annonce/${encodeURIComponent(listing.id)}" data-link>Voir la fiche</a>
        </div>
      </div>
    </article>`;
}

/* ------------------------------------------------------------------ */
/* Page de résultats                                                   */
/* ------------------------------------------------------------------ */

function searchParamsFromUrl() {
  const params = new URLSearchParams(location.search);
  return {
    query: (params.get("q") || "").trim(),
    category: params.get("cat") || "",
    brand: params.get("marque") || "",
    condition: params.get("etat") || "",
    seller_type: params.get("vendeur") || "",
    commune: params.get("commune") || "",
    price_min: params.get("min") || "",
    price_max: params.get("max") || "",
    sort: params.get("tri") || "pertinence",
    only_with_image: params.get("image") === "1",
  };
}

function renderSearchShell(params) {
  const tax = state.taxonomy || {};
  const categories = (tax.categories || []).map((cat) =>
    `<option value="${esc(cat.id)}" ${params.category === cat.id ? "selected" : ""}>${esc(cat.label)}</option>`
  ).join("");
  const brands = (tax.brands || []).map((brand) =>
    `<option value="${esc(brand.name)}" ${params.brand === brand.name ? "selected" : ""}>${esc(brand.name)}</option>`
  ).join("");
  const communes = (tax.communes || []).map((commune) =>
    `<option value="${esc(commune)}" ${params.commune === commune ? "selected" : ""}>${esc(commune)}</option>`
  ).join("");

  return `
    <div class="results-head">
      <div>
        <h1 data-results-title>${params.query ? `Résultats pour « ${esc(params.query)} »` : "Recherche"}</h1>
        <p class="muted small" data-results-subtitle>Recherche en cours sur les sources commerciales…</p>
      </div>
      <form class="row" data-search-form role="search" style="flex:1;min-width:240px">
        <label class="sr-only" for="q-results">Affiner la recherche</label>
        <input id="q-results" name="q" type="search" value="${esc(params.query)}"
               style="flex:1;min-width:160px;padding:.55rem .8rem;border:1px solid var(--line);border-radius:10px;background:var(--surface)" />
        <button class="btn btn-primary" type="submit">Rechercher</button>
      </form>
    </div>

    <div class="search-layout">
      <aside class="card filters" aria-label="Filtres de recherche">
        <h2>Filtres</h2>
        <form data-filter-form class="stack">
          <div class="filter-group">
            <h3>Prix (devise publiée)</h3>
            <div class="price-row">
              <label class="field"><span class="sr-only">Prix minimum</span>
                <input name="min" type="number" min="0" step="any" placeholder="Min" value="${esc(params.price_min)}" /></label>
              <label class="field"><span class="sr-only">Prix maximum</span>
                <input name="max" type="number" min="0" step="any" placeholder="Max" value="${esc(params.price_max)}" /></label>
            </div>
          </div>
          <div class="filter-group">
            <h3>Marque</h3>
            <label class="field"><span class="sr-only">Marque</span>
              <select name="marque"><option value="">Toutes les marques</option>${brands}</select></label>
          </div>
          <div class="filter-group">
            <h3>Catégorie</h3>
            <label class="field"><span class="sr-only">Catégorie</span>
              <select name="cat"><option value="">Toutes les catégories</option>${categories}</select></label>
          </div>
          <div class="filter-group">
            <h3>État</h3>
            <label class="field"><span class="sr-only">État du produit</span>
              <select name="etat">
                <option value="">Tous les états</option>
                <option value="neuf" ${params.condition === "neuf" ? "selected" : ""}>Neuf</option>
                <option value="occasion" ${params.condition === "occasion" ? "selected" : ""}>Occasion</option>
                <option value="reconditionne" ${params.condition === "reconditionne" ? "selected" : ""}>Reconditionné</option>
              </select></label>
          </div>
          <div class="filter-group">
            <h3>Type de vendeur</h3>
            <label class="field"><span class="sr-only">Type de vendeur</span>
              <select name="vendeur">
                <option value="">Tous les vendeurs</option>
                <option value="boutique" ${params.seller_type === "boutique" ? "selected" : ""}>Boutique commerciale</option>
                <option value="particulier" ${params.seller_type === "particulier" ? "selected" : ""}>Vendeur indépendant</option>
              </select></label>
          </div>
          <div class="filter-group">
            <h3>Commune (Kinshasa)</h3>
            <label class="field"><span class="sr-only">Commune</span>
              <select name="commune"><option value="">Toutes les communes</option>${communes}</select></label>
          </div>
          <div class="filter-group">
            <h3>Tri</h3>
            <label class="field"><span class="sr-only">Ordre de tri</span>
              <select name="tri">
                <option value="pertinence" ${params.sort === "pertinence" ? "selected" : ""}>Pertinence</option>
                <option value="prix_asc" ${params.sort === "prix_asc" ? "selected" : ""}>Prix croissant</option>
                <option value="prix_desc" ${params.sort === "prix_desc" ? "selected" : ""}>Prix décroissant</option>
                <option value="recent" ${params.sort === "recent" ? "selected" : ""}>Plus récentes</option>
              </select></label>
          </div>
          <label class="row small" style="gap:.45rem">
            <input type="checkbox" name="image" value="1" ${params.only_with_image ? "checked" : ""} />
            <span>Uniquement avec photo</span>
          </label>
          <div class="row">
            <button class="btn btn-primary btn-sm" type="submit">Appliquer</button>
            <button class="btn btn-ghost btn-sm" type="reset">Réinitialiser</button>
          </div>
        </form>
      </aside>

      <div>
        <div data-intent-panel></div>
        <div data-results>
          <div class="loading-block">
            <div class="spinner" aria-hidden="true"></div>
            <p>Analyse de votre demande et collecte des offres réelles…</p>
          </div>
        </div>
      </div>
    </div>`;
}

function filtersFromParams(params) {
  const filters = {
    price_min: params.price_min ? Number(params.price_min) : null,
    price_max: params.price_max ? Number(params.price_max) : null,
    brand: params.brand || null,
    category: params.category || null,
    condition: params.condition || null,
    seller_type: params.seller_type || null,
    commune: params.commune || null,
    only_with_image: Boolean(params.only_with_image),
    sort: params.sort || "pertinence",
  };
  return filters;
}

function intentPanel(response) {
  const intent = response.intent || {};
  const chips = [];
  if (intent.brand) chips.push(`Marque : ${intent.brand}`);
  if (intent.product_model) chips.push(`Modèle : ${intent.product_model}`);
  if (intent.product_reference) chips.push(`Référence : ${intent.product_reference}`);
  if (intent.category_label || intent.category) chips.push(`Catégorie : ${intent.category_label || intent.category}`);
  if (intent.price_max) chips.push(`Budget : ${intent.price_max} ${intent.currency || "USD"}`);
  if (intent.price_min) chips.push(`Minimum : ${intent.price_min} ${intent.currency || "USD"}`);
  if (intent.condition && intent.condition !== "inconnu") chips.push(`État : ${label(CONDITION_LABELS, intent.condition)}`);
  if (intent.commune) chips.push(`Commune : ${intent.commune}`);
  if (intent.city) chips.push(`Ville : ${intent.city}`);
  Object.entries(intent.corrections || {}).forEach(([from, to]) => chips.push(`« ${from} » → ${to}`));

  const stages = (response.stages || []).map((stage) => `
    <div class="stage-item ${stage.offers_found ? "" : "zero"}">
      <span class="dot" aria-hidden="true"></span>
      <span><strong>${esc(stage.label)}</strong> — ${stage.offers_found} offre(s)
        <span class="muted small">« ${esc(stage.query_used)} »</span>
        ${stage.note ? `<span class="muted small">· ${esc(stage.note)}</span>` : ""}
      </span>
    </div>`).join("");

  const sources = (response.sources || []).map((source) => `
    <span class="source-pill ${source.status === "ok" ? "ok" : source.status === "echec" ? "failed" : ""}"
          title="${esc(source.detail || source.label)}">${esc(source.label)} · ${source.offers ?? 0}</span>`).join("");

  return `
    <div class="intent-panel">
      <div class="between" style="margin-bottom:.4rem">
        <strong>Ce que JF MARKET a compris</strong>
        <span class="muted small">${response.took_ms || 0} ms${response.cached ? " · cache" : ""}</span>
      </div>
      <div class="intent-chips">${chips.length ? chips.map((c) => `<span>${esc(c)}</span>`).join("") : "<span>Demande générale : recherche élargie sur les sources commerciales</span>"}</div>
      <div class="stage-list">${stages}</div>
      ${sources ? `<div class="source-strip" style="margin-top:.6rem">${sources}</div>` : ""}
    </div>`;
}

async function runSearch(params) {
  const results = $("[data-results]");
  const panel = $("[data-intent-panel]");
  if (!results) return;

  if (!navigator.onLine) {
    results.innerHTML = `<div class="empty-state"><span class="emoji">📡</span>
      <p><strong>${OFFLINE_MESSAGE}</strong></p>
      <p class="muted small">JF MARKET interroge des sources commerciales en direct : sans connexion, aucun résultat ne peut être vérifié.</p></div>`;
    return;
  }

  try {
    const response = await api("/search", {
      method: "POST",
      body: { query: params.query, filters: filtersFromParams(params), limit: 24, fresh: false },
    });
    state.lastResponse = response;
    rememberOffers(response.offers || []);

    const title = $("[data-results-title]");
    const subtitle = $("[data-results-subtitle]");
    if (title) title.textContent = `Résultats pour « ${params.query} »`;
    if (subtitle) {
      subtitle.textContent = `${response.count} offre(s) pertinente(s) · ${(response.sources || []).filter((s) => s.status === "ok").length} source(s) consultée(s)`;
    }
    if (panel) panel.innerHTML = intentPanel(response);

    if (!response.network_ok) {
      const hint = response.message && response.message !== OFFLINE_MESSAGE
        ? response.message
        : "Les sources commerciales sont momentanément inaccessibles.";
      results.innerHTML = `<div class="empty-state"><span class="emoji">📡</span>
        <p><strong>${OFFLINE_MESSAGE}</strong></p>
        <p class="muted small">${esc(hint)}</p></div>`;
      return;
    }

    if (!response.offers || !response.offers.length) {
      results.innerHTML = `<div class="empty-state"><span class="emoji">🔍</span>
        <p><strong>Aucune offre fiable trouvée pour cette recherche.</strong></p>
        <p class="muted small">${esc(response.message || "JF MARKET n'invente pas de résultats : essayez un synonyme, une marque ou un budget plus large.")}</p>
        <div class="row" style="justify-content:center">
          <button class="btn btn-outline btn-sm" type="button" data-query="telephone samsung Kinshasa">Téléphones Samsung</button>
          <button class="btn btn-outline btn-sm" type="button" data-query="ordinateur portable core i5">Ordinateurs Core i5</button>
          <button class="btn btn-outline btn-sm" type="button" data-query="television 43 pouces">Téléviseurs 43 pouces</button>
        </div></div>`;
      return;
    }

    const notice = response.message ? `<p class="notice">${esc(response.message)}</p>` : "";
    results.innerHTML = `${notice}<div class="grid grid-offers">${response.offers.map(offerCard).join("")}</div>`;
  } catch (error) {
    results.innerHTML = `<div class="empty-state"><span class="emoji">⚠️</span>
      <p><strong>La recherche n'a pas pu aboutir.</strong></p>
      <p class="muted small">${esc(error.message)}</p>
      <button class="btn btn-outline btn-sm" type="button" data-retry="${esc(params.query)}">Réessayer</button></div>`;
  }
}

/* ------------------------------------------------------------------ */
/* Fiche d'une offre                                                   */
/* ------------------------------------------------------------------ */

async function renderOfferDetail(offerId) {
  let offer = recallOffer(offerId);
  let listing = null;

  if (!offer) {
    try {
      listing = await api(`/listings/${encodeURIComponent(offerId)}`);
    } catch (error) {
      return `<div class="empty-state"><span class="emoji">🔎</span>
        <p><strong>Cette offre n'est plus disponible dans la session.</strong></p>
        <p class="muted small">Relancez la recherche pour retrouver les annonces à jour.</p>
        <a class="btn btn-primary btn-sm" href="/" data-link>Retour à l'accueil</a></div>`;
    }
  }

  if (listing) return listingDetail(listing);

  const images = [offer.image, ...(offer.images || [])].filter((img) => img && img.url);
  const main = images[0];
  const gallery = main
    ? `<div class="detail-gallery">
         <div class="main-img"><img src="${esc(main.url)}" alt="${esc(main.alt || offer.title)}" referrerpolicy="no-referrer" /></div>
         <div class="thumbs">${images.map((img, index) => `<img src="${esc(img.url)}" alt="Photo ${index + 1}" data-thumb="${esc(img.url)}" loading="lazy" referrerpolicy="no-referrer" />`).join("")}</div>
       </div>`
    : `<div class="detail-gallery"><div class="main-img"><div class="no-image"><span>🖼️</span>Aucune image vérifiée pour cette annonce</div></div></div>`;

  const imageInfo = main
    ? `<p class="muted small">${esc(IMAGE_TYPE_LABELS[main.source_type] || "Image")}
       ${main.match_score ? ` · cohérence produit ${Math.round(main.match_score * 100)} %` : ""}
       ${(main.matched_signals || []).length ? ` · ${esc(main.matched_signals.join(", "))}` : ""}</p>`
    : "";

  const reasons = (offer.relevance_reasons || []).length
    ? `<div class="card"><h3>Pourquoi cette offre</h3><ul class="small">${offer.relevance_reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`
    : "";

  return `
    <p class="small"><a href="/" data-link>Accueil</a> › <a href="/recherche?q=${encodeURIComponent(state.lastResponse?.query || offer.title)}" data-link>Recherche</a> › ${esc(offer.title)}</p>
    <div class="detail-layout">
      <div>
        ${gallery}
        ${imageInfo}
        ${offer.description ? `<div class="card" style="margin-top:1rem"><h3>Description publiée</h3><p class="small">${esc(offer.description)}</p></div>` : ""}
        ${reasons}
      </div>
      <div class="detail-panel">
        <div class="card">
          <h1 class="page-title" style="font-size:1.3rem">${esc(offer.title)}</h1>
          <p class="price-lg">${money(offer)}</p>
          <div class="offer-meta" style="margin-bottom:.8rem">
            <span class="tag ${esc(offer.condition)}">${esc(label(CONDITION_LABELS, offer.condition))}</span>
            <span class="tag">${esc(label(AVAILABILITY_LABELS, offer.availability))}</span>
            ${offer.brand ? `<span class="tag">${esc(offer.brand)}</span>` : ""}
          </div>
          <table class="info-table">
            <tr><th>Marque</th><td>${esc(offer.brand || "Non renseigné")}</td></tr>
            <tr><th>Modèle</th><td>${esc(offer.product_model || "Non renseigné")}</td></tr>
            <tr><th>Vendeur</th><td>${esc(offer.seller_name || "Non renseigné")}</td></tr>
            <tr><th>Type de vendeur</th><td>${esc(label(SELLER_LABELS, offer.seller_type))}</td></tr>
            <tr><th>Localisation</th><td>${esc(offer.location || offer.city || "Non renseigné")}</td></tr>
            <tr><th>Commune</th><td>${esc(offer.commune || "Non renseigné")}</td></tr>
            <tr><th>Source</th><td>${esc(offer.source_name)} (${esc(hostOf(offer))})</td></tr>
            <tr><th>Publié le</th><td>${esc(offer.published_at || "Non renseigné")}</td></tr>
          </table>
          <div class="stack" style="margin-top:.9rem">
            <a class="btn btn-primary btn-block" href="${esc(offer.source_url)}" target="_blank" rel="noopener noreferrer">Consulter l'annonce originale</a>
            ${offer.contact ? `<a class="btn btn-outline btn-block" href="${contactHref(offer.contact)}" ${offer.contact.type === "page" ? 'target="_blank" rel="noopener noreferrer"' : ""}>Contacter le vendeur (${esc(offer.contact.type)})</a>` : `<p class="muted small">Aucun moyen de contact public vérifiable n'a été trouvé : JF MARKET n'en invente pas.</p>`}
            <button class="btn btn-ghost btn-block" type="button" data-favorite="${esc(offer.id)}">☆ Ajouter aux favoris</button>
          </div>
        </div>
        <div class="notice small">
          Les informations proviennent de la source indiquée. Vérifiez le prix, l'état et la disponibilité
          auprès du vendeur avant tout paiement.
        </div>
      </div>
    </div>`;
}

function listingDetail(listing) {
  const images = listing.images || [];
  return `
    <p class="small"><a href="/" data-link>Accueil</a> › <a href="/vendeur" data-link>Annonces vendeurs</a> › ${esc(listing.title)}</p>
    <div class="detail-layout">
      <div>
        <div class="detail-gallery">
          <div class="main-img">${images[0] ? `<img src="${esc(images[0])}" alt="${esc(listing.title)}" />` : `<div class="no-image"><span>🏪</span>Photo non fournie</div>`}</div>
          ${images.length > 1 ? `<div class="thumbs">${images.map((src, i) => `<img src="${esc(src)}" alt="Photo ${i + 1}" data-thumb="${esc(src)}" />`).join("")}</div>` : ""}
        </div>
        ${listing.description ? `<div class="card" style="margin-top:1rem"><h3>Description</h3><p class="small">${esc(listing.description)}</p></div>` : ""}
      </div>
      <div class="detail-panel">
        <div class="card">
          <h1 class="page-title" style="font-size:1.3rem">${esc(listing.title)}</h1>
          <p class="price-lg">${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(listing.price)}<span class="currency"> ${esc(listing.currency)}</span></p>
          <div class="offer-meta" style="margin-bottom:.8rem">
            <span class="tag ${esc(listing.condition)}">${esc(label(CONDITION_LABELS, listing.condition))}</span>
            <span class="tag">Annonce JF MARKET</span>
          </div>
          <table class="info-table">
            <tr><th>Vendeur</th><td>${esc(listing.seller_name)}</td></tr>
            <tr><th>Type de vendeur</th><td>${esc(label(SELLER_LABELS, listing.seller_type))}</td></tr>
            <tr><th>Commune</th><td>${esc(listing.commune || "Non renseigné")}</td></tr>
            <tr><th>Ville</th><td>${esc(listing.city || "Kinshasa")}</td></tr>
            <tr><th>Marque</th><td>${esc(listing.brand || "Non renseigné")}</td></tr>
            <tr><th>Modèle</th><td>${esc(listing.product_model || "Non renseigné")}</td></tr>
          </table>
          <div class="stack" style="margin-top:.9rem">
            ${listing.contact_whatsapp ? `<a class="btn btn-primary btn-block" href="https://wa.me/${esc(String(listing.contact_whatsapp).replace(/[^\d]/g, ""))}" target="_blank" rel="noopener noreferrer">WhatsApp du vendeur</a>` : ""}
            ${listing.contact_phone ? `<a class="btn btn-outline btn-block" href="tel:${esc(String(listing.contact_phone).replace(/[^\d+]/g, ""))}">Appeler ${esc(listing.contact_phone)}</a>` : ""}
            ${listing.contact_email ? `<a class="btn btn-outline btn-block" href="mailto:${esc(listing.contact_email)}">${esc(listing.contact_email)}</a>` : ""}
            ${!listing.contact_phone && !listing.contact_whatsapp && !listing.contact_email ? `<p class="muted small">Le vendeur n'a pas publié de moyen de contact.</p>` : ""}
          </div>
        </div>
      </div>
    </div>`;
}

/* ------------------------------------------------------------------ */
/* Favoris, compte, espace vendeur                                     */
/* ------------------------------------------------------------------ */

async function renderFavorites() {
  if (!state.user) {
    return `<div class="page-narrow">
      <h1 class="page-title">Mes favoris</h1>
      <div class="empty-state"><span class="emoji">🔐</span>
        <p><strong>Connectez-vous pour enregistrer vos favoris.</strong></p>
        <button class="btn btn-primary btn-sm" type="button" data-open-auth="signin">Se connecter</button>
      </div></div>`;
  }
  const container = document.createElement("div");
  container.innerHTML = `<div class="page-narrow"><h1 class="page-title">Mes favoris</h1>
    <div data-favorites-body><div class="loading-block"><div class="spinner"></div><p>Chargement…</p></div></div></div>`;
  const body = $("[data-favorites-body]", container);
  try {
    const data = await api("/favorites", { auth: true });
    const favorites = data.favorites || [];
    body.innerHTML = favorites.length
      ? `<div class="grid grid-offers">${favorites.map((fav) => offerCard(fav.offer)).join("")}</div>`
      : `<div class="empty-state"><span class="emoji">☆</span>
          <p><strong>Aucun favori pour l'instant.</strong></p>
          <p class="muted small">Cliquez sur « Favori » depuis une offre pour la retrouver ici.</p>
          <a class="btn btn-primary btn-sm" href="/" data-link>Rechercher un article</a></div>`;
  } catch (error) {
    body.innerHTML = `<p class="notice error">${esc(error.message)}</p>`;
  }
  return container.innerHTML;
}

async function renderAccount() {
  if (!state.user) {
    return `<div class="page-narrow">
      <h1 class="page-title">Mon compte</h1>
      <div class="empty-state"><span class="emoji">🔐</span>
        <p><strong>Connectez-vous ou créez un compte.</strong></p>
        <p class="muted small">Acheteur : favoris, historique et contacts. Vendeur : publication d'annonces.</p>
        <div class="row" style="justify-content:center">
          <button class="btn btn-primary btn-sm" type="button" data-open-auth="signin">Se connecter</button>
          <button class="btn btn-outline btn-sm" type="button" data-open-auth="signup">Créer un compte</button>
        </div>
      </div></div>`;
  }

  const container = document.createElement("div");
  container.innerHTML = `<div class="page-narrow">
    <h1 class="page-title">Bonjour ${esc(state.user.display_name)}</h1>
    <p class="muted small">${esc(state.user.email)} · profil ${esc(state.user.role === "vendeur" ? "vendeur" : "acheteur")}</p>
    <div class="account-grid" style="margin:1rem 0">
      <div class="card stat"><span class="muted small">Favoris</span><strong data-stat-favorites>—</strong></div>
      <div class="card stat"><span class="muted small">Recherches récentes</span><strong data-stat-history>—</strong></div>
      <div class="card stat"><span class="muted small">Mes annonces</span><strong data-stat-listings>—</strong></div>
    </div>
    <div class="card" style="margin-bottom:1rem">
      <div class="between"><h2 style="font-size:1.05rem;margin:0">Historique de recherche</h2>
      <button class="btn btn-ghost btn-sm" type="button" data-logout>Se déconnecter</button></div>
      <div data-history-body><div class="loading-block"><div class="spinner"></div></div></div>
    </div>
    <div class="card">
      <h2 style="font-size:1.05rem">Espace vendeur</h2>
      <p class="muted small">Publiez vos articles : ils apparaissent sur l'accueil et dans les recherches JF MARKET.</p>
      <a class="btn btn-primary btn-sm" href="/vendeur" data-link>Gérer mes annonces</a>
    </div>
  </div>`;

  const [favorites, history, listings] = await Promise.allSettled([
    api("/favorites", { auth: true }),
    api("/history", { auth: true }),
    api("/listings/mine", { auth: true }),
  ]);

  const setStat = (selector, value) => {
    const node = $(selector, container);
    if (node) node.textContent = value;
  };
  setStat("[data-stat-favorites]", favorites.status === "fulfilled" ? (favorites.value.favorites || []).length : "—");
  setStat("[data-stat-history]", history.status === "fulfilled" ? (history.value.history || []).length : "—");
  setStat("[data-stat-listings]", listings.status === "fulfilled" ? (listings.value.listings || []).length : "—");

  const historyBody = $("[data-history-body]", container);
  const entries = history.status === "fulfilled" ? history.value.history || [] : [];
  historyBody.innerHTML = entries.length
    ? `<ul class="small" style="padding-left:1rem">${entries.slice(0, 12).map((entry) => `
        <li><a href="/recherche?q=${encodeURIComponent(entry.query)}" data-link>${esc(entry.query)}</a>
        <span class="muted">— ${entry.results} résultat(s)</span></li>`).join("")}</ul>`
    : `<p class="muted small">Aucune recherche enregistrée pour l'instant.</p>`;

  $("[data-logout]", container)?.addEventListener("click", logout);
  return container.innerHTML;
}

function renderSeller() {
  const tax = state.taxonomy || {};
  const categories = (tax.categories || []).map((cat) =>
    `<option value="${esc(cat.id)}">${esc(cat.label)}</option>`).join("");
  const brands = (tax.brands || []).map((brand) =>
    `<option value="${esc(brand.name)}">${esc(brand.name)}</option>`).join("");
  const communes = (tax.communes || []).map((commune) =>
    `<option value="${esc(commune)}">${esc(commune)}</option>`).join("");

  const connected = Boolean(state.user);
  return `
    <div class="page-narrow">
      <h1 class="page-title">Espace vendeur</h1>
      <p class="muted">Publiez un article avec ses photos, son prix réel et votre commune. Les annonces sont visibles dans les recherches.</p>

      ${connected ? "" : `<div class="notice" style="margin:1rem 0">
        Connectez-vous avec un compte vendeur pour publier. <button class="btn-link" type="button" data-open-auth="signup">Créer un compte vendeur</button>
      </div>`}

      <form class="card stack" data-listing-form style="margin-top:1rem">
        <h2 style="font-size:1.1rem;margin:0">Nouvelle annonce</h2>
        <label class="field"><span>Titre de l'article *</span>
          <input name="title" required minlength="3" maxlength="160" placeholder="Ex. Samsung Galaxy A15 128 Go" /></label>
        <label class="field"><span>Description</span>
          <textarea name="description" maxlength="4000" placeholder="État, accessoires inclus, garantie, détails utiles…"></textarea></label>
        <div class="row" style="gap:.8rem">
          <label class="field" style="flex:1;min-width:120px"><span>Prix *</span>
            <input name="price" type="number" min="0" step="any" required placeholder="0" /></label>
          <label class="field" style="width:110px"><span>Devise</span>
            <select name="currency"><option value="USD">USD</option><option value="CDF">CDF</option></select></label>
          <label class="field" style="flex:1;min-width:130px"><span>État</span>
            <select name="condition">
              <option value="neuf">Neuf</option>
              <option value="occasion">Occasion</option>
              <option value="reconditionne">Reconditionné</option>
              <option value="inconnu">Non précisé</option>
            </select></label>
        </div>
        <div class="row" style="gap:.8rem">
          <label class="field" style="flex:1;min-width:150px"><span>Catégorie</span>
            <select name="category"><option value="">—</option>${categories}</select></label>
          <label class="field" style="flex:1;min-width:130px"><span>Marque</span>
            <select name="brand"><option value="">—</option>${brands}</select></label>
        </div>
        <div class="row" style="gap:.8rem">
          <label class="field" style="flex:1;min-width:130px"><span>Modèle</span>
            <input name="product_model" maxlength="80" placeholder="Ex. Galaxy A15" /></label>
          <label class="field" style="flex:1;min-width:130px"><span>Commune</span>
            <select name="commune"><option value="">—</option>${communes}</select></label>
        </div>
        <div class="row" style="gap:.8rem">
          <label class="field" style="flex:1;min-width:130px"><span>Téléphone</span>
            <input name="contact_phone" maxlength="30" placeholder="+243…" /></label>
          <label class="field" style="flex:1;min-width:130px"><span>WhatsApp</span>
            <input name="contact_whatsapp" maxlength="30" placeholder="+243…" /></label>
        </div>
        <label class="field"><span>E-mail de contact</span>
          <input name="contact_email" type="email" maxlength="200" placeholder="vente@exemple.cd" /></label>

        <div class="upload-zone">
          <label style="cursor:pointer">
            📷 Ajouter des photos (JPG, PNG, WebP — 4 max)
            <input type="file" accept="image/jpeg,image/png,image/webp" multiple data-listing-images hidden />
          </label>
          <div class="preview-row" data-image-preview></div>
        </div>

        <p class="form-error" data-listing-error hidden></p>
        <button class="btn btn-primary" type="submit">Publier l'annonce</button>
      </form>

      <section style="margin-top:2rem">
        <div class="between"><h2 style="font-size:1.15rem">Mes annonces</h2>
          <button class="btn btn-ghost btn-sm" type="button" data-refresh-mine>Rafraîchir</button></div>
        <div data-my-listings style="margin-top:.7rem"><p class="muted small">${connected ? "Chargement…" : "Connectez-vous pour voir vos annonces."}</p></div>
      </section>
    </div>`;
}

let uploadedImages = [];

function initSellerPage() {
  uploadedImages = [];
  const form = $("[data-listing-form]");
  const fileInput = $("[data-listing-images]");

  fileInput?.addEventListener("change", async () => {
    const files = Array.from(fileInput.files || []).slice(0, 4);
    if (!state.user) {
      toast("Connectez-vous pour téléverser des photos.", "info");
      return;
    }
    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);
      try {
        const result = await api("/uploads/image", { method: "POST", form: formData, auth: true });
        uploadedImages.push(result.url);
        renderPreviews();
      } catch (error) {
        toast(error.message, "error");
      }
    }
    fileInput.value = "";
  });

  function renderPreviews() {
    const box = $("[data-image-preview]");
    if (!box) return;
    box.innerHTML = uploadedImages.map((url, index) => `
      <div class="thumb"><img src="${esc(url)}" alt="Photo ${index + 1}" />
        <button type="button" data-remove-image="${index}" aria-label="Retirer">✕</button></div>`).join("");
    $$("[data-remove-image]", box).forEach((btn) => btn.addEventListener("click", () => {
      uploadedImages.splice(Number(btn.dataset.removeImage), 1);
      renderPreviews();
    }));
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = $("[data-listing-error]");
    errorBox.hidden = true;
    if (!state.user) {
      errorBox.textContent = "Connectez-vous avec un compte vendeur pour publier.";
      errorBox.hidden = false;
      return;
    }
    const data = new FormData(form);
    const payload = {
      title: String(data.get("title") || "").trim(),
      description: String(data.get("description") || "").trim(),
      price: Number(data.get("price") || 0),
      currency: String(data.get("currency") || "USD"),
      condition: String(data.get("condition") || "inconnu"),
      category: data.get("category") || null,
      brand: data.get("brand") || null,
      product_model: String(data.get("product_model") || "").trim() || null,
      commune: data.get("commune") || null,
      city: "Kinshasa",
      images: uploadedImages.slice(0, 6),
      contact_phone: String(data.get("contact_phone") || "").trim() || null,
      contact_whatsapp: String(data.get("contact_whatsapp") || "").trim() || null,
      contact_email: String(data.get("contact_email") || "").trim() || null,
    };
    setBusy(true);
    try {
      const created = await api("/listings", { method: "POST", body: payload, auth: true });
      toast("Annonce publiée. Elle est maintenant visible dans JF MARKET.");
      uploadedImages = [];
      form.reset();
      renderPreviews();
      navigate(`/annonce/${encodeURIComponent(created.id)}`);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
    } finally {
      setBusy(false);
    }
  });

  loadMyListings();
  $("[data-refresh-mine]")?.addEventListener("click", loadMyListings);
}

async function loadMyListings() {
  const box = $("[data-my-listings]");
  if (!box || !state.user) return;
  try {
    const data = await api("/listings/mine", { auth: true });
    const listings = data.listings || [];
    box.innerHTML = listings.length
      ? `<div class="stack">${listings.map((listing) => `
          <div class="listing-row">
            ${(listing.images || [])[0] ? `<img src="${esc(listing.images[0])}" alt="" />` : `<div class="ph">🏪</div>`}
            <div class="grow">
              <h4>${esc(listing.title)}</h4>
              <p class="muted small" style="margin:0">${new Intl.NumberFormat("fr-FR").format(listing.price)} ${esc(listing.currency)}
                · ${esc(label(CONDITION_LABELS, listing.condition))} · ${esc(listing.commune || "commune non précisée")}</p>
            </div>
            <a class="btn btn-ghost btn-sm" href="/annonce/${encodeURIComponent(listing.id)}" data-link>Voir</a>
            <button class="btn btn-ghost btn-sm" type="button" data-delete-listing="${esc(listing.id)}">Supprimer</button>
          </div>`).join("")}</div>`
      : `<p class="muted small">Aucune annonce publiée pour l'instant.</p>`;

    $$("[data-delete-listing]", box).forEach((btn) => btn.addEventListener("click", async () => {
      if (!confirm("Supprimer définitivement cette annonce ?")) return;
      try {
        await api(`/listings/${encodeURIComponent(btn.dataset.deleteListing)}`, { method: "DELETE", auth: true });
        toast("Annonce supprimée.");
        loadMyListings();
      } catch (error) {
        toast(error.message, "error");
      }
    }));
  } catch (error) {
    box.innerHTML = `<p class="notice error">${esc(error.message)}</p>`;
  }
}

function renderAbout() {
  const sources = (state.lastResponse?.sources || []).map((source) =>
    `<li><strong>${esc(source.label)}</strong> — ${esc(source.status)}${source.detail ? ` · ${esc(source.detail)}` : ""}</li>`).join("");
  return `
    <div class="page-narrow">
      <h1 class="page-title">À propos de JF MARKET</h1>
      <p>JF MARKET est un moteur de recherche commercial pensé pour Kinshasa : il comprend une demande
      formulée naturellement, interroge des sources publiques identifiées, associe une image cohérente
      à chaque offre et n'invente jamais une information vendeur.</p>
      <div class="card" style="margin:1rem 0">
        <h2 style="font-size:1.05rem">Comment la recherche fonctionne</h2>
        <ol class="small">
          <li>Analyse de la demande : produit, marque, modèle, budget, état, commune.</li>
          <li>Recherche progressive : requête exacte, synonymes, variantes, marque + référence.</li>
          <li>Collecte sur les sources commerciales, avec délais et protection contre les doublons.</li>
          <li>Sélection d'images indépendante, puis vérification de cohérence avec le produit.</li>
          <li>Classement par pertinence, filtres et affichage des fiches complètes.</li>
        </ol>
      </div>
      <div class="card" style="margin:1rem 0">
        <h2 style="font-size:1.05rem">Sources consultées</h2>
        <ul class="small">${sources || "<li>Les sources disponibles sont listées par <a href=\"/api/sources\" target=\"_blank\" rel=\"noopener\">/api/sources</a>.</li>"}</ul>
      </div>
      <div class="notice small">
        Les prix, contacts et disponibilités proviennent des annonces d'origine. Une information absente
        est affichée « Non renseigné ». Vérifiez toujours avant tout paiement.
      </div>
    </div>`;
}

/* ------------------------------------------------------------------ */
/* Actions globales                                                    */
/* ------------------------------------------------------------------ */

async function addFavorite(offerId) {
  if (!state.user) {
    openAuthModal("signin");
    toast("Connectez-vous pour enregistrer vos favoris.", "info");
    return;
  }
  const offer = recallOffer(offerId);
  if (!offer) {
    toast("Offre introuvable dans cette session.", "error");
    return;
  }
  try {
    await api("/favorites", { method: "POST", body: { offer, note: null }, auth: true });
    toast("Ajouté à vos favoris.");
  } catch (error) {
    toast(error.message, "error");
  }
}

function openImageSearch(file) {
  if (!file) return;
  const hint = window.prompt(
    "Précisez le produit recherché (marque et modèle si possible).\nLaissez vide pour analyser seulement l'image :",
    ""
  );
  if (hint === null) return;

  const view = $("#view");
  view.innerHTML = `<div class="loading-block"><div class="spinner"></div>
    <p>Analyse de votre photo et recherche des offres correspondantes…</p></div>`;

  const form = new FormData();
  form.append("file", file);
  if (hint.trim()) form.append("hint", hint.trim());
  form.append("limit", "12");

  api("/search/image", { method: "POST", form })
    .then((result) => {
      rememberOffers(result.offers || []);
      if (result.intent) {
        state.lastResponse = { query: result.query_guess || "recherche par image", intent: result.intent, sources: [], stages: [] };
      }
      view.innerHTML = `
        <div class="results-head"><div>
          <h1>Recherche par image</h1>
          <p class="muted small">${esc(result.method)}${result.query_guess ? ` · mot-clé utilisé : « ${esc(result.query_guess)} »` : ""}</p>
        </div></div>
        ${result.message ? `<p class="notice">${esc(result.message)}</p>` : ""}
        ${(result.offers || []).length
          ? `<div class="grid grid-offers">${result.offers.map(offerCard).join("")}</div>`
          : `<div class="empty-state"><span class="emoji">🖼️</span><p><strong>Aucune correspondance visuelle exploitable.</strong></p>
             <p class="muted small">Ajoutez un mot-clé pour que JF MARKET recherche les offres réelles.</p></div>`}`;
    })
    .catch((error) => {
      view.innerHTML = `<div class="empty-state"><span class="emoji">⚠️</span>
        <p><strong>Recherche par image impossible.</strong></p>
        <p class="muted small">${esc(error.message)}</p>
        <a class="btn btn-primary btn-sm" href="/" data-link>Retour à l'accueil</a></div>`;
    });
}

/* ------------------------------------------------------------------ */
/* Routeur et rendu                                                    */
/* ------------------------------------------------------------------ */

async function render() {
  const view = $("#view");
  if (!view) return;
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const mobileNav = $("[data-mobile-nav]");
  if (mobileNav) mobileNav.hidden = true;

  try {
    if (path === "/") {
      view.innerHTML = renderHome();
      hydrateLatestListings();
    } else if (path === "/recherche") {
      const params = searchParamsFromUrl();
      if (!params.query) {
        view.innerHTML = renderHome();
        hydrateLatestListings();
        return;
      }
      view.innerHTML = renderSearchShell(params);
      await runSearch(params);
    } else if (path.startsWith("/annonce/")) {
      const id = decodeURIComponent(path.split("/annonce/")[1] || "");
      view.innerHTML = await renderOfferDetail(id);
    } else if (path === "/favoris") {
      view.innerHTML = await renderFavorites();
    } else if (path === "/compte") {
      view.innerHTML = await renderAccount();
    } else if (path === "/vendeur") {
      view.innerHTML = renderSeller();
      initSellerPage();
    } else if (path === "/a-propos") {
      view.innerHTML = renderAbout();
    } else {
      view.innerHTML = `<div class="empty-state"><span class="emoji">🧭</span>
        <p><strong>Page introuvable.</strong></p>
        <a class="btn btn-primary btn-sm" href="/" data-link>Retour à l'accueil</a></div>`;
    }
  } catch (error) {
    view.innerHTML = `<div class="empty-state"><span class="emoji">⚠️</span>
      <p><strong>Une erreur est survenue.</strong></p>
      <p class="muted small">${esc(error.message)}</p>
      <button class="btn btn-outline btn-sm" type="button" onclick="location.reload()">Recharger</button></div>`;
  }
}

function buildSearchUrl(query, extra = {}) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, value);
  });
  return `/recherche?${params.toString()}`;
}

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-search-form]");
  if (form) {
    event.preventDefault();
    const value = String(new FormData(form).get("q") || "").trim();
    if (value.length < 2) {
      toast("Saisissez au moins deux caractères.", "info");
      return;
    }
    navigate(buildSearchUrl(value));
    return;
  }
  const filterForm = event.target.closest("[data-filter-form]");
  if (filterForm) {
    event.preventDefault();
    const data = new FormData(filterForm);
    const query = $("[data-results-title]")?.textContent.match(/« (.+) »/)?.[1] || "";
    const extra = {
      cat: data.get("cat") || "",
      marque: data.get("marque") || "",
      etat: data.get("etat") || "",
      vendeur: data.get("vendeur") || "",
      commune: data.get("commune") || "",
      min: data.get("min") || "",
      max: data.get("max") || "",
      tri: data.get("tri") || "pertinence",
      image: data.get("image") ? "1" : "",
    };
    navigate(buildSearchUrl(query, extra));
  }
});

document.addEventListener("click", (event) => {
  const queryBtn = event.target.closest("[data-query]");
  if (queryBtn) {
    navigate(buildSearchUrl(queryBtn.dataset.query));
    return;
  }
  const categoryBtn = event.target.closest("[data-category]");
  if (categoryBtn) {
    const cat = state.taxonomy?.categories?.find((item) => item.id === categoryBtn.dataset.category);
    navigate(buildSearchUrl(cat ? cat.label : categoryBtn.dataset.category, { cat: categoryBtn.dataset.category }));
    return;
  }
  const brandBtn = event.target.closest("[data-brand]");
  if (brandBtn) {
    navigate(buildSearchUrl(brandBtn.dataset.brand, { marque: brandBtn.dataset.brand }));
    return;
  }
  const favBtn = event.target.closest("[data-favorite]");
  if (favBtn) {
    addFavorite(favBtn.dataset.favorite);
    return;
  }
  const authBtn = event.target.closest("[data-open-auth]");
  if (authBtn) {
    openAuthModal(authBtn.dataset.openAuth);
    return;
  }
  const retryBtn = event.target.closest("[data-retry]");
  if (retryBtn) {
    navigate(buildSearchUrl(retryBtn.dataset.retry));
    return;
  }
  const thumb = event.target.closest("[data-thumb]");
  if (thumb) {
    const main = thumb.closest(".detail-gallery")?.querySelector(".main-img img");
    if (main) main.src = thumb.dataset.thumb;
  }
});

function initHeader() {
  $("[data-menu-toggle]")?.addEventListener("click", () => {
    const nav = $("[data-mobile-nav]");
    const open = nav.hidden;
    nav.hidden = !open;
    $("[data-menu-toggle]").setAttribute("aria-expanded", String(open));
  });
  const yearEl = $("[data-year]");
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());

  document.addEventListener("change", (event) => {
    const input = event.target.closest("[data-image-input]");
    if (input && input.files && input.files[0]) openImageSearch(input.files[0]);
  });

  const updateOnline = () => {
    const banner = $("[data-offline]");
    if (banner) banner.hidden = navigator.onLine;
  };
  window.addEventListener("online", updateOnline);
  window.addEventListener("offline", updateOnline);
  updateOnline();
}

async function boot() {
  initTheme();
  initHeader();
  initAuth();
  try {
    state.taxonomy = await api("/taxonomy");
  } catch (error) {
    state.taxonomy = { categories: [], brands: [], communes: [], popular_brands: [], trending: [] };
    toast("Catalogue indisponible : certaines suggestions sont limitées.", "info");
  }
  await loadUser();
  await render();
}

boot();
