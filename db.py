"""
db.py — Database helper module
-------------------------------
Reads DATABASE_URL from environment.

Local (.env):    use direct connection  port 5432
Vercel (prod):   use transaction pooler port 6543

Set DATABASE_URL in Vercel environment variables to the pooler URL:
  postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
"""

import os
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _get_conn():
    """Parse DATABASE_URL and connect using keyword args.
    urlparse splits 'postgres.PROJECT_REF' username correctly only
    when we extract it from the raw URL string.
    """
    # urlparse handles user:password@host:port/db correctly
    # but usernames with dots (postgres.ref) need the netloc parsed manually
    url = urlparse(_DATABASE_URL)
    # url.username lowercases and stops at '.' — use raw netloc instead
    netloc = url.netloc  # user:password@host:port
    userinfo, hostinfo = netloc.rsplit("@", 1)
    if ":" in userinfo:
        username, password = userinfo.split(":", 1)
    else:
        username, password = userinfo, ""
    if ":" in hostinfo:
        host, port_str = hostinfo.rsplit(":", 1)
        port = int(port_str)
    else:
        host, port = hostinfo, 5432
    dbname = url.path.lstrip("/")

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=username,
        password=password,
        sslmode="require",
        options="-c search_path=public",
    )


@contextmanager
def get_db():
    """Open a connection, yield it, commit/rollback, then close."""
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
