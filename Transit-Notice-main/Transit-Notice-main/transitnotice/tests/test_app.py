import pytest

from app import create_app
from services.ingest import refresh_source
from tests.conftest import NOW, TZ, FakeFetcher
from scraper.adapters.demo import DemoAdapter


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "t.db")
    app = create_app(db_path=db_path, start_scheduler=False, clock=lambda: NOW)
    from db import open_db
    conn = open_db(db_path)
    refresh_source(conn, DemoAdapter("http://demo.example"), FakeFetcher("sample_v1.html"), TZ, now=NOW)
    conn.close()
    return app.test_client()


def test_dashboard_shows_active_notices_with_provenance(client):
    html = client.get("/").get_data(as_text=True)
    assert "Routes 45A and 45B diverted" in html and "Last verified" in html and "Official source" in html
    assert "Route 7 stop closed" not in html                     # expired hidden by default
    assert "up to date" in html


def test_archive_and_filters(client):
    assert "Route 7 stop closed" in client.get("/?status=expired").get_data(as_text=True)
    html = client.get("/?route=45b").get_data(as_text=True)
    assert "45A" in html and "Green Line" not in html


def test_stale_banner_when_clock_moves_on(tmp_path):
    from datetime import timedelta
    db_path = str(tmp_path / "t.db")
    from db import open_db
    conn = open_db(db_path)
    refresh_source(conn, DemoAdapter("http://demo.example"), FakeFetcher("sample_v1.html"), TZ, now=NOW)
    conn.close()
    app = create_app(db_path=db_path, start_scheduler=False, clock=lambda: NOW + timedelta(hours=5))
    html = app.test_client().get("/").get_data(as_text=True)
    assert "Could not confirm these updates are current" in html and "Unverified since last check" in html


def test_json_api(client):
    data = client.get("/api/notices?route=GL").get_json()
    assert data["timezone"] == "Asia/Kolkata" and [n["routes"] for n in data["notices"]] == [["GL"]]
    assert data["sources"][0]["state"] == "live"


def test_notice_detail_and_404(client):
    assert client.get("/notice/demo:TN-A1").status_code == 200
    assert client.get("/notice/demo:nope").status_code == 404


def test_subscribe_validation_and_saving(client):
    r = client.post("/subscribe", data={"label": "me"}, follow_redirects=True)
    assert "at least a route or an area" in r.get_data(as_text=True)
    r = client.post("/subscribe", data={"label": "me", "route": "45a"}, follow_redirects=True)
    assert "Alert saved" in r.get_data(as_text=True) and "route 45A" in r.get_data(as_text=True)


def test_admin_requires_token(client):
    assert client.post("/admin", data={"token": "wrong", "action": "refresh"}).status_code == 403
    assert client.post("/admin", data={"token": "", "action": "view"}).status_code == 403
    assert client.post("/admin", data={"token": "test-token", "action": "view"}).status_code == 200


def test_scraped_html_is_escaped_and_unsafe_links_neutralised(tmp_path):
    db_path = str(tmp_path / "x.db")
    from db import open_db
    html = open("fixtures/sample_v1.html").read().replace("Road resurfacing.", "<script>alert(1)</script>")
    html = html.replace("https://demo.example/notice/TN-A1", "javascript:alert(1)")
    conn = open_db(db_path)
    refresh_source(conn, DemoAdapter("http://demo.example"), FakeFetcher(html), TZ, now=NOW)
    conn.close()
    page = create_app(db_path=db_path, start_scheduler=False, clock=lambda: NOW).test_client().get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page and "javascript:" not in page


def test_overview_timeline_and_relative_text(tmp_path):
    from datetime import timedelta
    from db import open_db
    from services import queries
    conn = open_db(":memory:")
    refresh_source(conn, DemoAdapter("http://demo.example"), FakeFetcher("no_end_date.html"), TZ, now=NOW)
    notices = queries.search_notices(conn, tz=TZ, now=NOW, status="all")
    ov = queries.overview(notices)
    assert (ov["active"], ov["upcoming"], ov["expired"], ov["open_ended"]) == (3, 1, 1, 1)
    assert ov["routes"] == 4                                   # 45A, 45B, GL, 21 (distinct routes of active notices)
    by = {n["notice_id"].split(":")[1]: n for n in notices}
    assert by["TN-B2"]["relative"].startswith("Ends in") and 0 <= by["TN-B2"]["progress"] <= 100
    assert by["TN-D4"]["relative"].startswith("Starts in") and by["TN-C3"]["relative"].startswith("Ended")
    assert by["TN-E5"]["relative"].startswith("Ongoing") and by["TN-E5"]["progress"] is None
    tl = queries.timeline(notices, NOW, TZ)
    ids = {r["notice_id"].split(":")[1] for r in tl["rows"]}
    assert ids == {"TN-A1", "TN-B2", "TN-D4", "TN-E5"} and len(tl["ticks"]) == 14      # expired never on the timeline
    open_row = next(r for r in tl["rows"] if r["notice_id"].endswith("TN-E5"))
    assert open_row["open_ended"] and open_row["left"] + open_row["width"] >= 99.9


def test_dashboard_tabs_keep_filters(client):
    html = client.get("/?route=45A&status=active").get_data(as_text=True)
    assert "route=45A" in html and "Active and upcoming" in html and 'aria-current="true"' in html
