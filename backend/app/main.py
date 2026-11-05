"""Owner: Aditya. Starts as a stub that serves contract fixtures, so the frontend can hit real URLs right away.
Replace each handler with real logic one at a time. The response shapes must stay identical to contract/CONTRACT.md."""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

FIX = Path(__file__).resolve().parents[2] / "contract" / "fixtures"
app = FastAPI(title="Sutradhar")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def fixture(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


class NewRequest(BaseModel):
    text: str


class Clarify(BaseModel):
    answer: str


class Approve(BaseModel):
    option_id: str


@app.post("/requests")
def create_request(body: NewRequest):
    return {"request_id": "r_demo", "status": "INTAKE"}  # TODO(Aditya): real state machine


@app.get("/requests/{rid}")
def get_request(rid: str):
    if rid == "r_clarify":
        return fixture("request_clarify")
    if rid == "r_demo":
        return fixture("request_booked")
    raise HTTPException(404, detail="not found")


@app.post("/requests/{rid}/clarify")
def clarify(rid: str, body: Clarify):
    return {"status": "FINDING"}


@app.post("/requests/{rid}/approve")
def approve(rid: str, body: Approve):
    return {"status": "BOOKING"}


@app.get("/experts")
def experts():
    return fixture("experts")


@app.get("/eval/latest")
def eval_latest():
    return fixture("eval")
