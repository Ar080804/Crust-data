"""Owner: Sunil. Expert onboarding with identity binding: LinkedIn login <-> Telegram account <-> Crustdata profile.

    python -m backend.integrations.onboarding        # http://localhost:8001

Flow:
 1. Expert opens the site -> "Sign in with LinkedIn" (OpenID Connect). LinkedIn returns name, verified email, photo.
    Proves: this person controls that LinkedIn account.
 2. Site shows a one-time deep link t.me/<bot>?start=<token>. Expert presses START.
    Proves: this Telegram account belongs to the same person who just logged in (only they saw the token).
 3. Expert pastes their LinkedIn profile URL -> Crustdata enrich -> the profile name must match the LinkedIn login name,
    and the current role becomes a verified claim.
 4. Expert is added to data/experts.json with telegram_chat_id and an "identity" block.

Env (.env at repo root):
  LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET   from the LinkedIn developer app (Auth tab)
  ONBOARDING_BOT_TOKEN                         bot used for step 2. REQUIRED, no fallback: it must NOT be the
                                               booking bot, or this poller would eat the experts' booking replies.
  BOOKING_BOT_USERNAME                         bot that sends booking messages (default aditya1267_bot). The expert
                                               is told to START it too: a bot can only message people who started it.
  ONBOARDING_BASE_URL                          default http://localhost:8001 (must match the app's redirect URL)
Personal data stays in data/onboarding.db (gitignored by *.db).
"""
import html
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import crustdata

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
POOL = ROOT / "data" / "experts.json"          # read only
OUTFILE = ROOT / "data" / "onboarded.json"     # onboarding results go here, never into experts.json
DB = ROOT / "data" / "onboarding.db"
IST = timezone(timedelta(hours=5, minutes=30))

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "").strip()
BASE = os.getenv("ONBOARDING_BASE_URL", "http://localhost:8001").rstrip("/")
REDIRECT = f"{BASE}/auth/linkedin/callback"
BOT_TOKEN = os.getenv("ONBOARDING_BOT_TOKEN", "").strip()   # no fallback to TELEGRAM_BOT_TOKEN (booking bot)
BOOKING_BOT = os.getenv("BOOKING_BOT_USERNAME", "aditya1267_bot").strip().lstrip("@")

_db = sqlite3.connect(DB, check_same_thread=False, isolation_level=None)
_db.row_factory = sqlite3.Row
_lock = threading.Lock()
_db.execute("""CREATE TABLE IF NOT EXISTS onboard (
  token TEXT PRIMARY KEY, state TEXT, li_sub TEXT, li_name TEXT, li_email TEXT, li_email_verified INTEGER,
  li_picture TEXT, chat_id TEXT, tg_name TEXT, linkedin_url TEXT, crust_name TEXT, name_match INTEGER,
  expert_id TEXT, claims TEXT, created_at TEXT, updated_at TEXT)""")


def _now():
    return datetime.now(IST).isoformat(timespec="seconds")


def _get(**kw):
    k, v = next(iter(kw.items()))
    with _lock:
        r = _db.execute(f"SELECT * FROM onboard WHERE {k}=?", (v,)).fetchone()
    return dict(r) if r else None


def _set(token, **fields):
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        _db.execute(f"UPDATE onboard SET {cols} WHERE token=?", (*fields.values(), token))


# ---- Telegram (bot API, separate from backend/integrations/telegram.py so it can use its own token) ----------

def _tg(method, **params):
    poll = int(params.get("timeout", 0))
    r = httpx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=params, timeout=poll + 10)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method}: {data.get('description')}")
    return data["result"]


BOT_USERNAME = ""


