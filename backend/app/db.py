"""Persistent state shared by the HTTP API and negotiation worker."""
import json
import sqlite3
import threading
from contextlib import contextmanager

from .config import CLOUD, DATABASE_URL, DB_PATH, now_iso

_lock = threading.RLock()
_sqlite = None
_pool = None
_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY, status TEXT, raw_text TEXT, clarification_question TEXT,
  clarified INTEGER DEFAULT 0, constraints TEXT, booking TEXT, escalation TEXT,
  current_expert TEXT, contacted_at DOUBLE PRECISION, offer TEXT, counter_sent INTEGER DEFAULT 0,
  asked_once INTEGER DEFAULT 0, created_at TEXT, owner_email TEXT
);
CREATE TABLE IF NOT EXISTS shortlist (
  request_id TEXT, expert_id TEXT, ord INTEGER, data TEXT, outreach_state TEXT, last_ask TEXT,
  PRIMARY KEY (request_id, expert_id)
);
CREATE TABLE IF NOT EXISTS timeline (
  id {timeline_key}, request_id TEXT, t TEXT, step TEXT, msg TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS replies (
  update_id {update_type} PRIMARY KEY, chat_id TEXT, text TEXT, t TEXT,
  expert_id TEXT, request_id TEXT, processed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (key TEXT PRIMARY KEY, chat_id TEXT, text TEXT, status TEXT, t TEXT);
CREATE TABLE IF NOT EXISTS calendar_events (
  event_id TEXT PRIMARY KEY, expert_id TEXT, start TEXT, "end" TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash TEXT PRIMARY KEY, email TEXT, name TEXT, picture TEXT, created_at TEXT, expires_at DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS auth_states (
  state TEXT PRIMARY KEY, verifier TEXT, redirect TEXT, expires_at DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


@contextmanager
def _connection():
    global _sqlite, _pool
    if DATABASE_URL:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        with _lock:
            if _pool is None:
                _pool = ConnectionPool(DATABASE_URL, min_size=0, max_size=4, timeout=10,
                                       kwargs={"row_factory": dict_row, "prepare_threshold": None,
                                               "connect_timeout": 8})
        with _pool.connection() as connection:
            yield connection
    else:
        if CLOUD:
            raise RuntimeError("Configure DATABASE_URL for the deployed API and worker")
        with _lock:
            if _sqlite is None:
                _sqlite = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
                _sqlite.row_factory = sqlite3.Row
                _sqlite.execute("PRAGMA journal_mode=WAL")
            yield _sqlite


def initialize():
    global _ready
    with _lock:
        if _ready:
            return
        key = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
        with _connection() as con:
            if DATABASE_URL:
                con.execute("SELECT pg_advisory_xact_lock(603471082)")
            else:
                con.execute("BEGIN IMMEDIATE")
            try:
                update_type = "BIGINT" if DATABASE_URL else "INTEGER"
                for statement in SCHEMA.format(timeline_key=key, update_type=update_type).split(";"):
                    if statement.strip():
                        con.execute(statement)
                if DATABASE_URL:
                    con.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS owner_email TEXT")
                elif not any(col[1] == "owner_email" for col in con.execute("PRAGMA table_info(requests)")):
                    con.execute("ALTER TABLE requests ADD COLUMN owner_email TEXT")
                con.commit()
            except Exception:
                con.rollback()
                raise
        _ready = True


class Transaction:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, args=()):
        # All repository SQL uses bound parameters and SQLite-style question marks.
        if DATABASE_URL:
            sql = sql.replace("?", "%s")
        return self.connection.execute(sql, args)


@contextmanager
def tx():
    initialize()
    with _connection() as con:
        if not DATABASE_URL:
            con.execute("BEGIN IMMEDIATE")
        try:
            yield Transaction(con)
            con.commit()
        except Exception:
            con.rollback()
            raise


def q(sql, args=()):
    with tx() as con:
        return [dict(row) for row in con.execute(sql, args).fetchall()]


def q1(sql, args=()):
    with tx() as con:
        row = con.execute(sql, args).fetchone()
        return dict(row) if row is not None else None


def ex(sql, args=()):
    with tx() as con:
        return con.execute(sql, args).rowcount


@contextmanager
def worker_turn():
    # Transaction-scoped locking also works through Neon's transaction pooler.
    # Business writes use their own connections and commit before side effects.
    if not DATABASE_URL:
        yield True
        return
    initialize()
    with _connection() as con:
        row = con.execute("SELECT pg_try_advisory_xact_lock(603471083) AS acquired").fetchone()
        yield row["acquired"]


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
