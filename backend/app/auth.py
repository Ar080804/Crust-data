"""Owner: Aditya. Real "Sign in with Google" (OpenID Connect) for the backend.

Flow (no frontend code needed to try it: open http://localhost:8000/auth/google/login in a browser):
  1. GET  /auth/google/login?redirect=<frontend url>  -> 302 to Google's consent page (state + PKCE)
  2. Google -> GET /auth/google/callback?code&state   -> we exchange the code, VERIFY the ID token
     (signature, audience, issuer, expiry, email_verified), create a session, and
     302 back to <redirect>#session=<token>
  3. Frontend sends  Authorization: Bearer <token>   ->  GET /auth/me, POST /auth/logout

Uses the same Google OAuth client as the Calendar (credentials.json, "Desktop app" type, which Google
allows to redirect to localhost). Users must be listed as Test users on the OAuth consent screen.
"""
import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token as g_id_token

from . import db
from .config import APP_URL, CLOUD, ROOT, now_iso

router = APIRouter(prefix="/auth", tags=["auth"])

CREDS = ROOT / "credentials.json"
CALLBACK = f"{APP_URL}/api/auth/google/callback" if APP_URL else "http://localhost:8000/auth/google/callback"
SESSION_TTL_S = 7 * 24 * 3600
STATE_TTL_S = 10 * 60
# Only send users back to our own frontend (prevents open redirects).
ALLOWED_REDIRECT_ORIGINS = {APP_URL} if CLOUD else {"http://localhost:5173", "http://127.0.0.1:5173"}
DEFAULT_REDIRECT = (APP_URL or "http://localhost:5173") + "/"


def _client() -> tuple[str, str]:
    client_id, secret = os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")
    if client_id and secret and (APP_URL or not CLOUD):
        return client_id, secret
    if CLOUD:
        raise HTTPException(503, detail="Google sign-in is awaiting configuration")
    if not CREDS.exists():
        raise HTTPException(503, detail="Google login is not configured (credentials.json missing)")
    c = json.loads(CREDS.read_text())
    c = c.get("web") or c.get("installed") or {}
    return c["client_id"], c["client_secret"]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()  # only hashes are stored


def _safe_redirect(url: str | None) -> str:
    if not url:
        return DEFAULT_REDIRECT
    u = urlparse(url)
    return url if f"{u.scheme}://{u.netloc}" in ALLOWED_REDIRECT_ORIGINS else DEFAULT_REDIRECT


@router.get("/google/login")
def google_login(redirect: str | None = Query(default=None)):
    client_id, _ = _client()
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    db.ex("DELETE FROM auth_states WHERE expires_at < ?", (time.time(),))
    db.ex("INSERT INTO auth_states (state, verifier, redirect, expires_at) VALUES (?,?,?,?)",
          (state, verifier, _safe_redirect(redirect), time.time() + STATE_TTL_S))
    params = {"client_id": client_id, "redirect_uri": CALLBACK, "response_type": "code",
              "scope": "openid email profile", "state": state, "code_challenge": challenge,
              "code_challenge_method": "S256", "prompt": "select_account"}
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=302)


@router.get("/google/callback")
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(400, detail=f"Google sign-in was cancelled or failed: {error}")
    if not code or not state:
        raise HTTPException(400, detail="missing code or state")
    row = db.q1("DELETE FROM auth_states WHERE state=? RETURNING *", (state,))
    if not row or row["expires_at"] < time.time():
        raise HTTPException(400, detail="login link expired or invalid; start again")
    client_id, client_secret = _client()
    try:
        tok = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": CALLBACK, "grant_type": "authorization_code", "code_verifier": row["verifier"]})
        tok.raise_for_status()
        raw_id_token = tok.json()["id_token"]
        # Verifies Google's signature, audience (our client_id), issuer and expiry.
        claims = g_id_token.verify_oauth2_token(raw_id_token, g_requests.Request(), client_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(401, detail=f"could not verify Google sign-in: {type(e).__name__}")
    if not claims.get("email") or not claims.get("email_verified"):
        raise HTTPException(401, detail="Google account email is not verified")
    session = secrets.token_urlsafe(32)
    db.ex("INSERT INTO auth_sessions (token_hash, email, name, picture, created_at, expires_at) VALUES (?,?,?,?,?,?)",
          (_hash(session), claims["email"].lower(), claims.get("name", ""), claims.get("picture", ""),
           now_iso(), time.time() + SESSION_TTL_S))
    # Fragment (#) so the token never reaches server logs or Referer headers.
    return RedirectResponse(f"{row['redirect']}#session={session}", status_code=302)


def current_user(authorization: str | None) -> dict | None:
    """Return the signed-in user for an 'Authorization: Bearer <token>' header, or None."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    row = db.q1("SELECT email, name, picture, expires_at FROM auth_sessions WHERE token_hash=?",
                (_hash(authorization.split(" ", 1)[1].strip()),))
    if not row or row["expires_at"] < time.time():
        return None
    return {"email": row["email"], "name": row["name"], "picture": row["picture"], "provider": "google"}


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if not user:
        raise HTTPException(401, detail="not signed in")
    return user


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        db.ex("DELETE FROM auth_sessions WHERE token_hash=?", (_hash(authorization.split(" ", 1)[1].strip()),))
    return {"ok": True}
