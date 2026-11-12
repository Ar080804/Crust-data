"""Owner: Sunil. Checks the negotiator agent in 3 scenarios on a throwaway DB (no real Telegram, Calendar in sim).

    python -m backend.eval.negotiation_check
    python -m backend.eval.negotiation_check --rules      # force the rule parser

Scenarios (every contacted expert follows the same script):
  accepts   : asks above budget, then accepts the agent's counter  -> BOOKED at <= budget, "Savings" logged
  declines  : asks above budget, then refuses the counter           -> that expert declined, never booked above budget
  holds_out : keeps asking above budget                             -> at most 2 counters per expert, then ESCALATED
Hard rules checked in every scenario: no booking above max_inr, no booking outside the window, <= 2 counters per expert.
"""
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

EVAL_DB = Path(tempfile.gettempdir()) / "sutradhar_negotiation.db"
for suffix in ("", "-wal", "-shm"):
    Path(str(EVAL_DB) + suffix).unlink(missing_ok=True)
os.environ["DATABASE_URL"] = ""
os.environ["APP_URL"] = ""
os.environ["VERCEL"] = ""
os.environ["DB_PATH"] = str(EVAL_DB)
os.environ["TELEGRAM_BOT_TOKEN"] = ""

from backend.app import adapters, db, engine, gcal, llm  # noqa: E402

adapters._tg = None
gcal._service = lambda: None
gcal.mode = lambda: "sim"
if "--rules" in sys.argv:
    llm._client = None

REQUEST = "Need an expert on fest sponsorship tomorrow 6-8 pm, budget 2000, 20 min call"
TABLES = ["requests", "shortlist", "timeline", "replies", "outbox", "calendar_events", "kv"]


def _slot(c):
    return datetime.fromisoformat(c["window_start"]).replace(minute=15).strftime("%I:%M").lstrip("0")


def accepts(e, c, n):
    return f"{_slot(c)} for {c['max_inr'] + 400}" if n == 0 else "ok done, theek hai"


def declines(e, c, n):
    return f"{_slot(c)} for {c['max_inr'] + 400}" if n == 0 else "no, sorry, can't go lower"


def holds_out(e, c, n):
    return f"{_slot(c)} for {c['max_inr'] + 400}"


def run(name, policy, expect):
    for t in TABLES:
        db.ex(f"DELETE FROM {t}")
    rid = engine.create_request(REQUEST)
    st = engine.run_until_settled(rid)
    experts = {e["expert_id"]: e for e in adapters.load_experts()}
    sent = Counter()
    order = []
    for _ in range(60):
        if st != "NEGOTIATING":
            break
        r = db.get_request_row(rid)
        eid = r["current_expert"]
        if eid not in order:
            order.append(eid)
        msg = policy(experts[eid], r["constraints"], sent[eid])
        engine.ingest_replies([adapters.sim_reply(experts[eid]["telegram_chat_id"], msg)])
        sent[eid] += 1
        st = engine.run_until_settled(rid)
    r = db.get_request_row(rid)
    c, b = r["constraints"], r["booking"]
    log = [f"{t['step']:<12} [{t['source']}] {t['msg']}" for t in
           db.q("SELECT step, msg, source FROM timeline WHERE request_id=? ORDER BY id", (rid,))]
    counters = Counter()
    for row in db.q("SELECT key FROM outbox WHERE key LIKE 'counter%'"):
        counters[row["key"].split(":")[-1].split("#")[0]] += 1
    problems = []
    if b and b["price_inr"] > c["max_inr"]:
        problems.append(f"booked above budget: {b['price_inr']} > {c['max_inr']}")
    if b and (b["start"] < c["window_start"] or b["end"] > c["window_end"]):
        problems.append("booked outside the window")
    if any(v > 2 for v in counters.values()):
        problems.append(f"more than 2 counters to one expert: {dict(counters)}")
    if r["status"] != expect:
        problems.append(f"status {r['status']}, expected {expect}")
    if name == "accepts" and not any("Savings" in line for line in log):
        problems.append('no "Savings" log line')
    print(f"\n=== {name}: {'PASS' if not problems else 'FAIL'}   status={r['status']}   contacted={order}   "
          f"counters={dict(counters)}   booking={(b or {}).get('confirmation')}")
    for p in problems:
        print("   !!", p)
    for line in log:
        if any(k in line for k in ("NEGOTIATING", "OUTREACH", "BOOK", "ESCALATED", "Savings")):
            print("   ", line[:190])
    return not problems


if __name__ == "__main__":
    print("parser:", "llm" if llm._client else "rules", "| request:", REQUEST)
    results = [run("accepts", accepts, "BOOKED"), run("declines", declines, "ESCALATED"),
               run("holds_out", holds_out, "ESCALATED")]
    print(f"\n{sum(results)}/3 scenarios passed")
    sys.exit(0 if all(results) else 1)
