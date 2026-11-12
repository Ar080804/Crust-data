"""Owner: Aditya. The state machine. Code decides; the LLM only parses.
Every step reads state from SQLite and writes the next state before side effects, so killing the process
at any point and restarting resumes from the last saved step."""
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta

from . import adapters, db, gcal, llm
from .config import CLIENT_EMAIL, CLOUD, IST, OUTREACH_TIMEOUT_S, WORKER_TICK_S, now

TERMINAL = {"BOOKED", "FAILED", "ESCALATED", "NEEDS_CLARIFICATION"}

SYNONYMS = {
    "warehouse": ["warehouse", "fulfilment", "fulfillment", "logistics", "supply chain", "inventory", "3pl", "ops"],
    "logistics": ["logistics", "supply chain", "fulfilment", "fulfillment", "freight", "shipping", "3pl"],
    "hiring": ["recruit", "talent", "hr", "people"],
    "fundraising": ["founder", "venture", "investor", "vc", "cfo"],
    "marketing": ["marketing", "growth", "brand", "performance"],
    "sponsor": ["sponsor", "sponsorship", "fest", "event", "brand", "partnership"],
    "event": ["event", "fest", "organizer", "organiser", "sponsor", "management"],
    "fest": ["fest", "event", "organizer", "organiser", "sponsor", "sports"],
}


def rupees(n: int) -> str:
    return f"₹{n:,}"


def fmt_time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%I:%M %p").lstrip("0")  # portable (no %-I on Windows)


# ---- intake ----------------------------------------------------------------

def create_request(text: str, owner_email: str | None = None) -> str:
    rid = "r_" + uuid.uuid4().hex
    db.ex("INSERT INTO requests (id, status, raw_text, created_at, owner_email) VALUES (?,?,?,?,?)",
          (rid, "INTAKE", text, now().isoformat(timespec="seconds"), owner_email))
    db.log(rid, "INTAKE", f'Request received: "{text}"', "human")
    return rid


def validate(p: llm.Intake) -> tuple[dict | None, list[str], list[str]]:
    """Hard-constraint validation in code. Returns (constraints, missing, notes)."""
    missing, notes = [], []
    if not p.topic:
        missing.append("topic")
    if not p.max_inr or p.max_inr <= 0:
        missing.append("budget")
    if not p.date or not p.window_start_time:
        missing.append("time")
    if missing:
        return None, missing, notes
    duration = p.duration_min if p.duration_min and 5 <= p.duration_min <= 240 else None
    if not duration:
        duration = 30
        notes.append("Duration not given; defaulting to 30 min")
    try:
        ws = datetime.fromisoformat(f"{p.date}T{p.window_start_time}:00").replace(tzinfo=IST)
        we = (datetime.fromisoformat(f"{p.date}T{p.window_end_time}:00").replace(tzinfo=IST)
              if p.window_end_time else ws + timedelta(minutes=duration))
    except ValueError:
        return None, ["time"], notes
    if we <= ws:
        we += timedelta(hours=12) if we + timedelta(hours=12) > ws else timedelta(days=1)
    if (we - ws) < timedelta(minutes=duration):
        return None, ["time"], ["Time window is shorter than the call"]
    if we < now():
        return None, ["time"], ["Time window is in the past"]
    return {"topic": p.topic.strip(), "duration_min": duration,
            "window_start": ws.isoformat(), "window_end": we.isoformat(),
            "max_inr": int(p.max_inr), "_keywords": [k.lower() for k in p.title_keywords]}, [], notes


QUESTIONS = {"topic": "what expertise you need", "budget": "your maximum budget in ₹",
             "time": "the date and time window for the call"}


