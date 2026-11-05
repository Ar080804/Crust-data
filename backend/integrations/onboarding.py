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

app = FastAPI(title="Sutradhar expert onboarding")

CSS = """body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#1d1d1f}
h1{font-size:26px}.step{border:1px solid #ddd;border-radius:12px;padding:16px 18px;margin:14px 0}
.done{border-color:#2e9e5b;background:#f2fbf5}.btn{display:inline-block;padding:10px 16px;border-radius:8px;
background:#0a66c2;color:#fff;text-decoration:none;border:0;font-size:15px;cursor:pointer}
.tg{background:#229ed9}input{width:100%;padding:9px;font-size:15px;margin:8px 0;box-sizing:border-box}
.muted{color:#666;font-size:14px}.err{color:#c0392b}.claim{margin:6px 0}img{border-radius:50%;vertical-align:middle}"""


def page(body):
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>Sutradhar onboarding</title>"
                        f"<style>{CSS}</style><h1>Join Sutradhar as an expert</h1>{body}")


@app.get("/")
def home():
    warn = "" if CLIENT_ID else "<p class=err>LINKEDIN_CLIENT_ID is not set in .env</p>"
    return page(f"""<p class=muted>We verify three things: you own your LinkedIn account, your Telegram account is yours,
and your work history (via Crustdata). Then clients can book short paid calls with you.</p>{warn}
<div class=step><b>1. Sign in with LinkedIn</b><p><a class=btn href="/auth/linkedin/login">Sign in with LinkedIn</a></p></div>
<div class=step><b>2. Connect Telegram</b><p class=muted>after step 1</p></div>
<div class=step><b>3. Verify your profile</b><p class=muted>after step 2</p></div>""")


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
        return page(f"<p class=err>LinkedIn error: {html.escape(error_description or error)}</p><a href=/>Try again</a>")
    st, _, token = state.partition(".")
    row = _get(token=token)
    if not row or row["state"] != f"oauth:{st}":
        return page("<p class=err>Invalid or expired login state.</p><a href=/>Try again</a>")
    tok = httpx.post("https://www.linkedin.com/oauth/v2/accessToken", timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    if tok.status_code != 200:
        return page(f"<p class=err>Token exchange failed: {html.escape(tok.text[:300])}</p>")
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
    pic = f"<img src='{html.escape(row['li_picture'])}' width=40> " if row["li_picture"] else ""
    s1 = (f"<div class='step done'><b>1. LinkedIn ✅</b><p>{pic}{html.escape(row['li_name'] or '')} "
          f"<span class=muted>{html.escape(row['li_email'] or '')}"
          f"{' (verified email)' if row['li_email_verified'] else ''}</span></p></div>")
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    if row["chat_id"]:
        s2 = f"<div class='step done'><b>2. Telegram ✅</b><p>Linked: {html.escape(row['tg_name'] or row['chat_id'])}</p></div>"
    else:
        s2 = (f"<div class=step><b>2. Connect Telegram</b><p class=muted>Opens @{BOT_USERNAME}. Press START there. "
              f"This link works once and only for you.</p><a class='btn tg' href='{link}' target=_blank>Connect Telegram</a>"
              f"<p class=muted id=wait>Waiting for START…</p></div>")
    if row["state"] == "done":
        claims = json.loads(row["claims"] or "[]")
        icon = {"verified": "🟢", "contradicted": "🔴", "unverifiable": "🟡"}
        items = "".join(f"<div class=claim>{icon.get(c['status'], '')} {html.escape(c['text'])}<br>"
                        f"<span class=muted>{html.escape(c.get('evidence') or '')} · {html.escape(c['source'])}</span></div>"
                        for c in claims)
        s3 = (f"<div class='step done'><b>3. Profile verified ✅</b><p>Crustdata name: {html.escape(row['crust_name'] or '')} "
              f"(matches LinkedIn login)</p>{items}<p><b>Onboarded as {row['expert_id']}</b> (saved to data/onboarded.json) "
              f"with identity status 🟢 verified.</p><p><b>Last step:</b> booking requests are sent by @{BOOKING_BOT}. Telegram only lets a bot message "
              f"people who started it, so press START there too: <a class='btn tg' href='https://t.me/{BOOKING_BOT}' "
              f"target=_blank>Open @{BOOKING_BOT}</a></p></div>")
    elif row["chat_id"]:
        s3 = (f"<div class=step><b>3. Verify your profile</b><form method=post action='/onboard/{token}/profile'>"
              f"<input name=linkedin_url placeholder='https://www.linkedin.com/in/your-profile' required "
              f"value='{html.escape(row['linkedin_url'] or '')}'><button class=btn>Verify with Crustdata</button></form></div>")
    else:
        s3 = "<div class=step><b>3. Verify your profile</b><p class=muted>after step 2</p></div>"
    poll = "" if row["chat_id"] else (f"<script>setInterval(async()=>{{const r=await fetch('/api/onboard/{token}');"
                                      f"const j=await r.json();if(j.telegram_linked)location.reload()}},2000)</script>")
    return page(s1 + s2 + s3 + poll)


@app.post("/onboard/{token}/profile")
async def profile(token: str, request: Request):
    linkedin_url = parse_qs((await request.body()).decode()).get("linkedin_url", [""])[0]
    if not _get(token=token):
        return RedirectResponse("/", status_code=303)
    res = finish(token, linkedin_url.strip())
    if not res["ok"]:
        return page(f"<p class=err>{html.escape(res['error'])}</p><a href='/onboard/{token}'>Back</a>")
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
