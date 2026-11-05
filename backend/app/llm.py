"""Owner: Aditya. The LLM only PARSES text into structured fields. Code validates and decides everything.
With no ANTHROPIC_API_KEY (or if the API fails or refuses), a rule-based parser is used so the pipeline never stops."""
import re
from datetime import timedelta
from typing import Literal, Optional

from pydantic import BaseModel

from .config import ANTHROPIC_API_KEY, LLM_MODEL, now

_client = None
if ANTHROPIC_API_KEY:
    import anthropic

    _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3)  # SDK retries 429/5xx


class Intake(BaseModel):
    topic: Optional[str]
    title_keywords: list[str]
    duration_min: Optional[int]
    date: Optional[str]                 # YYYY-MM-DD
    window_start_time: Optional[str]    # HH:MM, 24h
    window_end_time: Optional[str]      # HH:MM, 24h
    max_inr: Optional[int]


class Reply(BaseModel):
    intent: Literal["propose", "accept", "decline", "unclear"]
    slot_time: Optional[str]            # HH:MM, 24h, or null
    price_inr: Optional[int]


INTAKE_SYSTEM = """You extract booking constraints for an expert-call service. Output only what the user stated.
Rules:
- Never invent values. If something is not stated, use null.
- Today is {today} ({weekday}), timezone IST. Resolve "today"/"tomorrow"/weekday names to YYYY-MM-DD.
- Times are 24h HH:MM. "morning"=09:00-12:00, "afternoon"=12:00-17:00, "evening"=17:00-21:00, "night"=20:00-23:00,
  unless explicit times are given. "6-8 pm" means 18:00-20:00. A single time like "at 7pm" means start 19:00, end null.
- max_inr: the budget in rupees as an integer ("2k" = 2000, "Rs 1,500" = 1500).
- duration_min: call length in minutes ("half an hour" = 30).
- topic: short noun phrase for the expertise needed (e.g. "warehouse management").
- title_keywords: 4-8 lowercase job-title or domain words an expert with this experience would have on their profile
  (e.g. for warehouses: "warehouse", "fulfilment", "logistics", "supply chain", "inventory", "operations")."""

REPLY_SYSTEM = """You parse an expert's chat reply to a call-booking request. The client's window is {window}.
- intent: "propose" if they give a time and/or price, "accept" if they just agree (yes/ok/done/haan/theek hai),
  "decline" if they refuse or are unavailable, "unclear" if vague (e.g. "7ish", "maybe later", "let me see").
- slot_time: 24h HH:MM. Interpret bare hours as falling inside the client's window (e.g. "7:15" in an evening window = 19:15).
  Vague times like "7ish" or "around 7" -> slot_time null and intent "unclear".
- price_inr: integer rupees if stated ("1.8k" = 1800, "1800 rs" = 1800), else null.
Replies may be in English, Hindi or Hinglish."""


def _call(system, text, schema):
    if not _client:
        return None
    try:
        r = _client.messages.parse(
            model=LLM_MODEL, max_tokens=2000, system=system,
            messages=[{"role": "user", "content": text}], output_format=schema,
        )
        if r.stop_reason == "refusal" or r.parsed_output is None:
            return None
        return r.parsed_output
    except Exception as e:  # network / rate limit after retries -> rule fallback
        print("LLM error, using rule parser:", type(e).__name__, e)
        return None


def parse_intake(text: str) -> tuple[Intake, str]:
    t = now()
    out = _call(INTAKE_SYSTEM.format(today=t.date().isoformat(), weekday=t.strftime("%A")), text, Intake)
    if out:
        return out, "llm"
    return _rule_intake(text), "rules"


def parse_reply(text: str, window_desc: str) -> tuple[Reply, str]:
    out = _call(REPLY_SYSTEM.format(window=window_desc), text, Reply)
    if out:
        return out, "llm"
    return _rule_reply(text), "rules"


# ---- rule-based fallback ---------------------------------------------------

def _hhmm(h, m, pm_hint):
    h, m = int(h), int(m or 0)
    if pm_hint and h < 12:
        h += 12
    return f"{h:02d}:{m:02d}"


