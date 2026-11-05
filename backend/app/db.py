"""Owner: Aditya. SQLite holds all state, so a crash resumes where it stopped.
Rule: write the new state to the DB BEFORE doing the side effect it leads to."""
import json
import sqlite3
import threading
from contextlib import contextmanager

from .config import DB_PATH, now_iso

_lock = threading.RLock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY, status TEXT, raw_text TEXT, clarification_question TEXT,
  clarified INTEGER DEFAULT 0, constraints TEXT, booking TEXT, escalation TEXT,
  current_expert TEXT, contacted_at REAL, offer TEXT, counter_sent INTEGER DEFAULT 0,
  asked_once INTEGER DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS shortlist (
  request_id TEXT, expert_id TEXT, ord INTEGER, data TEXT, outreach_state TEXT, last_ask TEXT,
  PRIMARY KEY (request_id, expert_id)
);
CREATE TABLE IF NOT EXISTS timeline (
  id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, t TEXT, step TEXT, msg TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS replies (
  update_id INTEGER PRIMARY KEY, chat_id TEXT, text TEXT, t TEXT,
  expert_id TEXT, request_id TEXT, processed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (key TEXT PRIMARY KEY, chat_id TEXT, text TEXT, status TEXT, t TEXT);
CREATE TABLE IF NOT EXISTS calendar_events (
  event_id TEXT PRIMARY KEY, expert_id TEXT, start TEXT, end TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""

with _lock:
    _conn.executescript(SCHEMA)


@contextmanager
def tx():
    with _lock:
        _conn.execute("BEGIN IMMEDIATE")
        try:
            yield _conn
            _conn.execute("COMMIT")
        except Exception:
            _conn.execute("ROLLBACK")
            raise


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def ex(sql, args=()):
    with _lock:
        _conn.execute(sql, args)


def j(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def unj(v):
    return json.loads(v) if v else None


# ---- helpers ---------------------------------------------------------------

def log(request_id, step, msg, source):
    ex("INSERT INTO timeline (request_id, t, step, msg, source) VALUES (?,?,?,?,?)",
       (request_id, now_iso(), step, msg, source))


def update_request(rid, **fields):
    for k in ("constraints", "booking", "escalation", "offer"):
        if k in fields:
            fields[k] = j(fields[k])
    sets = ", ".join(f"{k}=?" for k in fields)
    ex(f"UPDATE requests SET {sets} WHERE id=?", (*fields.values(), rid))


def get_request_row(rid):
    r = q1("SELECT * FROM requests WHERE id=?", (rid,))
    if r:
        for k in ("constraints", "booking", "escalation", "offer"):
            r[k] = unj(r[k])
    return r


def shortlist_rows(rid):
    rows = q("SELECT * FROM shortlist WHERE request_id=? ORDER BY ord", (rid,))
    for r in rows:
        r["data"] = unj(r["data"])
        r["last_ask"] = unj(r["last_ask"])
    return rows


def set_outreach(rid, eid, state, last_ask=None):
    if last_ask is not None:
        ex("UPDATE shortlist SET outreach_state=?, last_ask=? WHERE request_id=? AND expert_id=?",
           (state, j(last_ask), rid, eid))
    else:
        ex("UPDATE shortlist SET outreach_state=? WHERE request_id=? AND expert_id=?", (state, rid, eid))


def kv_get(k, default=None):
    r = q1("SELECT v FROM kv WHERE k=?", (k,))
    return r["v"] if r else default


def kv_set(k, v):
    ex("INSERT INTO kv (k, v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))