def step_intake(r):
    rid = r["id"]
    text = r["raw_text"]
    parsed, src = llm.parse_intake(text)
    db.log(rid, "INTAKE", f"Parsed: {parsed.model_dump_json(exclude={'title_keywords'})}", src)
    c, missing, notes = validate(parsed)
    for n in notes:
        db.log(rid, "INTAKE", n, "code")
    if missing:
        if r["clarified"]:
            db.update_request(rid, status="ESCALATED", escalation={
                "reason": f"Still missing after one clarification: {', '.join(missing)}", "options": []})
            db.log(rid, "ESCALATED", "Constraints still incomplete after asking once; needs a human", "code")
            return
        qtext = "Could you tell me " + " and ".join(QUESTIONS[m] for m in missing) + "?"
        db.update_request(rid, status="NEEDS_CLARIFICATION", clarification_question=qtext)
        db.log(rid, "NEEDS_CLARIFICATION", f"Missing: {', '.join(missing)}. Asked once.", "code")
        return
    db.update_request(rid, status="FINDING", constraints=c)
    db.log(rid, "INTAKE", f"Constraints validated: {c['topic']}, {c['duration_min']} min, "
           f"{fmt_time(c['window_start'])}–{fmt_time(c['window_end'])} IST, max {rupees(c['max_inr'])}", "code")


def clarify(rid: str, answer: str):
    r = db.get_request_row(rid)
    if not r or r["status"] != "NEEDS_CLARIFICATION":
        return None
    db.update_request(rid, raw_text=r["raw_text"] + "\nClarification: " + answer, clarified=1,
                      status="INTAKE", clarification_question=None)
    db.log(rid, "INTAKE", f'Clarification: "{answer}"', "human")
    return "INTAKE"


# ---- find + verify ---------------------------------------------------------

def _norm_url(u: str) -> str:
    return re.sub(r"[?#].*$", "", (u or "").lower()).rstrip("/").replace("http://", "https://").replace("://www.", "://")


def _keywords(c) -> list[str]:
    kws = set(c.get("_keywords", []))
    for w in re.findall(r"[a-z0-9]+", c["topic"].lower()):
        if len(w) > 2:
            kws.add(w)
        for root, syns in SYNONYMS.items():
            if w.startswith(root[:5]):
                kws.update(syns)
    kws -= {"management", "manage", "managed", "expert", "someone", "call", "with", "and", "the", "for",
            "wale", "wala", "kisi", "baat", "person"}
    return sorted(kws)


def _available(e, c) -> str | None:
    """Earliest start inside the window where the expert is free for the whole call, else None."""
    ws, we = datetime.fromisoformat(c["window_start"]), datetime.fromisoformat(c["window_end"])
    dur = timedelta(minutes=c["duration_min"])
    slots = e.get("availability") or []
    if not slots and not CLOUD:
        slots = [{"start": c["window_start"], "end": c["window_end"]}]
    for a in slots:
        s = max(ws, datetime.fromisoformat(a["start"]))
        if s + dur <= min(we, datetime.fromisoformat(a["end"])):
            return s.isoformat()
    return None


