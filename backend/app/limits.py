"""Database-backed limits shared by all API instances."""
import hashlib
import time

from fastapi import HTTPException

from . import db


def check(action: str, identity: str, maximum: int, seconds: int = 60):
    now = int(time.time())
    window = now // seconds * seconds
    key = hashlib.sha256(f"{action}:{identity}".encode()).hexdigest()
    row = db.q1(
        "INSERT INTO rate_limits(key,window_start,count) VALUES(?,?,1) "
        "ON CONFLICT(key) DO UPDATE SET "
        "count=CASE WHEN rate_limits.window_start=excluded.window_start THEN rate_limits.count+1 ELSE 1 END, "
        "window_start=excluded.window_start RETURNING count", (key, window))
    if row['count'] > maximum:
        raise HTTPException(429, "Too many requests. Please try again shortly.",
                            headers={"Retry-After": str(window + seconds - now)})
