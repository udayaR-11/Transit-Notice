"""Generate data/demo_source.html - the fake 'authority advisory page' used in demo mode.

Dates are relative to today (source time zone) so the demo always has active/upcoming/expired items.
Edit data/demo_source.html by hand (or use scripts/mentor_challenge.py) to simulate source changes.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config  # noqa: E402

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Demo City Transport Authority - Service Advisories</title></head>
<body>
<h1>Demo City Transport Authority - Service Advisories</h1>
<p>Official notices for passengers. This is a DEMO page created for the TransitNotice project.</p>
<main id="advisories">
{articles}
</main>
</body></html>
"""

ARTICLE = """  <article class="advisory" data-ref="{ref}">
    <h2 class="title">{title}</h2>
    <p class="type">{type}</p>
    <p class="routes">{routes}</p>
    <p class="area">{area}</p>
    <p class="stations">{stations}</p>
    <time class="published">{published}</time>
    <span class="valid-from">{vfrom}</span>
    <span class="valid-to">{vto}</span>
    <p class="text">{text}</p>
    <a class="permalink" href="http://127.0.0.1:5000/demo-source/advisories#{ref}">Official notice {ref}</a>
  </article>"""


def _f(dt):
    return dt.strftime("%d %b %Y %H:%M")


def sample_items(now_local):
    d = lambda days, hour=6: (now_local + timedelta(days=days)).replace(hour=hour, minute=0)
    return [
        dict(ref="TN-1001", title="Route 45A and 45B diverted via Bypass Road", type="Diversion",
             routes="45A, 45B", area="Hosur Road", stations="Silk Board; Madiwala",
             published=_f(d(-2, 9)), vfrom=_f(d(-1)), vto=_f(d(3, 22)),
             text="Due to road resurfacing, routes 45A and 45B will run via Bypass Road and skip Silk Board stop."),
        dict(ref="TN-1002", title="Metro Green Line: service suspended between Central and Park", type="Service outage",
             routes="GL", area="Central", stations="Central; Park Street",
             published=_f(d(-1, 18)), vfrom=_f(d(0, 0)), vto=_f(d(1, 23)),
             text="Planned track maintenance. Shuttle buses will operate. Service outage for two days."),
        dict(ref="TN-1003", title="Route 12 revised timings on weekdays", type="Schedule change",
             routes="12", area="North Ring", stations="Gandhi Nagar",
             published=_f(d(-3, 10)), vfrom=_f(d(2)), vto=_f(d(9, 23)),
             text="First bus will start at 05:30 and the last bus at 22:00 during the exam period."),
        dict(ref="TN-0990", title="Route 7 stop shifted near Market Square", type="Stop closed",
             routes="7", area="Old Town", stations="Market Square",
             published=_f(d(-12, 9)), vfrom=_f(d(-10)), vto=_f(d(-4, 23)),
             text="Market Square stop closed for festival. Use the temporary stop on Temple Road."),
        dict(ref="TN-1004", title="Route 21 delays near Airport Road junction", type="Delay",
             routes="21, 21K", area="Airport Road", stations="Airport Road Junction",
             published=_f(d(0, 7)), vfrom=_f(d(0, 7)), vto="",
             text="Congestion due to ongoing construction. Delays of 10-15 minutes expected until further notice."),
    ]


def write_demo_page(path=os.path.join("data", "demo_source.html")):
    now_local = datetime.now(config.source_tz)
    articles = "\n".join(ARTICLE.format(**item) for item in sample_items(now_local))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(PAGE.format(articles=articles))
    return path


if __name__ == "__main__":
    print("wrote", write_demo_page())
