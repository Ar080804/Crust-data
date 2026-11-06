"""Owner: Sunil. Eval harness: 20 requests x 3 paraphrases, simulated expert replies (never real Telegram).

    python -m backend.eval.run_eval            # uses the LLM if ANTHROPIC_API_KEY is set, else the rule parser
    python -m backend.eval.run_eval --rules    # force the rule parser

Writes:
  backend/eval/latest.json  -> the Eval shape from contract/CONTRACT.md (served by GET /eval/latest)
  backend/eval/runs.json    -> every run: text, expected vs actual, booking, timeline (for debugging / README)

Safety: runs on a throwaway SQLite file, Telegram is disabled, Google Calendar is forced to sim mode.
Ground truth (budget, window) comes from the scenario, not from the parser, so parse errors show up as violations.
"""
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ---- isolate BEFORE importing the backend ----------------------------------
EVAL_DB = Path(tempfile.gettempdir()) / "sutradhar_eval.db"
for suffix in ("", "-wal", "-shm"):
    Path(str(EVAL_DB) + suffix).unlink(missing_ok=True)
os.environ["DB_PATH"] = str(EVAL_DB)
os.environ["TELEGRAM_BOT_TOKEN"] = ""

from backend.app import adapters, db, engine, gcal, llm  # noqa: E402
from backend.app.config import IST, now  # noqa: E402
from backend.integrations import crustdata, pool  # noqa: E402

adapters._tg = None                       # no real Telegram, ever
gcal._service = lambda: None              # no real calendar events
gcal.mode = lambda: "sim"
# engine.fmt_time uses "%-I", which crashes on Windows; same output, portable.
engine.fmt_time = lambda iso: datetime.fromisoformat(iso).strftime("%I:%M %p").lstrip("0")
if "--rules" in sys.argv:
    llm._client = None
PARSER = "llm" if llm._client else "rules"

OUT = Path(__file__).resolve().parent
TABLES = ["requests", "shortlist", "timeline", "replies", "outbox", "calendar_events", "kv"]


def reset_db():
    for t in TABLES:
        db.ex(f"DELETE FROM {t}")


# ---- reply policies: (expert, constraints, n = replies already sent by this expert, k = expert index) ----

def _slot(c, minutes=15):
    s = datetime.fromisoformat(c["window_start"]) + timedelta(minutes=minutes)
    return s.strftime("%I:%M").lstrip("0")


def accept(e, c, n, k):
    return f"{_slot(c)} for {min(e['rate_inr'], c['max_inr'])}"


def decline_first(e, c, n, k):
    return "sorry, busy that day" if k == 0 else accept(e, c, n, k)


def timeout_first(e, c, n, k):
    return None if k == 0 else accept(e, c, n, k)


def counter_accept(e, c, n, k):
    return f"{_slot(c)} for {c['max_inr'] + 500}" if n == 0 else "ok done"


def firm_over(e, c, n, k):
    return f"{_slot(c)} for {c['max_inr'] + 800}"


def unclear_first(e, c, n, k):
    return "around 7ish maybe" if n == 0 else f"{_slot(c, 30)} for {min(e['rate_inr'], c['max_inr'])}"


def outside_first(e, c, n, k):
    return f"10:30 for {e['rate_inr']}" if n == 0 else accept(e, c, n, k)


def all_decline(e, c, n, k):
    return "nahi, busy hoon"


def accept_no_price(e, c, n, k):
    return f"{_slot(c)} works"


def hinglish(e, c, n, k):
    return f"haan {_slot(c)} pe {min(e['rate_inr'], c['max_inr'])} chalega"


# ---- scenarios ----------------------------------------------------------------
# truth: day offset from today, window (24h), budget. expect: final status.
S = []


def sc(name, paras, truth, policy, expect, clarify=None):
    S.append({"name": name, "paraphrases": paras, "truth": truth, "policy": policy,
              "expect": expect, "clarify": clarify})