def step_find(r):
    rid, c = r["id"], r["constraints"]
    kws = _keywords(c)
    db.log(rid, "FINDING", "Expanded search terms: " + ", ".join(kws), "code")
    experts = adapters.load_experts()
    merged: dict[str, dict] = {}
    for e in experts:
        key = _norm_url(e.get("linkedin_url")) or e["expert_id"]
        if key in merged:
            merged[key]["claims"] = sorted(set(merged[key].get("claims", [])) | set(e.get("claims", [])))
            db.log(rid, "FINDING", f"Merged duplicate profile {e['expert_id']} into {merged[key]['expert_id']}", "code")
        else:
            merged[key] = dict(e)
    cands, unavailable = [], 0
    for e in merged.values():
        text = (e.get("headline", "") + " " + " ".join(e.get("claims", []))).lower()
        hits = [k for k in kws if k in text]
        if not hits:
            continue
        if not _available(e, c):
            unavailable += 1
            db.log(rid, "FINDING", f"{e['name']} matches but is not available in the window", "code")
            continue
        cands.append((min(1.0, 0.5 + 0.25 * len(hits)), e))
    cands.sort(key=lambda x: (-x[0], x[1]["expert_id"]))
    cands = cands[:10]  # wide enough that planted fakes get verified (and caught), not silently cut
    if not cands:
        # Say exactly why, so the human knows what to change (time window vs topic).
        if unavailable:
            reason = (f"No expert matching '{c['topic']}' is free {_window_desc(c)} "
                      f"({unavailable} match the topic but are busy then). Try another time window.")
        else:
            reason = f"No expert in the pool matches '{c['topic']}'. Try a broader topic."
        db.update_request(rid, status="ESCALATED", escalation={"reason": reason, "options": []})
        db.log(rid, "ESCALATED", reason, "code")
        return
    with db.tx() as con:
        con.execute("DELETE FROM shortlist WHERE request_id=?", (rid,))
        for i, (score, e) in enumerate(cands):
            con.execute("INSERT INTO shortlist (request_id, expert_id, ord, data, outreach_state) VALUES (?,?,?,?,?)",
                        (rid, e["expert_id"], i, db.j({"expert": e, "relevance": score}), "pending"))
        con.execute("UPDATE requests SET status='VERIFYING' WHERE id=?", (rid,))
    db.log(rid, "FINDING", f"{len(cands)} candidates from a pool of {len(experts)} (source: {adapters.MODE['pool']} pool)", "code")


