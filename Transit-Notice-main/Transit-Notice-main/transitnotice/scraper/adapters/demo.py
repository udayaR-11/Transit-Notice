"""Adapter for the bundled demo authority page (served at /demo-source/advisories).

Real adapters copy this shape: find a container per advisory, read each field defensively.
"""
from bs4 import BeautifulSoup

from scraper.base import ParseResult, SourceAdapter, StructureError
from services.normalize import RawNotice


def _text(node, selector):
    el = node.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


class DemoAdapter(SourceAdapter):
    source_key = "demo"
    agency = "Demo City Transport Authority"

    def __init__(self, base_url="http://127.0.0.1:5000"):
        self.page_url = f"{base_url.rstrip('/')}/demo-source/advisories"

    def parse(self, html):
        soup = BeautifulSoup(html, "html.parser")
        board = soup.select_one("main#advisories")
        if board is None:
            raise StructureError("expected <main id='advisories'> not found (layout changed or error page)")

        result = ParseResult()
        for idx, art in enumerate(board.select("article.advisory"), start=1):
            try:
                link = art.select_one("a.permalink")
                raw = RawNotice(
                    ref=art.get("data-ref") or None,
                    title=_text(art, ".title"),
                    text=_text(art, ".text"),
                    routes_raw=_text(art, ".routes"),
                    area=_text(art, ".area"),
                    stations_raw=_text(art, ".stations"),
                    type_raw=_text(art, ".type"),
                    published_raw=_text(art, ".published"),
                    valid_from_raw=_text(art, ".valid-from"),
                    valid_to_raw=_text(art, ".valid-to"),
                    source_url=(link["href"] if link and link.has_attr("href") else self.page_url),
                )
                result.notices.append(raw)
            except Exception as exc:  # one broken block must never kill the whole run
                result.issues.append(f"record #{idx}: {type(exc).__name__}: {exc}")
        return result
