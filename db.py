"""
db.py — Database helper module for hotel_system
------------------------------------------------
On Vercel (serverless), each function invocation is isolated —
persistent connection pools don't work because the process is
torn down after every request. We open one connection per request
and close it when done.

Environment variables:
  ENV                  : "local" or "production"
  DATABASE_URL_DIRECT  : Direct host, port 5432  — used when ENV=local
  DATABASE_URL_POOLER  : Supabase pooler, port 6543 — used when ENV=production
"""

import os
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# ── URL SELECTION ─────────────────────────────────────
_ENV = os.environ.get("ENV", "local").strip().lower()

if _ENV == "production":
    _DATABASE_URL = os.environ.get("DATABASE_URL_POOLER", "")
else:
    _DATABASE_URL = os.environ.get("DATABASE_URL_DIRECT", "")

# Append sslmode=require — Supabase rejects unencrypted connections
_DSN = _DATABASE_URL + ("&" if "?" in _DATABASE_URL else "?") + "sslmode=require"


# ── CONNECTION PER REQUEST ────────────────────────────
# On serverless, we open a fresh connection for each request and
# close it immediately after. No pool — Vercel has no persistent process.

@contextmanager
def get_db():
    """Open a connection, yield it, commit/rollback, then close."""
    if not _DATABASE_URL:
        raise RuntimeError(
            f"No DATABASE_URL set for ENV='{_ENV}'. "
            "Add DATABASE_URL_DIRECT (local) or DATABASE_URL_POOLER (production) "
            "to your environment variables."
        )
    conn = None
    try:
        conn = psycopg2.connect(_DSN)
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


# ── QUERY HELPERS ─────────────────────────────────────

def fetchone(query, params=()):
    """Return the first matching row as a dict, or None."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetchall(query, params=()):
    """Return all matching rows as a list of dicts."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def execute(query, params=()):
    """Run an INSERT / UPDATE / DELETE."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


def execute_returning(query, params=()):
    """Run INSERT ... RETURNING and return the first row as a dict."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()
