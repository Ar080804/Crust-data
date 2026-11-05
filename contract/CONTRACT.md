# API Contract (owner: Aditya, and only Aditya edits this file)

Need a new field? Ask Aditya. He updates this file and the fixtures, then posts in the group: "contract updated, pull".

Base URL: `http://localhost:8000`. JSON only. Times are ISO 8601 with `+05:30`. Money is an integer in INR.

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/requests` | `{"text": str}` | `{"request_id": str, "status": Status}` |
| GET | `/requests/{id}` | none | `Request` (see below). The frontend polls this every 1s. |
| POST | `/requests/{id}/clarify` | `{"answer": str}` | `{"status": Status}` |
| POST | `/requests/{id}/approve` | `{"option_id": str}` | `{"status": Status}` |
| GET | `/experts` | none | `{"experts": [Expert]}` |
| GET | `/eval/latest` | none | `Eval` |

Errors: `{"error": str}` with HTTP 400, 404 or 500.

## Status (fixed enum)
`INTAKE` → `NEEDS_CLARIFICATION` → `FINDING` → `VERIFYING` → `OUTREACH` → `NEGOTIATING` → `BOOKING` → `BOOKED`
Terminal or exception states: `ESCALATED`, `FAILED`

## Types

```
Request {
  id: str
  status: Status
  raw_text: str
  clarification_question: str | null     // set when status == NEEDS_CLARIFICATION
  constraints: Constraints | null
  shortlist: [ShortlistItem]
  timeline: [TimelineEvent]              // append-only audit log, oldest first
  booking: Booking | null
  escalation: Escalation | null
}

Constraints {
  topic: str
  duration_min: int
  window_start: str
  window_end: str
  max_inr: int
}

ShortlistItem {
  expert_id: str
  name: str
  headline: str
  rate_inr: int
  score: float                           // 0..1
  flag: "ok" | "unverifiable" | "contradicted"
  outreach_state: "pending" | "contacted" | "replied" | "declined" | "timed_out" | "booked" | "released" | "skipped"
  claims: [Claim]
}

Claim {
  text: str                              // e.g. "Logistics Manager at X, 2021–2024"
  status: "verified" | "contradicted" | "unverifiable"
  evidence: str | null                   // e.g. "Crustdata shows: Intern at X, 2022 (3 mo)"
  source: str                            // "crustdata:person_enrich" | "onboarding_form"
  fetched_at: str
}

TimelineEvent {
  t: str
  step: Status
  msg: str
  source: str                            // "llm" | "code" | "crustdata" | "telegram" | "gcal" | "human"
}

Booking {
  expert_id: str
  start: str
  end: str
  price_inr: int
  calendar_event_id: str                 // same as the idempotency key
  confirmation: str                      // "7:15 PM, ₹1,800"
}

Escalation {
  reason: str
  options: [{option_id: str, expert_id: str, slot: str, price_inr: int, summary: str}]
}

Expert {
  expert_id: str
  name: str
  headline: str
  linkedin_url: str
  rate_inr: int
  simulated: bool                        // true = replayed by the labeled simulator
}

Eval {
  run_at: str
  total_runs: int                        // e.g. 60 = 20 requests × 3 paraphrases
  consistent: int                        // paraphrase groups with identical outcomes
  budget_violations: int
  time_violations: int
  double_bookings: int
  fakes_planted: int
  fakes_caught: int
}
```

## Sunil → Aditya interface (Python, not HTTP)
Lives in `backend/integrations/`. Aditya imports these and calls them. Sunil never touches `backend/app/`.
- `crustdata.verify(expert: dict) -> list[Claim dict]`
- `telegram.send_message(chat_id: str, text: str) -> str`
- `telegram.get_replies(since_update_id: int) -> list[dict]`, where each dict is `{update_id, chat_id, text, t}`
- `pool.load_experts() -> list[dict]`

## Pool format and the integration check
- `data/experts.json` must match `contract/fixtures/pool_example.json` (a list of experts).
- Before every push, Sunil runs `python contract/check_integrations.py`, and it must print `ALL GOOD`.
- Deepak imports types from `contract/types.ts`.

## Dev-only endpoints (NOT for the frontend)
- `POST /dev/reply {"expert_id", "text"}`: pretend an expert replied on Telegram
- `GET /dev/status`: shows which parts are real or simulated (pool, verify, telegram, calendar, llm), plus the outbox

## Auth: Sign in with Google (backend ready, frontend not wired yet)
Real Google OpenID Connect. The ID token is verified on the backend (signature, audience, issuer, expiry, `email_verified`).

| Method | Path | Notes |
|---|---|---|
| GET | `/auth/google/login?redirect=<url>` | Browser navigation (not fetch). 302 to Google. `redirect` must be on `http://localhost:5173`, anything else falls back to `http://localhost:5173/`. |
| GET | `/auth/google/callback` | Google calls this. On success: 302 to `<redirect>#session=<token>`. Errors: `{"error"}` with 400/401. |
| GET | `/auth/me` | Header `Authorization: Bearer <token>` → `AuthUser`. 401 `{"error": "not signed in"}` if missing, invalid or expired (7 days). |
| POST | `/auth/logout` | Header `Authorization: Bearer <token>` → `{"ok": true}` |

```
AuthUser { email: str, name: str, picture: str, provider: "google" }
```
To wire it later: the login button does `window.location.href = "http://localhost:8000/auth/google/login?redirect=" + encodeURIComponent(location.origin + "/")`;
on load, read `#session=` from `location.hash`, store it, clear the hash, and call `/auth/me`.
Only Google accounts listed as **Test users** on the OAuth consent screen can sign in.
Existing endpoints do not require login.

## Chat with the booked expert (backend ready; frontend has `CHAT_ENABLED = MOCK`, flip it to use)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/requests/{id}/messages` | `{"expert_id": str, "text": str}` | `ChatMsg {id, expert_id, from: "me", text, t}` |

- Only when the request is `BOOKED` and `expert_id` is the booked expert. Otherwise 400 `{"error"}`
  (before booking the agent does the talking, so chat can't disturb the negotiation). Empty or >1000 chars: 400. Telegram down: 502.
- The message is relayed on Telegram. **Expert replies show up in the timeline** (see the formats below), so polling `GET /requests/{id}` is enough.

## Timeline message formats the frontend relies on (stable)
- Every message the agent sends to an expert: `source: "telegram"` (or `"simulator"` for simulated experts),
  `msg: Message to <Full Name> via Telegram: "<exact text>"`
- Every expert reply: `msg: Reply "<exact text>" from <Full Name> → <parsed JSON>` (during negotiation, `source: "llm"` or `"rules"`)
  or `Reply "<exact text>" from <Full Name> (after booking)` (`source: "telegram"`)
- Client chat messages: `source: "human"`, `msg: Client message relayed to the expert: "<text>"`
- Double quotes inside texts are replaced with `”` so `"…"` parsing never breaks.