def _rule_intake(text: str) -> Intake:
    s = text.lower()
    t = now()
    date = None
    if "tomorrow" in s or "kal" in s:
        date = (t + timedelta(days=1)).date().isoformat()
    elif "today" in s or "aaj" in s:
        date = t.date().isoformat()
    else:  # "on 8 November 2026" / "8 nov" / "2026-11-08"
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        iso = re.search(r"\b(20\d\d)-(\d{2})-(\d{2})\b", s)
        dm = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(months) + r")[a-z]*\.?(?:,?\s+(20\d\d))?", s)
        if iso:
            date = f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
        elif dm:
            year = int(dm.group(3) or t.year)
            date = f"{year}-{months.index(dm.group(2)) + 1:02d}-{int(dm.group(1)):02d}"
    budget = re.search(r"(?:budget|max|under|upto|up to|₹|rs\.?|inr)\s*(?:of\s*)?₹?\s*(\d[\d,]*)(k?)", s)
    max_inr = None
    if budget:
        max_inr = int(budget.group(1).replace(",", "")) * (1000 if budget.group(2) else 1)
    dur = re.search(r"(\d+)\s*(?:min|mins|minutes)", s)
    duration = int(dur.group(1)) if dur else (30 if "half an hour" in s else None)
    pm = any(w in s for w in ("pm", "evening", "shaam", "night"))
    no_dates = re.sub(r"\b20\d\d-\d{2}-\d{2}\b", " ", s)  # a date like 2026-11-08 is not a time range
    rng = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:-|–|to)\s*(\d{1,2})(?::(\d{2}))?", no_dates)
    ws = we = None
    if rng:
        ws, we = _hhmm(rng.group(1), rng.group(2), pm), _hhmm(rng.group(3), rng.group(4), pm)
    elif "evening" in s:
        ws, we = "17:00", "21:00"
    elif "morning" in s:
        ws, we = "09:00", "12:00"
    elif "afternoon" in s:
        ws, we = "12:00", "17:00"
    topic = None
    m = re.search(r"(?:who has |who's |someone who |expert (?:in|on) |about |on )([a-z ]+?)(?:,|\.| budget| for| tomorrow| today|$)", s)
    if m:
        topic = re.sub(r"^(?:has |have |had )?(?:managed |run |worked (?:in|at) |led )?(?:an? )?", "", m.group(1).strip())
    if not topic:
        m = re.search(r"([a-z]+(?: [a-z]+)?) (?:expert|specialist|person|consultant)", s)
        topic = m.group(1).replace("a ", "").strip() if m else None
    kws = [w for w in re.findall(r"[a-z]+", topic or "") if len(w) > 3]
    return Intake(topic=topic, title_keywords=kws, duration_min=duration, date=date,
                  window_start_time=ws, window_end_time=we, max_inr=max_inr)


def _rule_reply(text: str) -> Reply:
    s = text.lower().strip()
    if re.search(r"\b(no|nope|busy|not available|can't|cannot|nahi|nahin|sorry)\b", s):
        return Reply(intent="decline", slot_time=None, price_inr=None)
    if re.search(r"\b(ish|around|maybe|later|let me see|dekhta)\b", s):
        return Reply(intent="unclear", slot_time=None, price_inr=None)
    tm = re.search(r"\b(\d{1,2})[:.](\d{2})\b|\b(\d{1,2})\s*(am|pm)\b", s)
    slot = None
    if tm:
        if tm.group(1):
            slot = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        else:
            h = int(tm.group(3)) % 12 + (12 if tm.group(4) == "pm" else 0)
            slot = f"{h:02d}:00"
    rest = s[tm.end():] if tm else s
    pr = re.search(r"(\d[\d,]{2,})|(\d+(?:\.\d)?)k\b", rest)
    price = None
    if pr:
        price = int(pr.group(1).replace(",", "")) if pr.group(1) else int(float(pr.group(2)) * 1000)
    if slot or price:
        return Reply(intent="propose", slot_time=slot, price_inr=price)
    if re.search(r"\b(yes|ok|okay|done|sure|haan|ha|theek|thik|fine|works)\b", s):
        return Reply(intent="accept", slot_time=None, price_inr=None)
    return Reply(intent="unclear", slot_time=None, price_inr=None)
