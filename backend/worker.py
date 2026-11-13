"""Run one Telegram poller and resume pending booking requests from the database."""
import logging
import signal
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
                    engine.tick()
        except Exception:
            logging.exception("Booking worker tick failed")
        stopping.wait(max(WORKER_TICK_S, 0.1))


if __name__ == "__main__":
    run()
