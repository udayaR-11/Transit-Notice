"""Polite HTTP fetching: robots.txt check, per-host rate limit, timeout, retries with backoff."""
import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from config import config

log = logging.getLogger("transitnotice.fetch")


class FetchError(Exception):
    """Source could not be fetched (network, HTTP error, or disallowed)."""


class RobotsDisallowed(FetchError):
    """robots.txt forbids the URL (or could not be read, in which case we conservatively do not crawl)."""


class Fetcher:
    def __init__(self, user_agent=None, timeout=None, max_retries=None, backoff_base=None,
                 min_gap=None, session=None, sleep=time.sleep, clock=time.monotonic):
        self.user_agent = user_agent or config.USER_AGENT
        self.timeout = timeout if timeout is not None else config.HTTP_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else config.HTTP_MAX_RETRIES
        self.backoff_base = backoff_base if backoff_base is not None else config.HTTP_BACKOFF_BASE
        self.min_gap = min_gap if min_gap is not None else config.MIN_REQUEST_GAP
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = self.user_agent
        self._sleep, self._clock = sleep, clock
        self._last_hit = {}
        self._robots = {}
        self._robots_note = {}

    # -- robots.txt -------------------------------------------------------------------------
    def allowed(self, url):
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self.session.get(f"{origin}/robots.txt", timeout=self.timeout)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                elif resp.status_code in (401, 403):
                    rp.disallow_all = True      # access restricted -> do not crawl
                    self._robots_note[origin] = f"robots.txt returned HTTP {resp.status_code}"
                else:
                    rp.parse([])                # 404 etc.: no restrictions published
            except requests.RequestException as exc:
                log.warning("robots.txt unreachable for %s: %s (treating as disallowed)", origin, exc)
                rp.disallow_all = True
                self._robots_note[origin] = f"robots.txt unreachable ({type(exc).__name__}); not crawling"
            self._robots[origin] = rp
        return self._robots[origin].can_fetch(self.user_agent, url)

    def _throttle(self, host):
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.min_gap - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_hit[host] = self._clock()

    # -- main entry --------------------------------------------------------------------------
    def get(self, url):
        if not self.allowed(url):
            origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
            raise RobotsDisallowed(self._robots_note.get(origin) or f"robots.txt disallows fetching {url}")
        host = urlparse(url).netloc
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle(host)
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise FetchError(f"HTTP {resp.status_code}")
                if resp.status_code != 200:   # 4xx other than 429 will not fix itself: do not retry
                    raise FetchError(f"HTTP {resp.status_code} (not retrying)")
                return resp.text
            except FetchError as exc:
                last_exc = exc
                if "not retrying" in str(exc):
                    break
            except requests.RequestException as exc:
                last_exc = FetchError(f"{type(exc).__name__}: {exc}")
            if attempt < self.max_retries:
                delay = self.backoff_base * (2 ** (attempt - 1))
                log.warning("fetch %s failed (%s), retry %d/%d in %.1fs", url, last_exc, attempt,
                            self.max_retries - 1, delay)
                self._sleep(delay)
        raise FetchError(f"giving up on {url}: {last_exc}")