def _bot_loop():
    """Long-poll the onboarding bot; bind chat_id when someone presses START with a valid token."""
    offset = 0
    while True:
        try:
            for u in _tg("getUpdates", offset=offset, timeout=25, allowed_updates=["message"]):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                text = (msg.get("text") or "").strip()
                chat = str(msg.get("chat", {}).get("id", ""))
                m = re.match(r"^/start\s+([A-Za-z0-9_-]{16,64})$", text)
                if not m:
                    if text.startswith("/start"):
                        _tg("sendMessage", chat_id=chat, text="Hi! To join as an expert, open the Sutradhar "
                            f"onboarding page and use the Connect Telegram button: {BASE}")
                    continue
                row = _get(token=m.group(1))
                if not row or not row["li_sub"]:
                    _tg("sendMessage", chat_id=chat, text="This link is invalid or expired. Please start again on the website.")
                    continue
                if row["chat_id"] and row["chat_id"] != chat:
                    _tg("sendMessage", chat_id=chat, text="This link was already used by another Telegram account.")
                    continue
                frm = msg.get("from", {})
                tg_name = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x)
                _set(row["token"], chat_id=chat, tg_name=tg_name)
                _tg("sendMessage", chat_id=chat, text=f"✅ Telegram linked to LinkedIn account: {row['li_name']}.\n"
                    f"Booking requests will come from @{BOOKING_BOT}: open https://t.me/{BOOKING_BOT} and press START.\n"
                    "Go back to the website to finish (paste your LinkedIn profile URL).")
        except Exception as e:  # noqa: BLE001  keep polling
            print("onboarding bot:", e)
            time.sleep(3)


# ---- matching LinkedIn login <-> Crustdata profile ---------------------------------------------------------

def _name_tokens(n):
    return {w for w in re.findall(r"[a-z]+", (n or "").lower()) if len(w) > 1}


def names_match(a, b) -> bool:
    ta, tb = _name_tokens(a), _name_tokens(b)
    return bool(ta and tb) and (ta <= tb or tb <= ta or len(ta & tb) >= 2)


def _next_expert_id(pool):
    return f"e{max([int(e['expert_id'][1:]) for e in pool if e['expert_id'][1:].isdigit()] + [0]) + 1}"


def finish(token: str, linkedin_url: str) -> dict:
    row = _get(token=token)
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    # Reuse a pool listing only if BOTH the Telegram account and the name match the LinkedIn login;
    # otherwise one person's identity could be attached to someone else's listing.
    existing = next((e for e in pool if row["chat_id"] and str(e.get("telegram_chat_id")) == row["chat_id"]
                     and names_match(e.get("name"), row["li_name"])), None)
    eid = (existing or {}).get("expert_id") or row["expert_id"] or f"ob_{row['li_sub'][:10]}"
    m = re.search(r"linkedin\.com/in/([A-Za-z0-9\-_%]+)", linkedin_url or "")
    if not m:
        return {"ok": False, "error": "Please paste a LinkedIn profile URL like https://www.linkedin.com/in/your-name/"}
    linkedin_url = f"https://www.linkedin.com/in/{m.group(1)}/"
    # Own cache key, so onboarding can never overwrite the pool's cache files (e.g. e2.json used in the demo).
    probe = {"expert_id": f"ob_{row['li_sub'][:10]}", "linkedin_url": linkedin_url}
    try:
        raw, fetched_at = crustdata.fetch(probe)
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"Crustdata rejected the lookup ({e.response.status_code}): {e.response.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Crustdata lookup failed: {type(e).__name__}"}
    roles = crustdata.roles_from(raw)
    if roles is None:
        _set(token, linkedin_url=linkedin_url, expert_id=eid, name_match=0, crust_name=None)
        return {"ok": False, "error": "Crustdata has no record of this LinkedIn profile yet (brand-new profiles take "
                                      "time to be indexed), so your work history can't be verified. LinkedIn and "
                                      "Telegram are verified; try your main LinkedIn profile."}
    person = raw[0]["matches"][0]["person_data"]
    crust_name = person.get("basic_profile", {}).get("name") or ""
    match = names_match(row["li_name"], crust_name)
    current = [r for r in roles if not r["end"]] or roles
    claims = [f"{r['title']} at {r['company']}, {(r['start'] or '????')[:4]}-present" for r in current[:2]]
    _set(token, linkedin_url=linkedin_url, expert_id=eid, crust_name=crust_name, name_match=int(match),
         claims=json.dumps(claims))
    if not match:
        return {"ok": False, "error": f"Name mismatch: LinkedIn login is '{row['li_name']}', "
                                      f"profile is '{crust_name}'. Use your own profile URL."}
    if not row["chat_id"]:
        return {"ok": False, "error": "Connect Telegram first (step 2)."}
    headline = person.get("basic_profile", {}).get("headline") or (current[0]["title"] if current else "")
    days = ["2026-11-06", "2026-11-07", "2026-11-08"]
    expert = {
        "expert_id": eid, "name": row["li_name"], "headline": headline, "linkedin_url": linkedin_url,
        "rate_inr": 1500,
        "availability": [{"start": f"{d}T17:00:00+05:30", "end": f"{d}T22:00:00+05:30"} for d in days],
        "telegram_chat_id": row["chat_id"], "email": row["li_email"] or "", "claims": claims, "simulated": False,
        "identity": {"status": "verified", "method": "linkedin_oidc+telegram_deeplink+crustdata_name",
                     "linkedin_name": row["li_name"], "crustdata_name": crust_name,
                     "email_verified": bool(row["li_email_verified"]), "verified_at": _now()},
    }
    if existing:
        # Already in the pool (e.g. a teammate used in the demo): keep their listing, only attach the identity proof.
        expert = {**existing, "identity": expert["identity"]}
    out = json.loads(OUTFILE.read_text(encoding="utf-8")) if OUTFILE.exists() else {}
    out[eid] = expert
    OUTFILE.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verified = crustdata.verify(expert)
    _set(token, state="done", claims=json.dumps(verified, ensure_ascii=False))
    return {"ok": True, "expert": expert, "verification": verified}


