"""Ingest a read-only relational database into cognee as factual memory.

Issues SELECT-only queries against DB_INGEST_URL, dumps each table to JSON, and
uploads it to /api/v1/add. Use a read-only DB user; only SELECTs are executed.
"""

import datetime
import decimal
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

from common.cognee_client import cognify, health, upload_files

DB_URL = os.getenv("DB_INGEST_URL")
TABLES = [t.strip() for t in os.getenv("DB_INGEST_TABLES", "").split(",") if t.strip()]
QUERY = os.getenv("DB_INGEST_QUERY", "").strip()
DATASET = os.getenv("DB_DATASET_NAME", "flowly_db")
MAX_ROWS = int(os.getenv("DB_MAX_ROWS_PER_TABLE", "5000"))


def _coerce(value):
    if isinstance(value, (datetime.date, datetime.datetime, decimal.Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return value


def main():
    if not DB_URL:
        print("[database] DB_INGEST_URL not set; skipping.")
        return
    if not TABLES and not QUERY:
        print("[database] set DB_INGEST_TABLES or DB_INGEST_QUERY; skipping.")
        return
    if not health():
        print("[database] cognee API not healthy; aborting.")
        sys.exit(1)

    from sqlalchemy import create_engine, text

    engine = create_engine(DB_URL)
    queries = {"custom_query": QUERY} if QUERY else {t: f'SELECT * FROM "{t}"' for t in TABLES}

    tmpdir = tempfile.mkdtemp(prefix="db_ingest_")
    items = []
    with engine.connect() as conn:
        for name, sql in queries.items():
            print(f"[database] reading '{name}'...")
            result = conn.execute(text(sql))
            cols = list(result.keys())
            rows = []
            for i, row in enumerate(result):
                if i >= MAX_ROWS:
                    print(f"[database] '{name}' truncated at {MAX_ROWS} rows.")
                    break
                rows.append({c: _coerce(v) for c, v in zip(cols, row)})
            out = Path(tmpdir) / f"{name}.json"
            out.write_text(
                json.dumps({"table": name, "columns": cols, "rows": rows}, indent=2, default=str)
            )
            items.append((str(out), f"db__{name}.json"))

    if not items:
        print("[database] nothing extracted.")
        return
    print(f"[database] uploading {len(items)} table dump(s) to dataset '{DATASET}'...")
    upload_files(items, DATASET)
    print("[database] running cognify...")
    cognify(DATASET)
    print("[database] done.")


if __name__ == "__main__":
    main()
