"""Client Google and expert LinkedIn sign-in. Provider credentials stay on the server."""
import base64
import hashlib
import json
import os
import secrets
import time
from functools import lru_cache
from typing import Literal
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import jwt
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token as google_id_token

from . import db
from .config import APP_URL, CLOUD, DATABASE_URL, ROOT, now_iso

Provider = Literal["google", "linkedin"]
PROVIDER_LABELS = {"google": "Google", "linkedin": "LinkedIn"}
router = APIRouter(prefix="/auth", tags=["auth"])
CREDS = ROOT / "credentials.json"
SESSION_TTL_S = 7 * 24 * 3600
STATE_TTL_S = 10 * 60
DEFAULT_ORIGIN = APP_URL or "http://localhost:5173"
ALLOWED_ORIGINS = {APP_URL} if CLOUD else {DEFAULT_ORIGIN, "http://127.0.0.1:5173"}
API_BASE = f"{APP_URL}/api" if APP_URL else "http://localhost:8000"
AUTHORIZE = {"google": "https://accounts.google.com/o/oauth2/v2/auth", "linkedin": "https://www.linkedin.com/oauth/v2/authorization"}
TOKEN = {"google": "https://oauth2.googleapis.com/token", "linkedin": "https://www.linkedin.com/oauth/v2/accessToken"}


def _client(provider: Provider) -> tuple[str, str] | None:
    prefix = provider.upper()
    key = os.getenv(f"{prefix}_CLIENT_ID", "").strip()
    secret = os.getenv(f"{prefix}_CLIENT_SECRET", "").strip()
    if key and secret:
        return key, secret
    if provider == "google" and not CLOUD and CREDS.is_file():
        try:
            data = json.loads(CREDS.read_text())
            local = data.get("web") or data.get("installed") or {}
            if local.get("client_id") and local.get("client_secret"):
                return local["client_id"], local["client_secret"]
        except (ValueError, OSError):
            pass
    return None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _safe_redirect(url: str | None, provider: Provider) -> str:
    fallback = DEFAULT_ORIGIN + ("/login?role=expert" if provider == "linkedin" else "/")
    if not url or "\\" in url or any(ord(c) < 32 for c in url):
        return fallback
    try:
        parsed = urlsplit(url)
        if f"{parsed.scheme}://{parsed.netloc}" in ALLOWED_ORIGINS:
            return urlunsplit(parsed._replace(fragment=""))
    except ValueError:
        pass
    return fallback


def _storage_configured() -> bool:
    return not CLOUD or bool(APP_URL and DATABASE_URL)


@router.get("/providers")
def providers():
    return JSONResponse({p: bool(_client(p)) and _storage_configured() for p in ("google", "linkedin")},
                        headers={"Cache-Control": "no-store"})


def _cookie_name(provider: Provider, state: str) -> str:
    return f"sutradhar_{provider}_{state}"


def _cookie_path(provider: Provider) -> str:
    return urlsplit(f"{API_BASE}/auth/{provider}/callback").path