# ---- web --------------------------------------------------------------------------------------------------
# Look and feel: reuses Deepak's design system (frontend/src/index.css) so onboarding feels like the same app.

app = FastAPI(title="Sutradhar expert onboarding")

FRONTEND_CSS = ROOT / "frontend" / "src" / "index.css"
APP_URL = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")

EXTRA_CSS = """
.ob-steps{display:grid;gap:12px;margin-top:22px}
.ob-step{border:1px solid var(--line-2);border-radius:var(--r);background:var(--surface);padding:16px 18px;
  box-shadow:var(--shadow-s);animation:rise .25s ease both}
.ob-step.is-done{border-color:color-mix(in srgb,var(--ok) 45%,transparent);background:color-mix(in srgb,var(--ok-soft) 60%,var(--surface))}
.ob-step.is-now{border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-soft)}
.ob-step.is-next{opacity:.55}
.ob-head{display:flex;align-items:center;gap:10px}
.ob-num{width:24px;height:24px;border-radius:999px;display:grid;place-items:center;font-family:var(--mono);font-size:12px;
  background:var(--surface-2);color:var(--muted);flex-shrink:0}
.is-done .ob-num{background:var(--ok);color:#fff}.is-now .ob-num{background:var(--accent);color:#fff}
.ob-title{font-weight:600;font-size:15px}
.ob-body{margin:10px 0 0 34px;display:grid;gap:10px}
.ob-body .muted{font-size:13.5px}
.ob-who{display:flex;align-items:center;gap:10px}
.ob-who img{width:34px;height:34px;border-radius:999px;object-fit:cover}
.ob-claim{display:grid;gap:4px;padding:10px 12px;border-radius:12px;background:var(--surface-2)}
.ob-claim .ev{font-size:12.5px;color:var(--muted)}
.ob-claim .src{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.ob-wait{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.ob-dot{width:8px;height:8px;border-radius:999px;background:var(--accent);animation:obpulse 1.2s ease-in-out infinite}
@keyframes obpulse{50%{opacity:.25}}
.ob-hero{display:grid;place-items:center;text-align:center;gap:10px;padding:8px 0 4px}
.ob-check{width:56px;height:56px;border-radius:999px;display:grid;place-items:center;background:var(--ok-soft);color:var(--ok);font-size:28px}
.btn-tg{background:#229ed9;color:#fff;text-decoration:none;justify-content:center}
.btn-tg:hover{background:#1c8cc2}
a.btn-oauth{text-decoration:none}
.ob-back{display:block;text-align:center;margin-top:18px;color:var(--muted);font-size:13px;text-decoration:none}
.ob-back:hover{color:var(--ink)}
.ob-err{border:1px solid color-mix(in srgb,var(--bad) 45%,transparent);background:var(--bad-soft);color:var(--ink);
  border-radius:12px;padding:12px 14px;font-size:14px;margin-top:18px}
"""

LOGO = ("<svg width=30 height=30 viewBox='0 0 32 32' aria-hidden class=logo><defs><linearGradient id=lg x1=0 y1=0 x2=1 y2=1>"
        "<stop offset=0 stop-color='#8b8dff'/><stop offset=1 stop-color='#5e6ad2'/></linearGradient></defs>"
        "<rect width=32 height=32 rx=9 fill='url(#lg)'/><path d='M5 21c4-9 7-9 11 0s7 9 11 0' fill=none stroke='#fff' "
        "stroke-opacity=.55 stroke-width=2.2 stroke-linecap=round /><circle cx=9 cy=15.5 r=2.3 fill='#fff'/>"
        "<circle cx=16 cy=21 r=2.3 fill='#fff'/><circle cx=23 cy=15.5 r=2.3 fill='#fff'/></svg>")
