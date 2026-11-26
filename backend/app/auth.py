"""Authentification des comptes JF MARKET.

Deux modes :
* Firebase Authentication (REST Identity Toolkit) si `FIREBASE_API_KEY` est
  configurée — les comptes sont alors réellement gérés par Firebase ;
* mode local sinon : mots de passe hachés (PBKDF2-SHA256) et jetons signés
  HMAC, afin que l'application reste utilisable sans configuration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

import httpx

from .config import get_settings
from .models import AuthUser, SignInRequest, SignUpRequest, utcnow
from .store.repository import Repository, new_id

IDENTITY_BASE = "https://identitytoolkit.googleapis.com/v1/accounts"
PBKDF2_ROUNDS = 200_000


class AuthError(Exception):
    """Erreur d'authentification destinée à l'API."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(slots=True)
class AuthContext:
    """Utilisateur authentifié + jeton à réutiliser pour Firestore."""

    user: AuthUser
    id_token: str | None
    provider: str


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Hache un mot de passe avec un sel aléatoire (mode local)."""
    salt = salt or hashlib.sha256(new_id().encode()).digest()[:16]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return _b64encode(digest), _b64encode(salt)


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    try:
        salt = _b64decode(stored_salt)
    except Exception:  # noqa: BLE001
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return hmac.compare_digest(_b64encode(digest), stored_hash)


class AuthService:
    """Gère l'inscription, la connexion et la vérification des jetons."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    def provider(self) -> str:
        return "firebase" if self.settings.firebase_enabled else "local"

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=12.0)
        return self._client

    # --- Jetons locaux ---------------------------------------------------
    def _issue_token(self, uid: str) -> str:
        payload = {"uid": uid, "exp": int(time.time()) + self.settings.auth_token_ttl_hours * 3600}
        body = _b64encode(json.dumps(payload).encode())
        signature = hmac.new(
            self.settings.auth_secret.encode(), body.encode(), hashlib.sha256
        ).digest()
        return f"{body}.{_b64encode(signature)}"

    def _read_token(self, token: str) -> str:
        try:
            body, signature = token.split(".", 1)
        except ValueError as exc:
            raise AuthError("Jeton invalide") from exc
        expected = hmac.new(
            self.settings.auth_secret.encode(), body.encode(), hashlib.sha256
        ).digest()
        try:
            provided = _b64decode(signature)
        except Exception as exc:  # noqa: BLE001
            raise AuthError("Jeton invalide") from exc
        if not hmac.compare_digest(expected, provided):
            raise AuthError("Jeton invalide")
        try:
            payload = json.loads(_b64decode(body))
        except Exception as exc:  # noqa: BLE001
            raise AuthError("Jeton invalide") from exc
        if int(payload.get("exp", 0)) < int(time.time()):
            raise AuthError("Session expirée, reconnectez-vous")
        return str(payload.get("uid", ""))

    # --- Firebase REST ---------------------------------------------------
    async def _firebase(self, path: str, payload: dict) -> dict:
        response = await self._http().post(
            f"{IDENTITY_BASE}:{path}",
            params={"key": self.settings.firebase_api_key},
            json=payload,
        )
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("error", {}).get("message", "Erreur Firebase")
            raise AuthError(_firebase_message(message), 400)
        return data

    async def _firebase_profile(self, uid: str, email: str, id_token: str, defaults: dict) -> dict:
        profile = await self.repository.get_user(uid, id_token)
        if profile:
            return profile
        profile = {
            "uid": uid,
            "email": email,
            "role": defaults.get("role", "acheteur"),
            "display_name": defaults.get("display_name") or email.split("@")[0],
            "phone": defaults.get("phone"),
            "provider": "firebase",
            "created_at": utcnow(),
        }
        await self.repository.save_user(profile, id_token)
        return profile

    # --- API publique ----------------------------------------------------
    async def sign_up(self, request: SignUpRequest) -> tuple[str, AuthUser, str]:
        """Crée un compte et renvoie (jeton, utilisateur, fournisseur)."""
        if self.settings.firebase_enabled:
            data = await self._firebase(
                "signUp",
                {
                    "email": request.email,
                    "password": request.password,
                    "returnSecureToken": True,
                },
            )
            id_token = data.get("idToken", "")
            uid = data.get("localId", "")
            profile = await self._firebase_profile(
                uid,
                request.email,
                id_token,
                {
                    "role": request.role,
                    "display_name": request.display_name,
                    "phone": request.phone,
                    "seller_type": request.seller_type,
                },
            )
            return id_token, await self.repository.to_auth_user(profile), "firebase"

        existing = await self.repository.get_user_by_email(request.email)
        if existing:
            raise AuthError("Un compte existe déjà avec cette adresse e-mail", 409)
        uid = new_id("u_")
        password_hash, salt = hash_password(request.password)
        profile = {
            "uid": uid,
            "email": request.email,
            "role": request.role,
            "display_name": request.display_name,
            "phone": request.phone,
            "seller_type": request.seller_type,
            "provider": "local",
            "password_hash": password_hash,
            "salt": salt,
            "created_at": utcnow(),
        }
        await self.repository.save_user(profile)
        return self._issue_token(uid), await self.repository.to_auth_user(profile), "local"

    async def sign_in(self, request: SignInRequest) -> tuple[str, AuthUser, str]:
        """Connecte un utilisateur existant."""
        email = request.email.strip().lower()
        if self.settings.firebase_enabled:
            data = await self._firebase(
                "signInWithPassword",
                {"email": email, "password": request.password, "returnSecureToken": True},
            )
            id_token = data.get("idToken", "")
            uid = data.get("localId", "")
            profile = await self._firebase_profile(uid, email, id_token, {})
            return id_token, await self.repository.to_auth_user(profile), "firebase"

        profile = await self.repository.get_user_by_email(email)
        if not profile or not verify_password(
            request.password, profile.get("password_hash", ""), profile.get("salt", "")
        ):
            raise AuthError("E-mail ou mot de passe incorrect")
        return self._issue_token(profile["uid"]), await self.repository.to_auth_user(profile), "local"

    async def authenticate(self, token: str) -> AuthContext:
        """Vérifie un jeton et renvoie l'utilisateur associé."""
        if self.settings.firebase_enabled:
            data = await self._firebase("lookup", {"idToken": token})
            users = data.get("users") or []
            if not users:
                raise AuthError("Session expirée, reconnectez-vous")
            uid = users[0].get("localId", "")
            email = users[0].get("email", "")
            profile = await self._firebase_profile(uid, email, token, {})
            return AuthContext(
                user=await self.repository.to_auth_user(profile),
                id_token=token,
                provider="firebase",
            )

        uid = self._read_token(token)
        profile = await self.repository.get_user(uid)
        if not profile:
            raise AuthError("Compte introuvable")
        return AuthContext(
            user=await self.repository.to_auth_user(profile), id_token=None, provider="local"
        )


def _firebase_message(code: str) -> str:
    mapping = {
        "EMAIL_EXISTS": "Un compte existe déjà avec cette adresse e-mail",
        "EMAIL_NOT_FOUND": "E-mail ou mot de passe incorrect",
        "INVALID_PASSWORD": "E-mail ou mot de passe incorrect",
        "INVALID_LOGIN_CREDENTIALS": "E-mail ou mot de passe incorrect",
        "WEAK_PASSWORD": "Mot de passe trop faible (6 caractères minimum)",
        "INVALID_EMAIL": "Adresse e-mail invalide",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Trop de tentatives, réessayez plus tard",
    }
    return mapping.get(code, "Authentification impossible pour le moment")
