"""Owner: Aditya. Calendar booking with an idempotency key.
The event id is deterministic (hash of request+expert+slot), so inserting twice returns 409 and we treat that as success.
If credentials.json/token.json are missing, a local simulated calendar (SQLite) is used.

One-time setup for real Google Calendar:  python -m backend.app.gcal auth"""
import hashlib
import json
import os
from functools import lru_cache
import sys

from . import db
from .config import CLOUD, GOOGLE_CALENDAR_ID, ROOT

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDS = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"


def event_id(request_id: str, expert_id: str, start_iso: str) -> str:
    # Google allows base32hex chars (0-9, a-v); hex is a subset.
    return hashlib.sha1(f"{request_id}|{expert_id}|{start_iso}".encode()).hexdigest()


@lru_cache(maxsize=1)
def _credentials():
    from google.oauth2.credentials import Credentials

    raw = os.getenv("GOOGLE_CALENDAR_TOKEN_JSON")
    if raw:
        return Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not CLOUD and TOKEN.is_file():
        return Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    return None


def _service():
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _credentials()
    if creds is None:
        return None
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        if not CLOUD and not os.getenv("GOOGLE_CALENDAR_TOKEN_JSON"):
            TOKEN.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def mode() -> str:
    return "google" if _credentials() is not None else "sim"


def expert_conflict(expert_id: str, start: str, end: str, eid: str) -> bool:
    """True if this expert already has a different booking overlapping the slot (prevents double-booking)."""
    rows = db.q('SELECT 1 FROM calendar_events WHERE expert_id=? AND event_id!=? AND start<? AND "end">?',
                (expert_id, eid, end, start))
    return bool(rows)


def event_exists(eid: str) -> bool:
    if db.q1("SELECT event_id FROM calendar_events WHERE event_id=?", (eid,)):
        return True
    svc = _service()
    if svc is None:
        return False
    from googleapiclient.errors import HttpError
    try:
        event = svc.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=eid).execute()
    except HttpError as exc:
        if exc.resp.status in (404, 410):
            return False
        raise
    return event.get("status") != "cancelled"


def calendar_busy(start: str, end: str) -> bool:
    svc = _service()
    if not svc:
        return False
    fb = svc.freebusy().query(body={"timeMin": start, "timeMax": end,
                                    "items": [{"id": GOOGLE_CALENDAR_ID}]}).execute()
    return bool(fb["calendars"][GOOGLE_CALENDAR_ID]["busy"])


def book(eid: str, expert: dict, start: str, end: str, summary: str, description: str, attendees: list[str]) -> str:
    """Create the event (idempotent). Returns 'created' or 'already_exists'."""
    existing = db.q1("SELECT event_id FROM calendar_events WHERE event_id=?", (eid,))
    svc = _service()
    status = "created"
    if svc:
        from googleapiclient.errors import HttpError

        body = {"id": eid, "summary": summary, "description": description,
                "start": {"dateTime": start}, "end": {"dateTime": end},
                "attendees": [{"email": a} for a in attendees if a]}
        try:
            svc.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body, sendUpdates="all").execute()
        except HttpError as e:
            if e.resp.status == 409:
                status = "already_exists"
            else:
                raise
    elif existing:
        status = "already_exists"
    if not existing:
        db.ex('INSERT INTO calendar_events (event_id, expert_id, start, "end", data) VALUES (?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING',
              (eid, expert["expert_id"], start, end, json.dumps({"summary": summary, "attendees": attendees})))
    return status


if __name__ == "__main__" and sys.argv[1:] == ["auth"]:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)
    TOKEN.write_text(flow.run_local_server(port=0).to_json())
    print("Saved", TOKEN)
