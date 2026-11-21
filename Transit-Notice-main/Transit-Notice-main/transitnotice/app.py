"""TransitNotice - Flask application (dashboard, API, subscriptions, admin refresh, demo source)."""
import hmac
import logging
import os
from datetime import timedelta
from urllib.parse import urlparse

from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_file, url_for, flash

from config import config
from db import open_db
from services import queries
from services.refresh import Scheduler, refresh_all
from services.timeutil import fmt_local, from_iso, humanize_age, utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TYPE_LABELS = {
    "DIVERSION": "Diversion", "SUSPENSION": "Service suspended", "DELAY": "Delays",
    "SCHEDULE_CHANGE": "Schedule change", "STOP_CLOSURE": "Stop closed", "OTHER": "Notice",
}
STATE_LABELS = {"active": "Active", "upcoming": "Upcoming", "expired": "Expired", "withdrawn": "Withdrawn"}


def create_app(db_path=None, start_scheduler=None, clock=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or config.DB_PATH
    app.config["SECRET_KEY"] = os.environ.get("TN_SECRET_KEY") or os.urandom(24)
    app.config["CLOCK"] = clock or utcnow
    tz = config.source_tz

    def db():
        if "db" not in g:
            g.db = open_db(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    # ---- template helpers -------------------------------------------------------------
    @app.template_filter("local")
    def local_filter(iso):
        return fmt_local(iso, tz)

    @app.template_filter("ago")
    def ago_filter(iso):
        return humanize_age(iso, app.config["CLOCK"]())

    @app.template_filter("safe_url")
    def safe_url(value):
        """Scraped URLs are untrusted: only http(s) links are rendered as links."""
        return value if urlparse(value or "").scheme in ("http", "https") else "#"

    @app.template_filter("local_short")
    def local_short(iso):
        return from_iso(iso).astimezone(tz).strftime("%d %b, %H:%M") if iso else "-"

    @app.template_global()
    def url_with(**changes):
        """Current query string with some filters changed (used by the status tabs)."""
        args = request.args.to_dict()
        args.update(changes)
        return url_for("index", **{k: v for k, v in args.items() if v not in (None, "")})

    @app.context_processor
    def header_status():
        """Header pill: never says 'live' - it says when we last confirmed the data."""
        try:
            now = app.config["CLOCK"]()
            fresh = queries.source_freshness(db(), now)
        except Exception:
            fresh = []
        if not fresh:
            return {"hdr": {"state": "unknown", "label": "Not checked yet"}}
        if any(x["stale"] for x in fresh):
            last = max((x["last_success_at"] for x in fresh if x["last_success_at"]), default=None)
            problem = any(x["last_error"] for x in fresh)
            text = ("Source problem · " if problem else "") + ("last confirmed " + humanize_age(last, now) if last
                                                              else "never confirmed")
            return {"hdr": {"state": "stale", "label": text[0].upper() + text[1:]}}
        last = min(x["last_success_at"] for x in fresh)
        return {"hdr": {"state": "fresh", "label": "Checked " + humanize_age(last, now)}}

    app.jinja_env.globals.update(
        TYPE_LABELS=TYPE_LABELS, STATE_LABELS=STATE_LABELS, tz_name=config.SOURCE_TZ_NAME,
        TYPE_ICONS={"DIVERSION": "i-diversion", "SUSPENSION": "i-pause", "DELAY": "i-clock",
                    "SCHEDULE_CHANGE": "i-calendar", "STOP_CLOSURE": "i-pin", "OTHER": "i-info"})

    # ---- pages ------------------------------------------------------------------------
    def _filters():
        a = request.args
        return dict(q=a.get("q", "").strip(), route=a.get("route", "").strip(), station=a.get("station", "").strip(),
                    area=a.get("area", "").strip(), date=a.get("date", "").strip(), status=a.get("status", "current"))

    @app.get("/")
    def index():
        now, f = app.config["CLOCK"](), _filters()
        notices = queries.search_notices(db(), tz=tz, now=now, **f)
        fresh = queries.source_freshness(db(), now)
        everything = queries.search_notices(db(), tz=tz, now=now, status="all")
        return render_template("index.html", notices=notices, f=f, fresh=fresh, now=now,
                               counts=queries.type_counts(notices), any_stale=any(x["stale"] for x in fresh),
                               stats=queries.overview(everything), tl=queries.timeline(notices, now, tz))

    @app.get("/notice/<path:notice_id>")
    def notice_detail(notice_id):
        now = app.config["CLOCK"]()
        found = queries.search_notices(db(), tz=tz, now=now, status="all")
        notice = next((n for n in found if n["notice_id"] == notice_id), None)
        if notice is None:
            abort(404)
        return render_template("notice.html", n=notice, revs=queries.revisions(db(), notice_id), now=now)

    @app.get("/api/notices")
    def api_notices():
        now, f = app.config["CLOCK"](), _filters()
        notices = queries.search_notices(db(), tz=tz, now=now, **f)
        fresh = queries.source_freshness(db(), now)
        return jsonify({
            "generated_at": now.isoformat(), "timezone": config.SOURCE_TZ_NAME,
            "sources": [{"source_key": x["source"]["source_key"], "state": x["state"],
                         "last_success_at": x["last_success_at"], "last_error": x["last_error"]} for x in fresh],
            "notices": [{k: n[k] for k in ("notice_id", "agency", "routes", "stations", "area", "type", "title",
                                           "summary", "valid_from", "valid_to", "open_ended", "state", "revision_id",
                                           "change_summary", "last_confirmed_at", "source_url", "source_stale")}
                        for n in notices]})

    @app.route("/subscribe", methods=["GET", "POST"])
    def subscribe():
        if request.method == "POST":
            label = request.form.get("label", "").strip()[:60]
            route = request.form.get("route", "").strip().upper().replace(" ", "")[:20] or None
            area = request.form.get("area", "").strip()[:60] or None
            contact = request.form.get("contact", "").strip()[:120] or None
            if not label:
                flash("Enter a name for this alert.", "error")
            elif not route and not area:
                flash("Choose at least a route or an area, so you only get relevant alerts.", "error")
            else:
                db().execute("INSERT INTO subscribers(label, contact, filter_route, filter_area, created_at) "
                             "VALUES (?,?,?,?,?)", (label, contact, route, area, app.config["CLOCK"]().isoformat()))
                db().commit()
                flash("Alert saved. In demo mode, alerts are written to the delivery log.", "ok")
                return redirect(url_for("subscribe"))
        subs = db().execute("SELECT id, label, filter_route, filter_area FROM subscribers ORDER BY id DESC").fetchall()
        recent = db().execute(
            "SELECT a.kind, a.alert_status, a.alerted_at, a.message, s.label FROM alerts a "
            "JOIN subscribers s ON s.id=a.subscriber_id ORDER BY a.id DESC LIMIT 15").fetchall()
        return render_template("subscribe.html", subs=subs, recent=recent)

    # ---- admin (token protected) ------------------------------------------------------
    def _admin_ok():
        token = config.ADMIN_TOKEN
        supplied = request.form.get("token", "")
        return bool(token) and hmac.compare_digest(token.encode(), supplied.encode())

    @app.route("/admin", methods=["GET", "POST"])
    def admin():
        if not config.ADMIN_TOKEN:
            return render_template("admin.html", disabled=True, authed=False), 503
        if request.method == "POST":
            if not _admin_ok():
                return render_template("admin.html", authed=False, error="Wrong token."), 403
            results = None
            if request.form.get("action") == "refresh":
                results = refresh_all(db(), now=app.config["CLOCK"]())
            logs = db().execute("SELECT * FROM refresh_logs ORDER BY id DESC LIMIT 20").fetchall()
            return render_template("admin.html", authed=True, token=request.form["token"], logs=logs, results=results)
        return render_template("admin.html", authed=False)

    # ---- bundled demo authority page (what the scraper reads in demo mode) -------------
    @app.get("/demo-source/advisories")
    def demo_source():
        path = os.path.join("data", "demo_source.html")
        if not os.path.exists(path):
            abort(404)
        return send_file(path, mimetype="text/html")

    @app.get("/robots.txt")
    def robots():
        return "User-agent: *\nAllow: /demo-source/\nDisallow: /admin\n", 200, {"Content-Type": "text/plain"}

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    should_start = config.ENABLE_SCHEDULER if start_scheduler is None else start_scheduler
    if should_start and not app.debug:
        Scheduler(app.config["DB_PATH"]).start()
    return app


if __name__ == "__main__":
    from scripts.seed_demo_source import write_demo_page
    if not os.path.exists(os.path.join("data", "demo_source.html")):
        write_demo_page()
    create_app().run(host="127.0.0.1", port=5000, debug=False)
