"""Apply migrations/0006_line_items.sql to the Supabase database.

Same pattern as the earlier rollouts: read DATABASE_URL from the root .env
and execute the migration with psycopg2. Idempotent (IF NOT EXISTS), so it
is safe to run more than once.
"""
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0006_line_items.sql"

load_dotenv(ROOT / ".env")


def main() -> int:
    import os

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set (expected in root .env)")
        return 1

    sql = MIGRATION.read_text(encoding="utf-8")
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("OK: 0006_line_items.sql applied (invoices.line_items column).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

