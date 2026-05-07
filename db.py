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

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS full_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'customer',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
"""


APP_SCHEMA_SQL = """
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

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS full_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'customer',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS rooms (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    price       NUMERIC(10, 2) NOT NULL DEFAULT 0,
    description TEXT,
    image       TEXT,
    category    TEXT NOT NULL DEFAULT 'Standard'
);

ALTER TABLE rooms
    ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS image TEXT,
    ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'Standard';

CREATE TABLE IF NOT EXISTS bookings (
    id               SERIAL PRIMARY KEY,
    user_email       TEXT NOT NULL,
    room_id          INTEGER,
    checkin          DATE NOT NULL DEFAULT CURRENT_DATE,
    checkout         DATE NOT NULL DEFAULT CURRENT_DATE,
    payment_method   TEXT NOT NULL DEFAULT 'Cash',
    payment_status   TEXT NOT NULL DEFAULT 'Pending',
    reference_number TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS user_email TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS room_id INTEGER,
    ADD COLUMN IF NOT EXISTS checkin DATE NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS checkout DATE NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS payment_method TEXT NOT NULL DEFAULT 'Cash',
    ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'Pending',
    ADD COLUMN IF NOT EXISTS reference_number TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS payments (
    id               SERIAL PRIMARY KEY,
    booking_id       INTEGER,
    user_email       TEXT NOT NULL DEFAULT '',
    amount           NUMERIC(10, 2) NOT NULL DEFAULT 0,
    payment_method   TEXT NOT NULL DEFAULT 'Cash',
    payment_status   TEXT NOT NULL DEFAULT 'Pending',
    reference_number TEXT,
    paid_at          TIMESTAMPTZ
);

ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS booking_id INTEGER,
    ADD COLUMN IF NOT EXISTS user_email TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS payment_method TEXT NOT NULL DEFAULT 'Cash',
    ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'Pending',
    ADD COLUMN IF NOT EXISTS reference_number TEXT,
    ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;
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

    is_direct = parsed.hostname.startswith("db.") and parsed.hostname.endswith(".supabase.co")
    is_pooler = "pooler.supabase.com" in parsed.hostname

    if not is_direct and not is_pooler:
        raise RuntimeError(
            "DATABASE_URL must use a Supabase direct host or Supabase pooler host."
        )

    if is_direct and parsed.username != "postgres":
        raise RuntimeError("Direct Supabase DATABASE_URL must use username postgres.")

    if is_pooler and not parsed.username.startswith("postgres."):
        raise RuntimeError("Supabase pooler DATABASE_URL must use username postgres.PROJECT_REF.")

    if is_direct and parsed.port != 5432:
        raise RuntimeError("Direct Supabase DATABASE_URL must use port 5432.")

    if is_pooler and parsed.port not in (5432, 6543):
        raise RuntimeError("Supabase pooler DATABASE_URL must use port 5432 or 6543.")

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["sslmode"] = "require"

    clean_url = urlunparse(parsed._replace(query=urlencode(query)))
    print(f"DATABASE_URL LOADED host={parsed.hostname} port={parsed.port} user={parsed.username}")
    return clean_url


def url_info():
    parsed = urlparse(database_url())
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return {
        "host": parsed.hostname,
        "port": parsed.port,
        "username": parsed.username,
        "direct_connection": (
            parsed.hostname.startswith("db.")
            and parsed.hostname.endswith(".supabase.co")
            and parsed.port == 5432
            and parsed.username == "postgres"
        ),
        "pooler_connection": (
            "pooler.supabase.com" in parsed.hostname
            and parsed.port in (5432, 6543)
            and parsed.username.startswith("postgres.")
        ),
        "sslmode": query.get("sslmode"),
    }


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
        print("DATABASE CONNECTED SUCCESSFULLY")

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


def ensure_app_schema():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(APP_SCHEMA_SQL)
    print("APP DATABASE TABLES READY")


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
