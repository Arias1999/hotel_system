"""
db.py — Database helper module
-------------------------------
Reads a single DATABASE_URL environment variable.
Set this in .env (local) and in Vercel environment variables (production).

Supabase direct connection (port 5432) works on both local and Vercel.
SSL is enforced via sslmode=require.
"""

import os
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not _DATABASE_URL:
    import sys
    print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)

# Append sslmode=require — Supabase rejects unencrypted connections
# sslmode=require — Supabase rejects unencrypted connections
# options=-csearch_path=public — forces all unqualified table names to resolve
# to the public schema, preventing conflicts with Supabase's internal auth.users
_DSN = _DATABASE_URL + ("&" if "?" in _DATABASE_URL else "?") + "sslmode=require&options=-csearch_path%3Dpublic"


@contextmanager
def get_db():
    """Open a connection, yield it, commit/rollback, then close."""
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
