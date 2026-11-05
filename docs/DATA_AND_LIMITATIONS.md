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

## How experts are ranked (every rank cites its reasons)

`score = (topic relevance + experience bonus + value bonus) × verification × identity`

| Part | From | Effect |
|---|---|---|
| Topic relevance | Matched keywords in headline and claims (LLM-expanded synonyms) | 0.5 + 0.25 per match, max 1.0 |
| Experience | Longest **verified** tenure in Crustdata evidence ("14 mo") | up to +0.15 at 36 months |
| Value | How far under budget the rate is | up to +0.15 |
| Verification | Crustdata verdict | ×1 verified, ×0.6 unverifiable, ×0 contradicted |
| Identity | Telegram display name vs profile name | ×0.9 if they don't match |

The timeline shows a line like *"Ranked #1 Sunil Jakhar (score 1.1): topic match: event, fest; work history verified (14 mo); ₹1,500, 25% under budget; Telegram name matches"*.
The budget is a hard constraint: over-budget experts are ranked but never contacted, and only offered to a human in an escalation.

**First come, first served:** requests are processed oldest first. An expert who is negotiating with one request is locked;
a later request moves to its next-best expert, or waits if that expert is the only fit. Replies always go to the earliest waiting request.

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
- **Identity binding is weak.** We check that the Telegram account's display name matches the profile name, but anyone can set any display name,
  and anyone can submit someone else's LinkedIn URL. The real fix is "Sign in with LinkedIn" at onboarding, which proves the person owns the profile. We did not build it tonight.
- Verification is only as good as Crustdata's coverage: thin profiles come back *unverifiable*, not *verified*.
- Without an LLM key, a rule-based parser keeps the pipeline running, but it only handles simple English phrasing.

> Eval numbers (runs, violations, fakes caught) belong here only after the real eval in `backend/eval/` has been run.
