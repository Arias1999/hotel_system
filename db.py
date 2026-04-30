"""
db.py — Database helper
Uses psycopg2 to connect to PostgreSQL using DATABASE_URL.
"""

import os
import traceback
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Get DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# AUTO FIX: removes wrong format if DATABASE_URL=postgresql://... was stored literally
if DATABASE_URL.startswith("DATABASE_URL="):
    DATABASE_URL = DATABASE_URL.replace("DATABASE_URL=", "", 1)

print("DB DEBUG → URL exists:", bool(DATABASE_URL))
print("DB DEBUG → starts with:", DATABASE_URL[:40] if DATABASE_URL else "EMPTY")


@contextmanager
def get_db():
    conn = None

    try:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is missing. Check your .env file.")

        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            options="-c search_path=public"
        )

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


def fetchone(query, params=()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetchall(query, params=()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def execute(query, params=()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


def execute_returning(query, params=()):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()