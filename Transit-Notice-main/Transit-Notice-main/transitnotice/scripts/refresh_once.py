"""Manual refresh from the command line:  python -m scripts.refresh_once"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config  # noqa: E402
from db import open_db  # noqa: E402
from services.refresh import refresh_all  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = open_db(config.DB_PATH)
    for r in refresh_all(conn):
        print(f"{r.source_key}: {r.outcome} new={r.new} revised={r.revised} unchanged={r.unchanged} "
              f"withdrawn={r.withdrawn} skipped={r.skipped} {r.error}")
