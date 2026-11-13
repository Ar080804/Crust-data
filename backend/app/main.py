"""Owner: Aditya. HTTP API. Response shapes must match contract/CONTRACT.md exactly."""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from . import adapters, auth, db, engine, gcal
from .config import APP_URL, CLOUD, DATABASE_URL, RUN_WORKER_IN_API

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "contract" / "fixtures"
EVAL = ROOT / "backend" / "eval" / "latest.json"


@asynccontextmanager
async def lifespan(_app):
    if RUN_WORKER_IN_API:
        engine.start_worker()
    yield


app = FastAPI(title="Sutradhar", lifespan=lifespan)


# Contract: every error body is {"error": str}
@app.exception_handler(StarletteHTTPException)
async def http_error(_req, exc: StarletteHTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_req, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse({"error": f"invalid input: {where} {first.get('msg', '')}".strip()}, status_code=400)


@app.exception_handler(Exception)
async def server_error(_req, exc: Exception):
    return JSONResponse({"error": f"server error: {type(exc).__name__}"}, status_code=500)


app.include_router(auth.router)  # Sign in with Google: /auth/google/login, /auth/google/callback, /auth/me, /auth/logout
app.add_middleware(CORSMiddleware, allow_origins=([APP_URL] if CLOUD else ["http://localhost:5173", "http://127.0.0.1:5173"]),
                   allow_methods=["*"], allow_headers=["*"])


def session_user(authorization: str | None = Header(default=None)):
    user = auth.current_user(authorization)
    if CLOUD and not user:
        raise HTTPException(401, detail="Sign in with Google")
    if user and user["provider"] != "google":
        raise HTTPException(403, detail="Use a Google client account for booking requests")
    return user


def request_owner(rid: str, user=Depends(session_user)):
    if CLOUD:
        owner = db.q1("SELECT owner_email FROM requests WHERE id=?", (rid,))
        if owner is None or owner["owner_email"] != user["email"]:
            raise HTTPException(404, detail="Request not found")


@app.get("/health")
def health():
    if CLOUD and not DATABASE_URL:
        return JSONResponse({"database": "awaiting configuration"}, status_code=503)
    try:
        ready = db.q1("SELECT 1 AS ready")["ready"] == 1
    except Exception:
        ready = False
    return JSONResponse({"database": "ready" if ready else "unavailable"}, status_code=200 if ready else 503)


class NewRequest(BaseModel):
    text: str


class Clarify(BaseModel):
    answer: str


class Approve(BaseModel):
    option_id: str


def serialize(rid: str) -> dict:
    r = db.get_request_row(rid)
    if not r:
        raise HTTPException(404, detail="not found")
    c = r["constraints"]
    shortlist = []
    for row in db.shortlist_rows(rid):
        d, e = row["data"], row["data"]["expert"]
        shortlist.append({
            "expert_id": e["expert_id"], "name": e["name"], "headline": e.get("headline", ""),
            "rate_inr": e["rate_inr"], "score": d.get("score", d.get("relevance", 0)),
            "flag": d.get("flag", "unverifiable"), "outreach_state": row["outreach_state"],
            "claims": d.get("claims", []),
        })
    timeline = [{"t": t["t"], "step": t["step"], "msg": t["msg"], "source": t["source"]}
                for t in db.q("SELECT * FROM timeline WHERE request_id=? ORDER BY id", (rid,))]
    return {
        "id": r["id"], "status": r["status"], "raw_text": r["raw_text"],
        "clarification_question": r["clarification_question"],
        "constraints": {k: v for k, v in c.items() if not k.startswith("_")} if c else None,
        "shortlist": shortlist, "timeline": timeline,
        "booking": r["booking"], "escalation": r["escalation"],
    }


@app.post("/requests")
def create_request(body: NewRequest, user=Depends(session_user)):
    if CLOUD and not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("GOOGLE_CALENDAR_TOKEN_JSON")):
        raise HTTPException(503, detail="Live booking is awaiting integration setup")
    if not body.text.strip():
        raise HTTPException(400, detail="text is empty")
    rid = engine.create_request(body.text.strip(), user["email"] if user else None)
    return {"request_id": rid, "status": "INTAKE"}


@app.get("/requests/{rid}", dependencies=[Depends(request_owner)])
def get_request(rid: str):
    return serialize(rid)


@app.post("/requests/{rid}/clarify", dependencies=[Depends(request_owner)])
def clarify(rid: str, body: Clarify):
    st = engine.clarify(rid, body.answer)
    if not st:
        raise HTTPException(400, detail="request is not waiting for clarification")
    return {"status": st}


@app.post("/requests/{rid}/approve", dependencies=[Depends(request_owner)])
def approve(rid: str, body: Approve):
    st = engine.approve(rid, body.option_id)
    if not st:
        raise HTTPException(400, detail="no such pending option")
    return {"status": st}


class ChatIn(BaseModel):
    expert_id: str
    text: str


@app.post("/requests/{rid}/messages", dependencies=[Depends(request_owner)])
def send_message(rid: str, body: ChatIn):
    """Client -> booked expert, relayed on Telegram. Returns a ChatMsg. Expert replies appear in the timeline."""
    try:
        return engine.send_client_message(rid, body.expert_id, body.text)
    except LookupError:
        raise HTTPException(404, detail="not found")
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(502, detail=str(e))


@app.get("/experts", dependencies=[Depends(session_user)])
def experts():
    return {"experts": [{"expert_id": e["expert_id"], "name": e["name"], "headline": e.get("headline", ""),
                         "linkedin_url": e.get("linkedin_url", ""), "rate_inr": e["rate_inr"],
                         "simulated": bool(e.get("simulated"))} for e in adapters.load_experts()]}


@app.get("/eval/latest")
def eval_latest():
    p = EVAL if EVAL.exists() else FIX / "eval.json"
    return json.loads(p.read_text())


# ---- dev only (not part of the frontend contract) --------------------------

class DevReply(BaseModel):
    expert_id: str
    text: str


dev = APIRouter()


@dev.post("/dev/reply")
def dev_reply(body: DevReply):
    """Pretend an expert replied on Telegram. Useful when Sunil's telegram.py is not ready yet."""
    e = next((x for x in adapters.load_experts() if x["expert_id"] == body.expert_id), None)
    if not e:
        raise HTTPException(404, detail="unknown expert")
    engine.ingest_replies([adapters.sim_reply(e["telegram_chat_id"], body.text)])
    return {"ok": True}


@dev.get("/dev/status")
def dev_status():
    return {"modes": adapters.MODE, "calendar": gcal.mode(),
            "llm": "claude" if engine.llm._client else "rules",
            "outbox": db.q("SELECT * FROM outbox ORDER BY t DESC LIMIT 20")}


if not CLOUD:
    app.include_router(dev)
