import os
import traceback
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def database_url():
    return os.getenv("DATABASE_URL", "").strip()


@contextmanager
def get_db():
    conn = None

    try:
        url = database_url()

        if not url:
            raise RuntimeError("DATABASE_URL is missing.")

        conn = psycopg2.connect(url)

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