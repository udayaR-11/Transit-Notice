"""Practice the live mentor challenges against the demo source page (data/demo_source.html).

  python scripts/mentor_challenge.py extend-outage     # +24h on the outage (TN-1002)
  python scripts/mentor_challenge.py no-end-date       # remove the end date of TN-1001
  python scripts/mentor_challenge.py withdraw          # delete TN-1003 from the page
  python scripts/mentor_challenge.py break-layout      # simulate a changed page layout
  python scripts/mentor_challenge.py reset             # regenerate the original demo page
Then press "Refresh now" in /admin (or wait for the scheduler) and watch the dashboard.
"""
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_demo_source import write_demo_page  # noqa: E402

PATH = os.path.join("data", "demo_source.html")


def _read():
    with open(PATH, encoding="utf-8") as fh:
        return fh.read()


def _write(html):
    with open(PATH, "w", encoding="utf-8") as fh:
        fh.write(html)


def _article(html, ref):
    m = re.search(rf'<article class="advisory" data-ref="{ref}">.*?</article>', html, re.S)
    return m


def main(cmd):
    if cmd == "reset":
        print("wrote", write_demo_page()); return
    html = _read()
    if cmd == "extend-outage":
        m = _article(html, "TN-1002")
        block = m.group(0)
        end = re.search(r'<span class="valid-to">(.*?)</span>', block).group(1)
        new_end = (datetime.strptime(end, "%d %b %Y %H:%M") + timedelta(hours=24)).strftime("%d %b %Y %H:%M")
        block2 = block.replace(f'<span class="valid-to">{end}</span>', f'<span class="valid-to">{new_end}</span>')
        _write(html.replace(block, block2)); print(f"outage end {end} -> {new_end}")
    elif cmd == "no-end-date":
        m = _article(html, "TN-1001"); block = m.group(0)
        block2 = re.sub(r'<span class="valid-to">.*?</span>', '<span class="valid-to"></span>', block)
        _write(html.replace(block, block2)); print("TN-1001 now has no end date")
    elif cmd == "withdraw":
        m = _article(html, "TN-1003"); _write(html.replace(m.group(0), "")); print("TN-1003 removed from page")
    elif cmd == "break-layout":
        _write(html.replace('id="advisories"', 'id="notices-v2"')); print("layout changed")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
