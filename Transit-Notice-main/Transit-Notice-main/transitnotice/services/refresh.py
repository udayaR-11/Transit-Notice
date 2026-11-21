"""Orchestrates refresh of all sources + background scheduler (or trigger manually)."""
import logging
import threading

from config import config
from scraper.fetcher import Fetcher
from scraper.registry import enabled_adapters
from services import alerts as alert_service
from services.ingest import refresh_source

log = logging.getLogger("transitnotice.refresh")
_lock = threading.Lock()   # never run two refreshes at the same time


def refresh_all(conn, fetcher=None, adapters=None, now=None):
    if not _lock.acquire(blocking=False):
        log.warning("refresh already running, skipping")
        return []
    try:
        fetcher = fetcher or Fetcher()
        results = []
        for adapter in (adapters if adapters is not None else enabled_adapters()):
            summary = refresh_source(conn, adapter, fetcher, config.source_tz, now=now)
            if summary.events:
                alert_service.process_events(conn, summary.events, config.source_tz, now=now)
            results.append(summary)
        return results
    finally:
        _lock.release()


class Scheduler(threading.Thread):
    """Runs refresh_all every REFRESH_MINUTES. Uses its own DB connection (SQLite threads)."""

    def __init__(self, db_path, interval_minutes=None):
        super().__init__(daemon=True, name="tn-scheduler")
        self.db_path = db_path
        self.interval = (interval_minutes or config.REFRESH_MINUTES) * 60
        self._halt = threading.Event()

    def run(self):
        from db import open_db
        conn = open_db(self.db_path)
        while not self._halt.is_set():
            try:
                refresh_all(conn)
            except Exception:
                log.exception("scheduled refresh crashed (will retry next interval)")
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()
