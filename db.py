"""
db.py — Database helper module for hotel_system
------------------------------------------------
Handles connection pooling and query execution against
a PostgreSQL (Supabase) database using psycopg2.

Environment variables read:
  ENV                  : "local" or "production"
  DATABASE_URL_DIRECT  : Direct connection (port 5432) — used when ENV=local
  DATABASE_URL_POOLER  : Transaction pooler (port 6543) — used when ENV=production
"""

import os
import traceback
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# ── URL SELECTION ─────────────────────────────────────
# Choose the correct connection string based on the ENV variable.
# - local  → direct connection (port 5432), no pooler overhead
# - production → transaction pooler (port 6543), required on Vercel
#   because serverless functions can't hold persistent connections

_ENV = os.environ.get("ENV", "local").strip().lower()

if _ENV == "production":
    _DATABASE_URL = os.environ.get("DATABASE_URL_POOLER")
else:
    _DATABASE_URL = os.environ.get("DATABASE_URL_DIRECT")

if not _DATABASE_URL:
    raise RuntimeError(
        f"No database URL found for ENV='{_ENV}'. "
        "Set DATABASE_URL_DIRECT (local) or DATABASE_URL_POOLER (production)."
    )

# Append sslmode=require so all connections are encrypted.
# Supabase enforces SSL; without this the connection is rejected.
_DSN = _DATABASE_URL + ("&" if "?" in _DATABASE_URL else "?") + "sslmode=require"

# ── CONNECTION POOL ───────────────────────────────────
# SimpleConnectionPool keeps between 1 and 10 open connections.
# Connections are borrowed (getconn) and returned (putconn) per request,
# avoiding the overhead of opening a new connection on every query.

_pool = None


def get_pool():
    """Initialise the connection pool once and reuse it across requests."""
    global _pool
    if _pool is None:
        try:
            _pool = psycopg2.pool.SimpleConnectionPool(1, 10, _DSN)
        except psycopg2.OperationalError as e:
            traceback.print_exc()
            raise RuntimeError(f"Failed to create connection pool: {e}") from e
    return _pool


# ── CONTEXT MANAGER ───────────────────────────────────
# Using a context manager ensures:
#   - commit is called on success
#   - rollback is called on any exception (prevents dirty state)
#   - the connection is always returned to the pool (putconn in finally)

@contextmanager
def get_db():
    """Borrow a connection from the pool, yield it, then return it."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── QUERY HELPERS ─────────────────────────────────────
# RealDictCursor makes every row a dict keyed by column name,
# so callers can do row["email"] instead of row[0].

def fetchone(query, params=()):
    """Execute a SELECT and return the first row as a dict, or None."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetchall(query, params=()):
    """Execute a SELECT and return all rows as a list of dicts."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def execute(query, params=()):
    """Execute an INSERT / UPDATE / DELETE with no return value."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


def execute_returning(query, params=()):
    """Execute an INSERT ... RETURNING and return the first row as a dict."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()