LI_ICON = ("<svg width=18 height=18 viewBox='0 0 24 24' aria-hidden class=icon><rect width=24 height=24 rx=4 fill='#0A66C2'/>"
           "<path fill='#fff' d='M7.1 9.5H4.6V19h2.5V9.5zM5.9 5.2a1.45 1.45 0 1 0 0 2.9 1.45 1.45 0 0 0 0-2.9zM19.4 13.6"
           "c0-2.6-1.4-4.3-3.6-4.3-1.3 0-2.1.7-2.5 1.3V9.5h-2.4V19h2.5v-4.9c0-1.3.4-2.4 1.8-2.4 1.3 0 1.7 1.1 1.7 2.5V19h2.5v-5.4z'/></svg>")
TG_ICON = ("<svg width=18 height=18 viewBox='0 0 24 24' aria-hidden class=icon><path fill='currentColor' d='M21.9 4.3 18.7 19.4c-.2 1"
           "-.9 1.3-1.8.8l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.3-5 9.2-8.3c.4-.4-.1-.6-.6-.2L6.2 13.1 1.3 11.6c-1-.3-1-1 .2-1.5"
           "L20.6 2.8c.9-.3 1.6.2 1.3 1.5z'/></svg>")
SHIELD = ("<svg width=16 height=16 viewBox='0 0 24 24' class=icon fill=none stroke='currentColor' stroke-width=2 "
          "stroke-linecap=round stroke-linejoin=round><path d='M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z'/><path d='M9 12l2 2 4-4'/></svg>")
MSG = ("<svg width=16 height=16 viewBox='0 0 24 24' class=icon fill=none stroke='currentColor' stroke-width=2 "
       "stroke-linecap=round stroke-linejoin=round><path d='M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z'/></svg>")
CHECK = ("<svg width=16 height=16 viewBox='0 0 24 24' class=icon fill=none stroke='currentColor' stroke-width=2 "
         "stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=12 r=9 /><path d='M8 12l3 3 5-6'/></svg>")


def _css() -> str:
    try:
        return FRONTEND_CSS.read_text(encoding="utf-8") + EXTRA_CSS
    except OSError:  # frontend folder missing: keep a usable dark theme
        return (":root{--paper:#08090a;--surface:#0f1012;--surface-2:#17181b;--ink:#f7f8f8;--ink-2:#d0d6e0;--muted:#8a8f98;"
                "--line:rgba(255,255,255,.08);--line-2:rgba(255,255,255,.14);--accent:#8183ff;--accent-soft:rgba(129,131,255,.14);"
                "--ok:#4cb782;--ok-soft:rgba(76,183,130,.13);--bad:#eb5757;--bad-soft:rgba(235,87,87,.13);--r:14px;"
                "--sans:Inter,system-ui,sans-serif;--mono:ui-monospace,monospace}body{background:var(--paper);color:var(--ink);"
                "font-family:var(--sans);margin:0}" + EXTRA_CSS)


def page(card: str, title: str = "Join as an expert", sub: str = "") -> HTMLResponse:
    sub_html = f"<p class='muted small'>{sub}</p>" if sub else ""
    return HTMLResponse(f"""<!doctype html><html lang=en data-theme=dark><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Sutradhar · Expert onboarding</title>
<link rel=preconnect href="https://fonts.googleapis.com"><link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel=stylesheet>
<style>{_css()}</style></head><body><div class=auth>
<section class=auth-art><div class=auth-art-in>
  <div class=row>{LOGO}<span class=brand-word>Sutradhar</span></div>
  <h1 class=auth-line>Get paid for<br>short expert calls.<br><span class=muted-line>We just make sure</span> you're real.</h1>
  <ul class=auth-points>
    <li>{SHIELD} Sign in with LinkedIn: proves the account is yours</li>
    <li>{MSG} One-tap Telegram link: requests reach the right phone</li>
    <li>{CHECK} Work history checked against Crustdata</li>
  </ul>
  <p class=auth-hint>Clients only ever see verified experts.</p>
</div></section>
<section class=auth-panel><div class=auth-card>
  <h2 class=auth-title>{title}</h2>{sub_html}
  {card}
  <a class=ob-back href="{APP_URL}/login">← Back to Sutradhar</a>
</div></section></div></body></html>""")


