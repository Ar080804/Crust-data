# API Contract (owner: Aditya, and only Aditya edits this file)

Need a new field? Ask Aditya. He updates this file and the fixtures, then posts in the group: "contract updated, pull".

Base URL: `http://localhost:8000`. JSON only. Times are ISO 8601 with `+05:30`. Money is an integer in INR.

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/requests` | `{"text": str}` (optional header `X-User-Email`) | `{"request_id": str, "status": Status}` |
| GET | `/requests?limit=20` | none (optional header `X-User-Email`) | `{"requests": [Request]}`, newest first. With the header: only that user's requests. Without it: everyone's. `limit` is 1–100. |
| GET | `/requests/{id}` | none | `Request` (see below). The frontend polls this every 1s. |
| POST | `/requests/{id}/clarify` | `{"answer": str}` | `{"status": Status}` |
| POST | `/requests/{id}/approve` | `{"option_id": str}` | `{"status": Status}` |
| POST | `/requests/{id}/cancel` | none | `{"status": "CANCELLED"}`. 400 if already BOOKING/BOOKED/CANCELLED/FAILED. Any expert we were waiting on gets a Telegram message. |
| GET | `/experts` | none | `{"experts": [Expert]}` |
| GET | `/eval/latest` | none | `Eval` |

Errors: `{"error": str}` with HTTP 400, 404 or 500.

## Status (fixed enum)
`INTAKE` → `NEEDS_CLARIFICATION` → `FINDING` → `VERIFYING` → `OUTREACH` → `NEGOTIATING` → `BOOKING` → `BOOKED`
Terminal or exception states: `ESCALATED`, `FAILED`, `CANCELLED`

## Types

```
Request {
  id: str
  status: Status
  raw_text: str
  created_at: str                        // ISO 8601 with +05:30, e.g. "2026-11-06T01:02:00.000+05:30"
  clarification_question: str | null     // set when status == NEEDS_CLARIFICATION
  constraints: Constraints | null
  shortlist: [ShortlistItem]
  timeline: [TimelineEvent]              // append-only audit log, oldest first
  booking: Booking | null
  escalation: Escalation | null         // escalation.options can be [] (show only the reason)
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
  source: str                            // "crustdata:person_search" | "crustdata:person_enrich" | "telegram:getChat" | ...
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

## Changelog
- **v2 (02:55):** `created_at` on Request; `GET /requests` (+ `X-User-Email`); `POST /requests/{id}/cancel`; status `CANCELLED`;
  claims may include an identity claim with `source: "telegram:getChat"` (Telegram name vs profile name);
  the timeline now has a "Ranked #n … (score x): reasons" line per expert. Fixture: `requests_list.json`.
