import requests

from scraper.fetcher import FetchError, Fetcher, RobotsDisallowed
import pytest


class Resp:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls, self.headers = routes, [], {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        value = self.routes.get(url) if not isinstance(self.routes.get(url), list) else self.routes[url].pop(0)
        if value is None:
            return Resp(404)
        if isinstance(value, Exception):
            raise value
        return value


def make(routes, **kw):
    sleeps = []
    f = Fetcher(session=FakeSession(routes), sleep=sleeps.append, min_gap=0, backoff_base=1, max_retries=3, **kw)
    return f, sleeps


ROBOTS_OK = Resp(200, "User-agent: *\nAllow: /\n")


def test_retries_with_exponential_backoff_then_succeeds():
    f, sleeps = make({"http://a.test/robots.txt": ROBOTS_OK,
                      "http://a.test/p": [requests.Timeout("slow"), Resp(503), Resp(200, "<html>ok</html>")]})
    assert f.get("http://a.test/p") == "<html>ok</html>"
    assert sleeps == [1, 2]


def test_gives_up_after_retry_ceiling():
    f, sleeps = make({"http://a.test/robots.txt": ROBOTS_OK, "http://a.test/p": [Resp(500)] * 5})
    with pytest.raises(FetchError, match="giving up"):
        f.get("http://a.test/p")
    assert len([c for c in f.session.calls if c.endswith("/p")]) == 3


def test_client_error_is_not_retried():
    f, sleeps = make({"http://a.test/robots.txt": ROBOTS_OK, "http://a.test/p": [Resp(404)]})
    with pytest.raises(FetchError):
        f.get("http://a.test/p")
    assert sleeps == []


def test_robots_disallow_blocks_fetch_entirely():
    f, _ = make({"http://a.test/robots.txt": Resp(200, "User-agent: *\nDisallow: /\n")})
    with pytest.raises(RobotsDisallowed):
        f.get("http://a.test/p")
    assert "http://a.test/p" not in f.session.calls


def test_unreachable_or_forbidden_robots_means_do_not_crawl():
    f, _ = make({"http://a.test/robots.txt": requests.ConnectionError("down")})
    with pytest.raises(RobotsDisallowed):
        f.get("http://a.test/p")
    f2, _ = make({"http://b.test/robots.txt": Resp(403)})
    with pytest.raises(RobotsDisallowed):
        f2.get("http://b.test/p")


def test_rate_limit_waits_between_requests_to_same_host():
    sleeps, t = [], [100.0]
    f = Fetcher(session=FakeSession({"http://a.test/robots.txt": ROBOTS_OK, "http://a.test/p": Resp(200, "x")}),
                sleep=sleeps.append, clock=lambda: t[0], min_gap=2.0)
    f.get("http://a.test/p"); t[0] += 0.5
    f.get("http://a.test/p")
    assert sleeps and abs(sleeps[0] - 1.5) < 1e-6