def step_verify(r):
    rid = r["id"]
    rows = db.shortlist_rows(rid)
    scored = []
    for row in rows:
        d = row["data"]
        if "claims" in d:  # already verified before a crash
            scored.append((d["score"], row["expert_id"]))
            continue
        e = d["expert"]
        claims, src = adapters.verify(e)
        st = {c["status"] for c in claims}
        if "contradicted" in st:
            flag, factor = "contradicted", 0.0
        elif "verified" in st:
            flag, factor = "ok", 1.0
        else:
            flag, factor = "unverifiable", 0.6
        d.update(claims=claims, flag=flag, score=round(d["relevance"] * factor, 2))
        state = "skipped" if flag == "contradicted" else "pending"
        db.ex("UPDATE shortlist SET data=?, outreach_state=? WHERE request_id=? AND expert_id=?",
              (db.j(d), state, rid, row["expert_id"]))
        if flag == "contradicted":
            bad = next(c for c in claims if c["status"] == "contradicted")
            db.log(rid, "VERIFYING", f"{e['name']} dropped: claim \"{bad['text']}\" contradicted. {bad['evidence']}", src)
        elif flag == "unverifiable":
            db.log(rid, "VERIFYING", f"{e['name']}: claims unverifiable, ranked lower and flagged", src)
        else:
            db.log(rid, "VERIFYING", f"{e['name']}: work history verified", src)
        scored.append((d["score"], row["expert_id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    for i, (_, eid) in enumerate(scored):
        db.ex("UPDATE shortlist SET ord=? WHERE request_id=? AND expert_id=?", (i, rid, eid))
    db.update_request(rid, status="OUTREACH")


# ---- outreach + negotiate --------------------------------------------------

def _quote(text: str) -> str:
    return (text or "").replace('"', "”")  # keep the UI's "..." parsing intact


def _tell(rid: str, step: str, e: dict, key: str, text: str) -> bool:
    """Send one Telegram message to an expert (idempotent) and log its exact text.
    Timeline format, read by the frontend chat panel: Message to <Name> via Telegram: "<text>" """
    ok = adapters.send_once(key, e["telegram_chat_id"], text)
    if ok:
        src = "telegram" if adapters.MODE["telegram"] == "real" else "simulator"
        db.log(rid, step, f'Message to {e["name"]} via Telegram: "{_quote(text)}"', src)
    return ok


def _window_desc(c):
    d = datetime.fromisoformat(c["window_start"])
    return f"{d.strftime('%a %d %b')}, {fmt_time(c['window_start'])}–{fmt_time(c['window_end'])} IST"


def step_outreach(r):
    rid, c = r["id"], r["constraints"]
    waiting_for_expert = False
    for row in db.shortlist_rows(rid):
        if row["outreach_state"] != "pending":
            continue
        e = row["data"]["expert"]
        if e["rate_inr"] > c["max_inr"]:
            db.set_outreach(rid, e["expert_id"], "skipped",
                            last_ask={"slot": _available(e, c), "price": e["rate_inr"]})
            db.log(rid, "OUTREACH", f"{e['name']} skipped: rate {rupees(e['rate_inr'])} > budget {rupees(c['max_inr'])}", "code")
            continue
        if not e.get("telegram_chat_id"):
            db.set_outreach(rid, e["expert_id"], "skipped")
            db.log(rid, "OUTREACH", f"{e['name']} skipped: no contact channel", "code")
            continue
        if db.q1("SELECT 1 AS active FROM requests WHERE current_expert=? AND id<>? "
                 "AND status IN ('NEGOTIATING','BOOKING') LIMIT 1", (e["expert_id"], rid)):
            # An unthreaded Telegram reply can belong to only one negotiation.
            waiting_for_expert = True
            continue
        first = e["name"].split()[0]
        msg = (f"Namaste {first}! Sutradhar here. A client wants a {c['duration_min']}-min call on {c['topic']}, "
               f"{_window_desc(c)}. Your listed rate is {rupees(e['rate_inr'])}. Are you free? "
               f"Reply with a time and price, e.g. \"7:15 for {e['rate_inr']}\", or \"no\".")
        db.set_outreach(rid, e["expert_id"], "contacted")
        db.update_request(rid, status="NEGOTIATING", current_expert=e["expert_id"], contacted_at=time.time(),
                          offer=None, counter_sent=0, asked_once=0)
        if _tell(rid, "OUTREACH", e, f"outreach:{rid}:{e['expert_id']}", msg):
            db.log(rid, "OUTREACH", f"Waiting up to {OUTREACH_TIMEOUT_S}s for {e['name']} to reply", "code")
        else:
            db.update_request(rid, contacted_at=0)  # forces an immediate timeout -> next expert
            db.log(rid, "OUTREACH", f"Could not reach {e['name']} on Telegram after 3 tries; moving on", "telegram")
        return
    if not waiting_for_expert:
        escalate(rid, c, "No verified expert accepted within budget and window")


def escalate(rid, c, reason):
    opts = []
    for row in db.shortlist_rows(rid):
        ask = row["last_ask"]
        d = row["data"]
        if ask and ask.get("slot") and ask.get("price") and d.get("flag") != "contradicted":
            e = d["expert"]
            if _slot_taken(e["expert_id"], ask["slot"], c):
                continue  # never offer a human a slot we already know is unavailable
            opts.append({"option_id": f"o_{e['expert_id']}", "expert_id": e["expert_id"], "slot": ask["slot"],
                         "price_inr": ask["price"],
                         "summary": f"{e['name']}, {rupees(ask['price'])} at {fmt_time(ask['slot'])}, approve?"})
    opts.sort(key=lambda o: (o["price_inr"] - c["max_inr"], o["slot"]))
    db.update_request(rid, status="ESCALATED", escalation={"reason": reason, "options": opts[:3]}, current_expert=None)
    db.log(rid, "ESCALATED", f"{reason}. {len(opts[:3])} closest option(s) sent to a human.", "code")


def _slot_taken(expert_id: str, start: str, c) -> bool:
    end = (datetime.fromisoformat(start) + timedelta(minutes=c["duration_min"])).isoformat()
    return gcal.expert_conflict(expert_id, start, end, "") or gcal.calendar_busy(start, end)


def _resolve_slot(hhmm: str | None, c) -> str | None:
    if not hhmm or not re.match(r"^\d{1,2}:\d{2}$", hhmm):
        return None
    ws, we = datetime.fromisoformat(c["window_start"]), datetime.fromisoformat(c["window_end"])
    h, m = map(int, hhmm.split(":"))
    dur = timedelta(minutes=c["duration_min"])
    for hh in (h, h + 12):
        if hh > 23:
            continue
        s = ws.replace(hour=hh, minute=m)
        if ws <= s and s + dur <= we:
            return s.isoformat()
    return None


def _next_expert(rid, eid, state, msg, source="code"):
    db.set_outreach(rid, eid, state)
    db.update_request(rid, status="OUTREACH", current_expert=None)
    db.log(rid, "NEGOTIATING", msg, source)


def step_negotiate(r):
    rid, c, eid = r["id"], r["constraints"], r["current_expert"]
    row = next(x for x in db.shortlist_rows(rid) if x["expert_id"] == eid)
    e = row["data"]["expert"]
    replies = db.q("SELECT * FROM replies WHERE request_id=? AND expert_id=? AND processed=0 ORDER BY update_id",
                   (rid, eid))
    if not replies:
        if time.time() - (r["contacted_at"] or 0) > OUTREACH_TIMEOUT_S:
            _next_expert(rid, eid, "timed_out", f"{e['name']} did not reply in {OUTREACH_TIMEOUT_S}s; moving on")
        return
    rep = replies[-1]
    db.ex("UPDATE replies SET processed=1 WHERE request_id=? AND expert_id=? AND update_id<=?",
          (rid, eid, rep["update_id"]))
    db.set_outreach(rid, eid, "replied")
    p, src = llm.parse_reply(rep["text"], _window_desc(c))
    db.log(rid, "NEGOTIATING", f'Reply "{_quote(rep["text"])}" from {e["name"]} → {p.model_dump_json()}', src)
    offer = r["offer"] or {}
    chat = e["telegram_chat_id"]
    n = int(rep["update_id"])

    if p.intent == "decline":
        return _next_expert(rid, eid, "declined", f"{e['name']} declined")
    if p.intent == "unclear" and not p.slot_time and not p.price_inr:
        return _ask_once(r, e, f"Sorry, could you confirm an exact time in {_window_desc(c)}? e.g. \"19:15 for {e['rate_inr']}\"", n)

    slot = _resolve_slot(p.slot_time, c) if p.slot_time else offer.get("slot")
    price = p.price_inr or (offer.get("price") if p.intent == "accept" else None) or e["rate_inr"]
    if p.slot_time and not slot:
        return _ask_once(r, e, f"The client's window is {_window_desc(c)}. Could you do a time inside it?", n)
    if not slot:
        return _ask_once(r, e, f"Great! What exact time works in {_window_desc(c)}?", n)
    db.set_outreach(rid, eid, "replied", last_ask={"slot": slot, "price": price})
    asked = offer.get("asked") or (price if price > c["max_inr"] else None)  # the expert's first over-budget ask
    if price > c["max_inr"]:
        rounds = int(r["counter_sent"] or 0)
        if rounds < MAX_COUNTER_ROUNDS:
            counter = _counter_amount(c["max_inr"], rounds)
            text, how = _counter_text(e, slot, counter, price, rounds + 1, c)
            db.update_request(rid, counter_sent=rounds + 1, offer={"slot": slot, "price": counter, "asked": asked},
                              contacted_at=time.time())
            _tell(rid, "NEGOTIATING", e, f"counter{rounds + 1}:{rid}:{eid}", text)
            db.log(rid, "NEGOTIATING", f"Round {rounds + 1}/{MAX_COUNTER_ROUNDS}: {e['name']} asked {rupees(price)} > budget "
                   f"{rupees(c['max_inr'])}; agent offered {rupees(counter)} ({how})", "code")
            return
        return _next_expert(rid, eid, "declined",
                            f"{e['name']} still over budget ({rupees(price)}) after {MAX_COUNTER_ROUNDS} counter rounds; moving on")
    db.update_request(rid, status="BOOKING", offer={"slot": slot, "price": price, "asked": asked})
    db.log(rid, "NEGOTIATING", f"{fmt_time(slot)} is inside the window and {rupees(price)} ≤ {rupees(c['max_inr'])}: accepted", "code")


MAX_COUNTER_ROUNDS = 2


def _counter_amount(budget: int, rounds_done: int) -> int:
    """Round 1 opens 10% under budget (rounded down to ₹50); round 2 is the full budget. Never above budget."""
    if rounds_done == 0:
        return max(50, int(budget * 0.9) // 50 * 50)
    return budget


def _counter_text(e: dict, slot: str, counter: int, asked: int, round_no: int, c: dict) -> tuple[str, str]:
    """LLM drafts the message; code checks it. Every rupee amount in it must equal our offer (which is ≤ budget)."""
    draft = llm.draft_counter(e["name"].split()[0], rupees(asked), rupees(counter), fmt_time(slot), round_no, c["topic"])
    if draft:
        no_times = re.sub(r"\b\d{1,2}[:.]\d{2}\b", " ", draft)
        amounts = {int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{2,}", no_times)}
        if amounts == {counter} and counter <= c["max_inr"] and len(draft) <= 400:
            return draft, "LLM-drafted, code-checked"
        print("Counter draft rejected by code check:", amounts, draft)
    first = e["name"].split()[0]
    if round_no == 1:
        text = (f"Thanks {first}! Could you do {fmt_time(slot)} for {rupees(counter)}? "
                f"The client is ready to book right now.")
    else:
        text = f"{rupees(counter)} is the client's final offer for {fmt_time(slot)}. Shall I lock it in?"
    return text, "template"


def _ask_once(r, e, text, n):
    rid, eid = r["id"], e["expert_id"]
    if r["asked_once"]:
        return _next_expert(rid, eid, "declined", f"{e['name']}'s reply still unclear after asking once; moving on")
    db.update_request(rid, asked_once=1, contacted_at=time.time())
    _tell(rid, "NEGOTIATING", e, f"ask:{rid}:{eid}", text)
    db.log(rid, "NEGOTIATING", f"Reply ambiguous; asked {e['name']} once to clarify", "code")


# ---- booking ---------------------------------------------------------------

def step_book(r):
    rid, c, eid, offer = r["id"], r["constraints"], r["current_expert"], r["offer"]
    row = next(x for x in db.shortlist_rows(rid) if x["expert_id"] == eid)
    e = row["data"]["expert"]
    start = offer["slot"]
    end = (datetime.fromisoformat(start) + timedelta(minutes=c["duration_min"])).isoformat()
    eid_cal = gcal.event_id(rid, eid, start)
    if gcal.expert_conflict(eid, start, end, eid_cal) or (gcal.calendar_busy(start, end) and not gcal.event_exists(eid_cal)):
        db.log(rid, "BOOKING", f"Calendar conflict at {fmt_time(start)}; not double-booking", "gcal")
        if not r["asked_once"] and e.get("telegram_chat_id"):
            # Like a human coordinator: ask the same expert for another time once before moving on.
            db.update_request(rid, status="NEGOTIATING", offer={"price": offer["price"]}, asked_once=1,
                              contacted_at=time.time())
            _tell(rid, "NEGOTIATING", e, f"slot_taken:{rid}:{eid}",
                  f"Sorry, {fmt_time(start)} is no longer free. Could you do another time in "
                  f"{_window_desc(c)}? e.g. \"19:40 for {offer['price']}\"")
            db.log(rid, "NEGOTIATING", f"Asked {e['name']} once for another time", "code")
            return
        return _next_expert(rid, eid, "declined", f"Slot unavailable for {e['name']}; trying next expert")
    status = gcal.book(eid_cal, e, start, end,
                       summary=f"Sutradhar: {c['topic']} call with {e['name']}",
                       description=f"{c['duration_min']}-min expert call. Fee {rupees(offer['price'])}. Request {rid}.",
                       attendees=[e.get("email", ""), r.get("owner_email") or CLIENT_EMAIL])
    conf = f"{fmt_time(start)}, {rupees(offer['price'])}"
    booking = {"expert_id": eid, "start": start, "end": end, "price_inr": offer["price"],
               "calendar_event_id": eid_cal, "confirmation": conf}
    db.update_request(rid, status="BOOKED", booking=booking)
    db.set_outreach(rid, eid, "booked")
    db.log(rid, "BOOKING", f"Calendar event {eid_cal[:10]}… {status} ({gcal.mode()}); invites sent to both sides", "gcal")
    _tell(rid, "BOOKED", e, f"confirm:{rid}:{eid}", f"Confirmed: {conf}. Calendar invite sent. Thank you!")
    db.log(rid, "BOOKED", f"Confirmed: {conf}", "code")
    asked = offer.get("asked")
    if asked and asked > offer["price"]:
        # Format read by the frontend badge: ^Savings: listed=<int> booked=<int>  (listed = the expert's first ask)
        db.log(rid, "BOOKED", f"Savings: listed={asked} booked={offer['price']} saved={asked - offer['price']} "
               f"(expert first asked {rupees(asked)}; negotiated by agent)", "code")


def approve(rid: str, option_id: str):
    r = db.get_request_row(rid)
    if not r or r["status"] != "ESCALATED" or not r["escalation"]:
        return None
    opt = next((o for o in r["escalation"]["options"] if o["option_id"] == option_id), None)
    if not opt:
        return None
    db.update_request(rid, status="BOOKING", current_expert=opt["expert_id"],
                      offer={"slot": opt["slot"], "price": opt["price_inr"]})
    db.log(rid, "BOOKING", f"Human approved: {opt['summary'].removesuffix(', approve?')}", "human")
    return "BOOKING"


# ---- client <-> booked expert chat ------------------------------------------

def send_client_message(rid: str, expert_id: str, text: str) -> dict:
    """Relay a client's message to the booked expert. Only after booking, so chat can't disturb negotiation."""
    r = db.get_request_row(rid)
    if not r:
        raise LookupError("not found")
    text = (text or "").strip()
    if not text:
        raise ValueError("message is empty")
    if len(text) > 1000:
        raise ValueError("message is too long (max 1000 characters)")
    if r["status"] != "BOOKED" or not r["booking"]:
        raise ValueError("chat opens once the call is booked; until then the agent talks to experts")
    if r["booking"]["expert_id"] != expert_id:
        raise ValueError("you can only message the expert you booked")
    row = next(x for x in db.shortlist_rows(rid) if x["expert_id"] == expert_id)
    e = row["data"]["expert"]
    mid = "m_" + uuid.uuid4().hex[:10]
    c = r["constraints"]
    sent = adapters.send_once(f"chat:{rid}:{mid}", e["telegram_chat_id"],
                              f"Message from your client about the {c['topic']} call "
                              f"({r['booking']['confirmation']}):\n{text}\n\n(Just reply here; we'll pass it on.)")
    if not sent:
        raise RuntimeError("could not reach the expert on Telegram; try again")
    # source "human": the client wrote it (keeps it out of the agent's message bubbles)
    db.log(rid, "BOOKED", f'Client message relayed to the expert: "{_quote(text)}"', "human")
    return {"id": mid, "expert_id": expert_id, "from": "me", "text": text, "t": now().isoformat(timespec="seconds")}


# ---- replies router --------------------------------------------------------

def ingest_replies(replies: list[dict]):
    """Attach each reply to the request that is waiting on that expert; release late repliers politely."""
    if not replies:
        return
    by_chat = {str(e.get("telegram_chat_id")): e for e in adapters.load_experts()}
    for rep in replies:
        e = by_chat.get(str(rep["chat_id"]))
        if not e:
            continue
        eid = e["expert_id"]
        active = db.q1("SELECT id FROM requests WHERE status='NEGOTIATING' AND current_expert=? "
                       "ORDER BY created_at DESC LIMIT 1", (eid,))
        rid = active["id"] if active else None
        inserted = db.ex("INSERT INTO replies (update_id, chat_id, text, t, expert_id, request_id) "
                         "VALUES (?,?,?,?,?,?) ON CONFLICT(update_id) DO NOTHING",
                         (rep["update_id"], str(rep["chat_id"]), rep["text"], rep["t"], eid, rid))
        if not inserted:
            continue
        if rid:
            continue
        booked = db.q1("SELECT r.id FROM requests r JOIN shortlist s ON s.request_id=r.id "
                       "WHERE r.status='BOOKED' AND s.expert_id=? AND s.outreach_state='booked' "
                       "ORDER BY r.created_at DESC LIMIT 1", (eid,))
        if booked:
            db.ex("UPDATE replies SET request_id=?, processed=1 WHERE update_id=?", (booked["id"], rep["update_id"]))
            src = "simulator" if str(rep["chat_id"]).startswith("sim-") else "telegram"
            db.log(booked["id"], "BOOKED", f'Reply "{_quote(rep["text"])}" from {e["name"]} (after booking)', src)
            continue
        late = db.q1("SELECT s.request_id, r.status FROM shortlist s JOIN requests r ON r.id=s.request_id "
                     "WHERE s.expert_id=? AND s.outreach_state IN ('timed_out','declined','contacted','replied') "
                     "AND r.status IN ('BOOKED','ESCALATED','FAILED') ORDER BY r.created_at DESC LIMIT 1", (eid,))
        if late:
            lrid = late["request_id"]
            db.set_outreach(lrid, eid, "released")
            if late["status"] == "BOOKED":
                text = ("Thank you for replying! This call has already been booked with someone else. "
                        "We'll reach out for the next one.")
            else:
                text = ("Thank you for replying! We had to move this request forward without you, "
                        "since we didn't hear back in time. We'll reach out for the next one.")
            _tell(lrid, late["status"], e, f"release:{lrid}:{eid}", text)
            db.log(lrid, late["status"], f"Late reply from {e['name']}; released politely", "code")


# ---- worker ----------------------------------------------------------------

STEPS = {"INTAKE": step_intake, "FINDING": step_find, "VERIFYING": step_verify, "OUTREACH": step_outreach,
         "NEGOTIATING": step_negotiate, "BOOKING": step_book}


def tick():
    replies = adapters.poll_replies()
    ingest_replies(replies)
    if replies:
        db.kv_set("tg_last_update_id", max(r["update_id"] for r in replies))
    for r in db.q("SELECT id FROM requests WHERE status IN (%s)" % ",".join("?" * len(STEPS)), tuple(STEPS)):
        row = db.get_request_row(r["id"])
        try:
            STEPS[row["status"]](row)
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            db.log(row["id"], row["status"], f"Step error: {type(ex).__name__}; will retry", "code")


def run_until_settled(rid: str, max_ticks: int = 50):
    """Used by tests and the eval: run steps synchronously until the request waits or finishes."""
    for _ in range(max_ticks):
        st = db.get_request_row(rid)["status"]
        if st in TERMINAL:
            return st
        before = st
        tick()
        after = db.get_request_row(rid)
        if after["status"] == before == "NEGOTIATING" and not db.q(
                "SELECT 1 FROM replies WHERE request_id=? AND processed=0", (rid,)):
            return "NEGOTIATING"
    return db.get_request_row(rid)["status"]


_started = False


def start_worker():
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            time.sleep(WORKER_TICK_S)

    threading.Thread(target=loop, daemon=True, name="sutradhar-worker").start()
