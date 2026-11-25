"""Run one Telegram poller and resume pending booking requests from the database."""
import logging
import signal
import time
from threading import Event

from backend.app import db, engine
from backend.app.config import WORKER_TICK_S


def run():
    stopping = Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            with db.worker_turn() as acquired:
                if acquired:
                    db.kv_set('worker_heartbeat', str(time.time()))
                    engine.tick()
                    db.kv_set('worker_heartbeat', str(time.time()))
                    if time.time() - float(db.kv_get('last_cleanup', '0')) > 3600:
                        db.ex('DELETE FROM auth_states WHERE expires_at<?', (time.time(),))
                        db.ex('DELETE FROM auth_sessions WHERE expires_at<?', (time.time(),))
                        db.ex('DELETE FROM rate_limits WHERE window_start<?', (int(time.time()) - 86400,))
                        db.kv_set('last_cleanup', str(time.time()))
        except Exception:
            logging.exception("Booking worker tick failed")
        stopping.wait(max(WORKER_TICK_S, 0.1))


if __name__ == "__main__":
    run()
