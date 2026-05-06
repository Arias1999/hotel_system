import os
import traceback
from contextlib import contextmanager
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()


USERS_TABLE_SQL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name  TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT '',
    email      TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,
    is_admin   BOOLEAN NOT NULL DEFAULT FALSE,
    role       TEXT NOT NULL DEFAULT 'customer',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def database_url():
    load_dotenv(override=True)
    raw_url = os.getenv("DATABASE_URL", "").strip()

    if "\n" in raw_url or "\r" in raw_url:
        raise RuntimeError("DATABASE_URL contains a line break. Keep it on one line.")

    if not raw_url:
        raise RuntimeError("DATABASE_URL is missing.")

    parsed = urlparse(raw_url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError("DATABASE_URL must start with postgresql://")

    if not parsed.hostname:
        raise RuntimeError("DATABASE_URL is missing the Supabase host.")

    if not parsed.username:
        raise RuntimeError("DATABASE_URL is missing the database username.")

    if parsed.password in (None, "", "[YOUR-PASSWORD]", "MY_PASSWORD"):
        raise RuntimeError("DATABASE_URL still has a placeholder or missing password.")

    if parsed.hostname.endswith(".supabase.co") and parsed.port not in (5432, 6543):
        raise RuntimeError("Supabase DATABASE_URL must use port 5432 or 6543.")

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["sslmode"] = "require"

    return urlunparse(parsed._replace(query=urlencode(query)))


@contextmanager
def get_db():
    conn = None

    try:
        url = database_url()
        conn = psycopg2.connect(
            url,
            connect_timeout=15,
            options="-c search_path=public",
        )
        print("DATABASE CONNECTED")

        yield conn
        conn.commit()

    except Exception:
        if conn:
            conn.rollback()

        print("DB ERROR:")
        traceback.print_exc()
        raise

    finally:
        if conn:
            conn.close()


def ensure_users_table():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(USERS_TABLE_SQL)
    print("USERS TABLE READY")


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