def page_error(msg: str, back: str = "/") -> HTMLResponse:
    return page(f"<div class=ob-err>{html.escape(msg)}</div>"
                f"<p style='margin-top:14px'><a class='btn btn-ghost btn-block' href='{back}'>Try again</a></p>",
                title="Something went wrong")


def step(n: int, state: str, title: str, body: str = "") -> str:
    tag = {"done": "<span class='tag tag-ok push'>Done</span>", "now": "<span class='tag tag-live push'>Now</span>",
           "next": "<span class='tag push'>Next</span>"}[state]
    num = "✓" if state == "done" else str(n)
    inner = f"<div class=ob-body>{body}</div>" if body else ""
    return (f"<div class='ob-step is-{state}'><div class=ob-head><span class=ob-num>{num}</span>"
            f"<span class=ob-title>{title}</span>{tag}</div>{inner}</div>")


@app.get("/")
def home():
    warn = "" if CLIENT_ID else "<div class=ob-err>LINKEDIN_CLIENT_ID is not set in .env</div>"
    s1 = step(1, "now", "Sign in with LinkedIn",
              f"<a class=btn-oauth href='/auth/linkedin/login'>{LI_ICON} Continue with LinkedIn</a>"
              "<span class=muted>We only read your name, email and photo.</span>")
    return page(warn + "<div class=ob-steps>" + s1 + step(2, "next", "Connect Telegram")
                + step(3, "next", "Verify your work history") + "</div>",
                sub="Three quick checks, about a minute. Then clients can book short paid calls with you.")


@app.get("/auth/linkedin/login")
def li_login():
    token = secrets.token_urlsafe(18)
    state = secrets.token_urlsafe(16)
    with _lock:
        _db.execute("INSERT INTO onboard (token, state, created_at, updated_at) VALUES (?,?,?,?)",
                    (token, f"oauth:{state}", _now(), _now()))
    q = urlencode({"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
                   "state": f"{state}.{token}", "scope": "openid profile email"})
    return RedirectResponse(f"https://www.linkedin.com/oauth/v2/authorization?{q}")


