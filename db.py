"""
db.py — Database helper using supabase-py
------------------------------------------
Uses Supabase REST API. No database password needed.

Environment variables:
  SUPABASE_URL : https://zyjqxnnvnpjbgmnmlxns.supabase.co
  SUPABASE_KEY : your anon/publishable key
"""

import os
import traceback
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_url = os.environ.get("SUPABASE_URL", "")
_key = os.environ.get("SUPABASE_KEY", "")

supabase: Client = create_client(_url, _key)


def fetchone(query, params=()):
    result = supabase.rpc("execute_sql", {"query": _bind(query, params)}).execute()
    rows = result.data
    return rows[0] if rows else None


def fetchall(query, params=()):
    result = supabase.rpc("execute_sql", {"query": _bind(query, params)}).execute()
    return result.data or []


def execute(query, params=()):
    supabase.rpc("execute_sql", {"query": _bind(query, params)}).execute()


def execute_returning(query, params=()):
    result = supabase.rpc("execute_sql", {"query": _bind(query, params)}).execute()
    rows = result.data
    return rows[0] if rows else None


def _bind(query, params):
    """Replace %s placeholders with safely quoted values."""
    if not params:
        return query
    parts = query.split("%s")
    if len(parts) - 1 != len(params):
        raise ValueError("Parameter count mismatch")
    out = parts[0]
    for i, val in enumerate(params):
        out += _quote(val) + parts[i + 1]
    return out


def _quote(val):
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    return "'" + str(val).replace("'", "''") + "'"
