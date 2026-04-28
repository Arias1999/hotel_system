import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            1, 5,
            host=os.environ.get("DB_HOST", "db.zyjqxnnvnpjbgmnmlxns.supabase.co"),
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ.get("DB_NAME", "postgres"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", ""),
            sslmode="require"
        )
    return _pool


from contextlib import contextmanager

@contextmanager
def get_db():
    p = get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)


def fetchall(query, params=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def fetchone(query, params=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()


def execute(query, params=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            conn.commit()


def execute_returning(query, params=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            result = cur.fetchone()
            conn.commit()
            return result