@app.get("/auth/linkedin/callback")
def li_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error:
        return page_error(f"LinkedIn: {error_description or error}")
    st, _, token = state.partition(".")
    row = _get(token=token)
    if not row or row["state"] != f"oauth:{st}":
        return page_error("This login link expired. Please start again.")
    tok = httpx.post("https://www.linkedin.com/oauth/v2/accessToken", timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    if tok.status_code != 200:
        return page_error(f"LinkedIn sign-in failed: {tok.text[:200]}")
    info = httpx.get("https://api.linkedin.com/v2/userinfo", timeout=30,
                     headers={"Authorization": f"Bearer {tok.json()['access_token']}"}).json()
    _set(token, state="linkedin_ok", li_sub=info.get("sub"), li_name=info.get("name"), li_email=info.get("email"),
         li_email_verified=int(bool(info.get("email_verified"))), li_picture=info.get("picture"))
    return RedirectResponse(f"/onboard/{token}", status_code=303)


@app.get("/onboard/{token}")
def onboard(token: str):
    row = _get(token=token)
    if not row or not row["li_sub"]:
        return RedirectResponse("/")
    esc = html.escape
    pic = f"<img src='{esc(row['li_picture'])}' alt=''>" if row["li_picture"] else ""
    ver = " <span class='tag tag-ok'>verified email</span>" if row["li_email_verified"] else ""
    s1 = step(1, "done", "LinkedIn",
              f"<div class=ob-who>{pic}<div><div class=strong>{esc(row['li_name'] or '')}</div>"
              f"<div class='muted small'>{esc(row['li_email'] or '')}{ver}</div></div></div>")
    poll = ""
    if row["chat_id"]:
        s2 = step(2, "done", "Telegram", f"<span class=muted>Linked to {esc(row['tg_name'] or 'your account')}</span>")
    else:
        link = f"https://t.me/{BOT_USERNAME}?start={token}"
        s2 = step(2, "now", "Connect Telegram",
                  f"<a class='btn btn-tg btn-block' href='{link}' target=_blank rel=noreferrer>{TG_ICON} Open @{esc(BOT_USERNAME)} and press START</a>"
                  "<span class=muted>This link works once and only for you.</span>"
                  "<div class=ob-wait><span class=ob-dot></span> Waiting for START…</div>")
        poll = (f"<script>setInterval(async()=>{{try{{const r=await fetch('/api/onboard/{token}');"
                f"const j=await r.json();if(j.telegram_linked)location.reload()}}catch(e){{}}}},2000)</script>")
    if row["state"] == "done":
        claims = json.loads(row["claims"] or "[]")
        tagc = {"verified": "tag-ok", "contradicted": "tag-bad", "unverifiable": "tag-warn"}
        items = "".join(f"<div class=ob-claim><div class=row><span class='tag {tagc.get(c['status'], '')}'>{esc(c['status'])}</span>"
                        f"<span class=strong>{esc(c['text'])}</span></div><div class=ev>{esc(c.get('evidence') or '')}</div>"
                        f"<div class=src>{esc(c['source'])}</div></div>" for c in claims)
        s3 = step(3, "done", "Work history", items)
        hero = (f"<div class=ob-hero><div class=ob-check>✓</div><div class=h2>You're verified</div>"
                f"<p class='muted small'>Crustdata profile <b>{esc(row['crust_name'] or '')}</b> matches your LinkedIn login. "
                f"Saved as {esc(row['expert_id'] or '')}.</p></div>")
        last = (f"<div class='ob-step is-now'><div class=ob-head><span class=ob-num>→</span>"
                f"<span class=ob-title>Last step: get booking requests</span></div><div class=ob-body>"
                f"<span class=muted>Requests are sent by @{esc(BOOKING_BOT)}. Telegram only lets a bot message people who "
                f"started it, so press START there too.</span>"
                f"<a class='btn btn-tg btn-block' href='https://t.me/{esc(BOOKING_BOT)}' target=_blank rel=noreferrer>"
                f"{TG_ICON} Open @{esc(BOOKING_BOT)}</a></div></div>")
        return page(hero + "<div class=ob-steps>" + last + s1 + s2 + s3 + "</div>", title="All set")
    if row["chat_id"]:
        s3 = step(3, "now", "Verify your work history",
                  f"<form method=post action='/onboard/{token}/profile' class=auth-form>"
                  f"<label class=field><span>Your LinkedIn profile URL</span>"
                  f"<input name=linkedin_url placeholder='https://www.linkedin.com/in/your-name' required "
                  f"value='{esc(row['linkedin_url'] or '')}'></label>"
                  f"<button class='btn btn-primary btn-block'>Verify with Crustdata</button></form>"
                  "<span class=muted>The profile name must match your LinkedIn login.</span>")
    else:
        s3 = step(3, "next", "Verify your work history")
    return page("<div class=ob-steps>" + s1 + s2 + s3 + "</div>" + poll,
                sub="Three quick checks, about a minute.")


@app.post("/onboard/{token}/profile")
async def profile(token: str, request: Request):
    linkedin_url = parse_qs((await request.body()).decode()).get("linkedin_url", [""])[0]
    if not _get(token=token):
        return RedirectResponse("/", status_code=303)
    res = finish(token, linkedin_url.strip())
    if not res["ok"]:
        return page_error(res["error"], back=f"/onboard/{token}")
    return RedirectResponse(f"/onboard/{token}", status_code=303)


@app.get("/api/onboard/{token}")
def onboard_status(token: str):
    row = _get(token=token)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"linkedin": bool(row["li_sub"]), "telegram_linked": bool(row["chat_id"]),
            "done": row["state"] == "done", "expert_id": row["expert_id"]}


def main():
    global BOT_USERNAME
    import uvicorn
    if not BOT_TOKEN:
        raise SystemExit("Set ONBOARDING_BOT_TOKEN in .env (a separate bot, NOT the booking bot)")
    BOT_USERNAME = _tg("getMe")["username"]
    if BOT_USERNAME.lower() == BOOKING_BOT.lower():
        raise SystemExit(f"ONBOARDING_BOT_TOKEN is the booking bot @{BOOKING_BOT}; use a different bot")
    print(f"onboarding bot: @{BOT_USERNAME}   site: {BASE}   linkedin redirect: {REDIRECT}")
    threading.Thread(target=_bot_loop, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=int(BASE.rsplit(":", 1)[-1]) if BASE.count(":") > 1 else 8001)


if __name__ == "__main__":
    main()
