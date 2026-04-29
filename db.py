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

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# 🔍 DEBUG (visible in Vercel Logs on cold start)
print("DB DEBUG → URL exists:", bool(DATABASE_URL))
print(
    "DB DEBUG → correct user:",
    "postgres.zyjqxnnvnpjbgmnmlxns" in DATABASE_URL
)
print("DB DEBUG → starts with:", DATABASE_URL[:40] if DATABASE_URL else "EMPTY")


@contextmanager
def get_db():
    conn = None
    try:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is missing. Check Vercel Environment Variables.")

        conn = psycopg2.connect(
            DATABASE_URL,
            options="-c search_path=public"
        )

        yield conn
        conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        print("DB ERROR:", str(e))
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