@router.get("/{provider}/login")
def login(provider: Provider, redirect: str | None = None):
    client = _client(provider)
    if not client or not _storage_configured():
        raise HTTPException(503, detail=f"{PROVIDER_LABELS[provider]} sign-in is awaiting configuration")
    state = secrets.token_urlsafe(28)
    verifier = secrets.token_urlsafe(48)
    browser_secret = secrets.token_urlsafe(32)
    db.ex("DELETE FROM auth_states WHERE expires_at < ?", (time.time(),))
    db.ex("INSERT INTO auth_states (state,verifier,redirect,expires_at,provider,browser_hash) VALUES (?,?,?,?,?,?)",
          (state, verifier, _safe_redirect(redirect, provider), time.time() + STATE_TTL_S, provider, _hash(browser_secret)))
    params = {"client_id": client[0], "redirect_uri": f"{API_BASE}/auth/{provider}/callback", "response_type": "code",
              "scope": "openid email profile" if provider == "google" else "openid profile", "state": state}
    if provider == "google":
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params.update(prompt="select_account", code_challenge=challenge, code_challenge_method="S256")
    response = RedirectResponse(AUTHORIZE[provider] + "?" + urlencode(params), status_code=302,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.set_cookie(_cookie_name(provider, state), browser_secret, path=_cookie_path(provider),
                        max_age=STATE_TTL_S, secure=API_BASE.startswith("https://"), httponly=True, samesite="lax")
    return response


@lru_cache(maxsize=1)
def _linkedin_keys():
    return jwt.PyJWKClient("https://www.linkedin.com/oauth/openid/jwks", timeout=8)


def _identity(provider: Provider, raw: str, client_id: str) -> dict:
    if provider == "google":
        claims = google_id_token.verify_oauth2_token(raw, g_requests.Request(), client_id)
        if not claims.get("email") or claims.get("email_verified") is not True:
            raise ValueError("A verified email is required")
        email = claims["email"].lower()
    else:
        key = _linkedin_keys().get_signing_key_from_jwt(raw).key
        claims = jwt.decode(raw, key, algorithms=["RS256"], issuer="https://www.linkedin.com/oauth", audience=client_id,
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        email = None
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ValueError("Missing provider identity")
    return {"provider": provider, "subject": claims["sub"], "email": email,
            "name": claims.get("name") or email or "Expert",
            "picture": claims.get("picture") or ""}


@router.get("/{provider}/callback")
def callback(provider: Provider, request: Request, state: str = "", code: str = "", error: str = ""):
    if not state or len(state) > 128 or not state.isascii() or not all(c.isalnum() or c in "_-" for c in state):
        raise HTTPException(400, detail="Invalid sign-in state. Start sign-in again.")
    cookie = _cookie_name(provider, state)
    browser_secret = request.cookies.get(cookie)
    if not browser_secret:
        raise HTTPException(400, detail="Start sign-in again in this browser")
    row = db.q1("DELETE FROM auth_states WHERE state=? AND provider=? AND browser_hash=? RETURNING *",
                (state, provider, _hash(browser_secret)))
    if not row or row["expires_at"] < time.time():
        raise HTTPException(400, detail="This sign-in link has expired. Start again.")
    role = "user" if provider == "google" else "expert"
    result_url = f"{DEFAULT_ORIGIN}/login?role={role}&result=cancelled"
    if not error:
        client = _client(provider)
        if not client or not code:
            raise HTTPException(400, detail="Incomplete sign-in. Start again.")
        form = {"code": code, "client_id": client[0], "client_secret": client[1],
                "redirect_uri": f"{API_BASE}/auth/{provider}/callback", "grant_type": "authorization_code"}
        if provider == "google":
            form["code_verifier"] = row["verifier"]
        try:
            tokens = httpx.post(TOKEN[provider], data=form, timeout=16)
            tokens.raise_for_status()
            user = _identity(provider, tokens.json()["id_token"], client[0])
        except (ValueError, KeyError, httpx.HTTPError, jwt.PyJWTError, GoogleAuthError) as exc:
            raise HTTPException(401, detail=f"Could not verify {PROVIDER_LABELS[provider]} sign-in") from exc
        session = secrets.token_urlsafe(32)
        db.ex("INSERT INTO auth_sessions (token_hash,provider,subject,email,name,picture,created_at,expires_at) "
              "VALUES (?,?,?,?,?,?,?,?)", (_hash(session), provider, user["subject"], user["email"], user["name"],
                                           user["picture"], now_iso(), time.time() + SESSION_TTL_S))
        result_url = f"{row['redirect']}#session={session}"
    response = RedirectResponse(result_url, status_code=302,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.delete_cookie(cookie, path=_cookie_path(provider), secure=API_BASE.startswith("https://"), httponly=True, samesite="lax")
    return response


def current_user(authorization: str | None) -> dict | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return db.q1("SELECT email,name,picture,provider,subject FROM auth_sessions "
                 "WHERE token_hash=? AND expires_at>? AND provider IN (?,?)",
                 (_hash(authorization.split(" ", 1)[1].strip()), time.time(), "google", "linkedin"))


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if not user:
        raise HTTPException(401, detail="not signed in")
    return JSONResponse(user, headers={"Cache-Control": "no-store"})


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        db.ex("DELETE FROM auth_sessions WHERE token_hash=?", (_hash(authorization.split(" ", 1)[1].strip()),))
    return {"ok": True}
