"""
db.py — Database helper
------------------------
Derives the PostgreSQL pooler connection from SUPABASE_URL and SUPABASE_KEY.
No separate DATABASE_URL needed — just set the two Supabase keys.

Environment variables (same ones used by supabase-js):
  SUPABASE_URL  : https://PROJECT_REF.supabase.co
  SUPABASE_KEY  : your publishable/anon or service role key
  DB_PASSWORD   : your Supabase database password (Settings → Database → Reveal)
"""

import os
import re
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_DB_PASSWORD  = os.environ.get("DB_PASSWORD", "")

# Extract project ref from https://PROJECT_REF.supabase.co
_match = re.match(r"https://([^.]+)\.supabase\.co", _SUPABASE_URL)
_PROJECT_REF = _match.group(1) if _match else ""


def _get_conn():
    if not _PROJECT_REF or not _DB_PASSWORD:
        raise RuntimeError(
            "Set SUPABASE_URL (https://PROJECT_REF.supabase.co) "
            "and DB_PASSWORD in your environment variables."
        )
    return psycopg2.connect(
        host=f"aws-0-ap-southeast-1.pooler.supabase.com",
        port=6543,
        dbname="postgres",
        user=f"postgres.{_PROJECT_REF}",
        password=_DB_PASSWORD,
        sslmode="require",
        options="-c search_path=public",
    )


@contextmanager
def get_db():
    conn = None
    try:
        conn = _get_conn()
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        traceback.print_exc()
        raise
    finally:
        if conn:
            conn.close()


def fetchone(query, params=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetchall(query, params=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def execute(query, params=()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


def execute_returning(query, params=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()
