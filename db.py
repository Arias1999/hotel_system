"""
db.py — Database helper
------------------------
Supports two ways to configure the connection:

Option A (recommended for Vercel) — single env var:
  DATABASE_URL = postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres

Option B — separate vars:
  SUPABASE_URL = https://PROJECT_REF.supabase.co
  DB_PASSWORD  = your database password
"""

import os
import re
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()


def _get_conn():
    # Option A: full DATABASE_URL provided
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        # Parse manually to avoid urlparse dot-in-username bug
        # Format: postgresql://user:password@host:port/dbname
        m = re.match(r"[^:]+://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", database_url)
        if m:
            user, password, host, port, dbname = m.groups()
            return psycopg2.connect(
                host=host, port=int(port), dbname=dbname,
                user=user, password=password,
                sslmode="require", options="-c search_path=public"
            )

    # Option B: derive from SUPABASE_URL + DB_PASSWORD
    supabase_url = os.environ.get("SUPABASE_URL", "")
    db_password  = os.environ.get("DB_PASSWORD", "")
    m = re.match(r"https://([^.]+)\.supabase\.co", supabase_url)
    if m and db_password:
        ref = m.group(1)
        return psycopg2.connect(
            host="aws-0-ap-southeast-1.pooler.supabase.com",
            port=6543, dbname="postgres",
            user=f"postgres.{ref}",
            password=db_password,
            sslmode="require", options="-c search_path=public"
        )

    raise RuntimeError(
        "No database config found. Set DATABASE_URL or (SUPABASE_URL + DB_PASSWORD)."
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