T = {"day": 1, "start": "18:00", "end": "20:00", "max_inr": 2000}
sc("warehouse_basic", [
    "Need an expert in warehouse management tomorrow 6-8 pm, budget 2000, 20 min call",
    "Looking for someone who has managed a warehouse, tomorrow 6 to 8 pm, max 2000, 20 minutes",
    "warehouse management expert for a 20 min call tomorrow 6-8 pm under ₹2,000",
], T, accept, "BOOKED")
sc("warehouse_high_budget", [
    "Need an expert in warehouse management tomorrow 6-8 pm, budget 3000, 30 min call",
    "Find me someone who has run a warehouse, tomorrow 6 to 8 pm, max 3000, 30 minutes",
    "warehouse management expert for a 30 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, accept, "BOOKED")
sc("logistics_basic", [
    "Need an expert in logistics tomorrow 7-9 pm, budget 2500, 20 min call",
    "Looking for a logistics expert, tomorrow 7 to 9 pm, max 2500, 20 minutes",
    "logistics specialist for a 20 min call tomorrow 7-9 pm under ₹2,500",
], {"day": 1, "start": "19:00", "end": "21:00", "max_inr": 2500}, accept, "BOOKED")
sc("supply_chain_basic", [
    "Need an expert in supply chain tomorrow 6-8 pm, budget 3000, 30 min call",
    "Looking for someone who has worked in supply chain, tomorrow 6 to 8 pm, max 3000, 30 minutes",
    "supply chain consultant for a 30 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, accept, "BOOKED")
sc("fulfilment_basic", [
    "Need an expert in fulfilment tomorrow 6-8 pm, budget 3000, 20 min call",
    "Looking for someone who has led fulfilment, tomorrow 6 to 8 pm, max 3000, 20 minutes",
    "fulfilment specialist for a 20 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, accept, "BOOKED")
sc("first_declines", [
    "Need an expert in warehouse management tomorrow 6-8 pm, budget 3000, 20 min call",
    "Looking for someone who has managed a warehouse, tomorrow 6 to 8 pm, max 3000, 20 minutes",
    "warehouse management expert for a 20 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, decline_first, "BOOKED")
sc("first_times_out", [
    "Need an expert in logistics tomorrow 7-9 pm, budget 3000, 20 min call",
    "Looking for a logistics expert, tomorrow 7 to 9 pm, max 3000, 20 minutes",
    "logistics specialist for a 20 min call tomorrow 7-9 pm under ₹3,000",
], {"day": 1, "start": "19:00", "end": "21:00", "max_inr": 3000}, timeout_first, "BOOKED")
sc("counter_offer_accepted", [
    "Need an expert in warehouse management tomorrow 6-8 pm, budget 2000, 20 min call",
    "Looking for someone who has managed a warehouse, tomorrow 6 to 8 pm, max 2000, 20 minutes",
    "warehouse management expert for a 20 min call tomorrow 6-8 pm under ₹2,000",
], T, counter_accept, "BOOKED")
sc("everyone_over_budget", [
    "Need an expert in supply chain tomorrow 6-8 pm, budget 3000, 30 min call",
    "Looking for someone who has worked in supply chain, tomorrow 6 to 8 pm, max 3000, 30 minutes",
    "supply chain consultant for a 30 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, firm_over, "ESCALATED")
sc("unclear_then_clear", [
    "Need an expert in warehouse management tomorrow 6-8 pm, budget 2000, 20 min call",
    "Looking for someone who has managed a warehouse, tomorrow 6 to 8 pm, max 2000, 20 minutes",
    "warehouse management expert for a 20 min call tomorrow 6-8 pm under ₹2,000",
], T, unclear_first, "BOOKED")
sc("outside_window_then_inside", [
    "Need an expert in logistics tomorrow 7-9 pm, budget 2500, 20 min call",
    "Looking for a logistics expert, tomorrow 7 to 9 pm, max 2500, 20 minutes",
    "logistics specialist for a 20 min call tomorrow 7-9 pm under ₹2,500",
], {"day": 1, "start": "19:00", "end": "21:00", "max_inr": 2500}, outside_first, "BOOKED")
sc("everyone_declines", [
    "Need an expert in warehouse management tomorrow 6-8 pm, budget 3000, 20 min call",
    "Looking for someone who has managed a warehouse, tomorrow 6 to 8 pm, max 3000, 20 minutes",
    "warehouse management expert for a 20 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, all_decline, "ESCALATED")
sc("missing_budget_clarified", [
    "Need an expert in warehouse management tomorrow 6-8 pm, 20 min call",
    "Looking for someone who has managed a warehouse, tomorrow 6 to 8 pm, 20 minutes",
    "warehouse management expert for a 20 min call tomorrow 6-8 pm",
], T, accept, "BOOKED", clarify="budget 2000")
sc("missing_time_clarified", [
    "Need an expert in logistics, budget 2500, 20 min call",
    "Looking for a logistics expert, max 2500, 20 minutes",
    "logistics specialist for a 20 min call under ₹2,500",
], {"day": 1, "start": "19:00", "end": "21:00", "max_inr": 2500}, accept, "BOOKED", clarify="tomorrow 7-9 pm")
sc("fest_sponsorship_demo", [
    "Need an expert on fest sponsorship tomorrow 6-8 pm, budget 2000, 20 min call",
    "Looking for someone who has done fest sponsorship, tomorrow 6 to 8 pm, max 2000, 20 minutes",
    "fest sponsorship expert for a 20 min call tomorrow 6-8 pm under ₹2,000",
], T, accept, "BOOKED")
sc("event_management", [
    "Need an expert on event management tomorrow 6-8 pm, budget 3000, 30 min call",
    "Looking for an event management consultant, tomorrow 6 to 8 pm, max 3000, 30 minutes",
    "event management specialist for a 30 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, accept, "BOOKED")
sc("budget_too_low", [
    "Need an expert in warehouse management tomorrow 6-8 pm, budget 500, 20 min call",
    "Looking for someone who has managed a warehouse, tomorrow 6 to 8 pm, max 500, 20 minutes",
    "warehouse management expert for a 20 min call tomorrow 6-8 pm under ₹500",
], {**T, "max_inr": 500}, accept, "ESCALATED")
sc("hinglish", [
    "kal shaam 6-8 baje warehouse expert chahiye, budget 2000, 20 min",
    "kal 6 to 8 pm ek warehouse specialist chahiye, max 2000, 20 min call",
    "warehouse expert chahiye kal shaam 6-8, budget 2k, 20 min",
], T, hinglish, "BOOKED")
sc("accept_without_price", [
    "Need an expert in fulfilment tomorrow 6-8 pm, budget 3000, 20 min call",
    "Looking for someone who has led fulfilment, tomorrow 6 to 8 pm, max 3000, 20 minutes",
    "fulfilment specialist for a 20 min call tomorrow 6-8 pm under ₹3,000",
], {**T, "max_inr": 3000}, accept_no_price, "BOOKED")
sc("evening_window", [
    "Need an expert in logistics tomorrow evening, budget 2500, 30 min call",
    "Looking for a logistics expert tomorrow evening, max 2500, 30 minutes",
    "logistics specialist for a 30 min call tomorrow evening under ₹2,500",
], {"day": 1, "start": "17:00", "end": "21:00", "max_inr": 2500}, accept, "BOOKED")
assert len(S) == 20 and all(len(s["paraphrases"]) == 3 for s in S)


# ---- runner -----------------------------------------------------------------

def run_one(text, scen, reset=True):
    if reset:
        reset_db()
    rid = engine.create_request(text)
    st = engine.run_until_settled(rid)
    if st == "NEEDS_CLARIFICATION" and scen["clarify"]:
        engine.clarify(rid, scen["clarify"])
        st = engine.run_until_settled(rid)
    experts = {e["expert_id"]: e for e in adapters.load_experts()}
    order, sent = [], defaultdict(int)
    for _ in range(60):  # up to 3 replies per expert (ask + 2 counter rounds) x ~10 experts
        if st != "NEGOTIATING":
            break
        r = db.get_request_row(rid)
        eid = r["current_expert"]
        if eid not in order:
            order.append(eid)
        e = experts[eid]
        msg = scen["policy"](e, r["constraints"], sent[eid], order.index(eid))
        if msg is None:
            db.update_request(rid, contacted_at=0)   # simulate the outreach timeout instantly
        else:
            engine.ingest_replies([adapters.sim_reply(e["telegram_chat_id"], msg)])
            sent[eid] += 1
        st = engine.run_until_settled(rid)
    r = db.get_request_row(rid)
    sl = {row["expert_id"]: row for row in db.shortlist_rows(rid)}
    return {
        "request_id": rid, "status": r["status"], "booking": r["booking"],
        "constraints": {k: v for k, v in (r["constraints"] or {}).items() if not k.startswith("_")} or None,
        "contacted": [eid for eid, row in sl.items() if row["outreach_state"] not in ("pending", "skipped")],
        "flags": {eid: row["data"].get("flag") for eid, row in sl.items()},
        "timeline": [f"{t['step']}: {t['msg']}" for t in db.q(
            "SELECT step, msg FROM timeline WHERE request_id=? ORDER BY id", (rid,))],
    }


def truth_window(t):
    d = (now() + timedelta(days=t["day"])).date().isoformat()
    return (datetime.fromisoformat(f"{d}T{t['start']}:00").replace(tzinfo=IST),
            datetime.fromisoformat(f"{d}T{t['end']}:00").replace(tzinfo=IST))


def outcome_key(res):
    b = res["booking"] or {}
    return (res["status"], b.get("expert_id"), b.get("price_inr"), b.get("start"))


def overlaps(rows):
    n = 0
    by = defaultdict(list)
    for r in rows:
        by[r["expert_id"]].append((r["start"], r["end"]))
    for slots in by.values():
        slots.sort()
        n += sum(1 for a, b in zip(slots, slots[1:]) if b[0] < a[1])
    return n


def main():
    runs, groups = [], []
    budget_v = time_v = double_b = 0
    for scen in S:
        keys = []
        for text in scen["paraphrases"]:
            res = run_one(text, scen)
            double_b += overlaps(db.q("SELECT expert_id, start, end FROM calendar_events"))
            b = res["booking"]
            if b:
                ws, we = truth_window(scen["truth"])
                if b["price_inr"] > scen["truth"]["max_inr"]:
                    budget_v += 1
                if datetime.fromisoformat(b["start"]) < ws or datetime.fromisoformat(b["end"]) > we:
                    time_v += 1
            keys.append(outcome_key(res))
            runs.append({"scenario": scen["name"], "text": text, "expected_status": scen["expect"],
                         "ok": res["status"] == scen["expect"], **res})
            print(f"{'PASS' if res['status'] == scen['expect'] else 'FAIL'} {scen['name']:<28} "
                  f"{res['status']:<20} {(b or {}).get('confirmation', '')}")
        groups.append(len(set(keys)) == 1)

    # Double-booking probe: 3 identical requests on ONE database; every expert accepts the same slot.
    reset_db()
    probe = S[0]
    for text in probe["paraphrases"]:
        run_one(text, probe, reset=False)
    probe_rows = db.q("SELECT expert_id, start, end FROM calendar_events")
    double_b += overlaps(probe_rows)
    print(f"double-booking probe: {len(probe_rows)} bookings, {overlaps(probe_rows)} overlaps")

    # Fakes: planted profiles must come back contradicted AND never be contacted in any run.
    planted = [e for e in pool.load_experts() if e.get("planted")]
    contacted = {eid for r in runs for eid in r["contacted"]}
    caught = [e["expert_id"] for e in planted
              if any(c["status"] == "contradicted" for c in crustdata.verify(e)) and e["expert_id"] not in contacted]

    ev = {"run_at": now().isoformat(timespec="seconds"), "total_runs": len(runs), "consistent": sum(groups),
          "budget_violations": budget_v, "time_violations": time_v, "double_bookings": double_b,
          "fakes_planted": len(planted), "fakes_caught": len(caught)}
    (OUT / "latest.json").write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
    passed = sum(r["ok"] for r in runs)
    (OUT / "runs.json").write_text(json.dumps({"parser": PARSER, "expected_status_matched": passed,
                                               "fakes_caught": caught, "runs": runs},
                                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(ev, indent=2))
    print(f"parser={PARSER}  expected status matched: {passed}/{len(runs)}  consistent groups: {sum(groups)}/{len(S)}")


if __name__ == "__main__":
    main()
