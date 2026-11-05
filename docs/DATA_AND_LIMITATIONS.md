# What the data can and cannot do

Owner: Aditya. This is meant to be copied or linked into the main README.

**Crustdata is used for one job: verifying people.** It tells us where someone has worked, in what role,
and for how long. It does *not* know who has consented to take calls, who is free tomorrow evening,
or what anyone charges. We do not pretend it does.

So the data is split in two:

| Data | Source |
|---|---|
| Who is in the pool, their rate, availability and Telegram contact | Opt-in onboarding form (teammates and friends with real LinkedIn profiles) |
| Whether their claimed work history is true | Crustdata career history (Person Search, cached in `data/crustdata_cache/`, so re-verifying costs no credits) |
| A few extra profiles for variety | Real Crustdata profiles replayed by a simulator, labeled `simulated: true` in the UI |
| Planted fakes for testing (Test Profile A–D) | Real Crustdata records paired with inflated claims **written by our team**. The real people never made these claims; names and LinkedIn URLs are hidden. |

**Every claim gets one of three verdicts, with the source cited:**
- **verified**: Crustdata shows a matching role at the same company with matching dates.
- **contradicted**: Crustdata shows something different (e.g. the claim says "Warehouse Head", the record shows a 3-month internship). The expert is dropped.
- **unverifiable**: no matching record. The expert is ranked lower and flagged, not dropped.

## Who decides what

The LLM (Claude) only **parses** text: the client's request into constraints, and an expert's reply
("7:15 for 1800", "saade saat baje, 1800 chalega") into a time and a price.
**Code decides everything else**: whether the slot is inside the window, whether the price is within budget,
whether to counter-offer, who to contact next, and when to book. The LLM can never override a hard constraint.

## Robustness
- **Crash-safe:** all state lives in SQLite and is saved *before* each side effect. Kill the process anywhere and it resumes.
- **No double sends:** every Telegram message has an idempotency key in an outbox table.
- **No double invites:** the calendar event ID is a hash of request + expert + slot, so a retry returns "already exists".
- **No double bookings:** overlapping slots for the same expert are refused.
- Late replies after a booking get a polite release message. Telegram and Crustdata errors are retried, then skipped, never fatal.

## Known limitations
- One counter-offer per expert and one clarification question per request. After that the agent moves on or escalates to a human.
- Experts must have messaged the Telegram bot once (`/start`) before it can reach them.
- Verification is only as good as Crustdata's coverage: thin profiles come back *unverifiable*, not *verified*.
- Without an LLM key, a rule-based parser keeps the pipeline running, but it only handles simple English phrasing.

> Eval numbers (runs, violations, fakes caught) belong here only after the real eval in `backend/eval/` has been run.
