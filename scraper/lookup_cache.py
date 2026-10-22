"""
scraper/lookup_cache.py — SQLite caching for company lookups.

TTL Rules:
- 30 days for basic identity (name, city, mobile, website).
- 7 days for people, leadership, services, and company size.
- 2 days (1-3 days) for "not found" or "ambiguous" results.
- Parameter `refresh=True` bypasses cache read and triggers fresh extraction.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
from typing import Any, Optional

logger = logging.getLogger(__name__)

TTL_DAYS_BASIC = 30
TTL_DAYS_INTEL = 7
TTL_DAYS_NOT_FOUND = 2


def _get_db_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lookup_cache (
            cache_key TEXT PRIMARY KEY,
            place_id TEXT,
            domain TEXT,
            status TEXT,
            data_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lookup_cache_place_id ON lookup_cache(place_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lookup_cache_domain ON lookup_cache(domain)")
    conn.commit()
    return conn


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def get_cached_lookup(
    cache_key: str,
    db_path: Optional[str] = None,
    refresh: bool = False,
) -> Optional[dict[str, Any]]:
    """
    Retrieve cached lookup result if valid and not expired.
    Returns None if cache miss, expired, or if refresh=True.
    """
    if refresh:
        logger.info("[Cache] Bypass requested (refresh=True) for '%s'", cache_key)
        return None

    if not db_path:
        db_path = str(os.path.join(os.path.dirname(__file__), "..", "data", "archscale.db"))

    norm_key = " ".join(cache_key.lower().split())

    try:
        with _get_db_connection(db_path) as conn:
            cur = conn.execute(
                "SELECT data_json, expires_at FROM lookup_cache WHERE cache_key = ?",
                (norm_key,),
            )
            row = cur.fetchone()
            if not row:
                return None

            expires_at_str = row["expires_at"]
            if expires_at_str:
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
                if _now_utc() > expires_at:
                    logger.info("[Cache] Expired entry for '%s'", norm_key)
                    return None

            data = json.loads(row["data_json"])
            logger.info("[Cache] Hit for '%s' (Status: %s)", norm_key, data.get("match_status"))
            return data
    except Exception as exc:
        logger.debug("[Cache] Read error for '%s': %s", norm_key, exc)
        return None


def save_cached_lookup(
    cache_key: str,
    result: dict[str, Any],
    db_path: Optional[str] = None,
    place_id: Optional[str] = None,
    domain: Optional[str] = None,
) -> None:
    """
    Save lookup result to SQLite cache with appropriate TTL.
    """
    if not db_path:
        db_path = str(os.path.join(os.path.dirname(__file__), "..", "data", "archscale.db"))

    norm_key = " ".join(cache_key.lower().split())
    status = result.get("match_status", "matched")

    # Determine TTL based on outcome
    if status in ("not_found", "ambiguous", "error"):
        ttl_days = TTL_DAYS_NOT_FOUND
    elif result.get("people") or (result.get("ceo") and result["ceo"].get("name", {}).get("value") != "not found"):
        ttl_days = TTL_DAYS_INTEL
    else:
        ttl_days = TTL_DAYS_BASIC

    expires_at = _now_utc() + datetime.timedelta(days=ttl_days)

    try:
        with _get_db_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO lookup_cache (cache_key, place_id, domain, status, data_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    place_id = excluded.place_id,
                    domain = excluded.domain,
                    status = excluded.status,
                    data_json = excluded.data_json,
                    created_at = CURRENT_TIMESTAMP,
                    expires_at = excluded.expires_at
                """,
                (
                    norm_key,
                    place_id,
                    domain,
                    status,
                    json.dumps(result, ensure_ascii=False),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
            logger.info("[Cache] Saved entry for '%s' (TTL: %d days)", norm_key, ttl_days)
    except Exception as exc:
        logger.debug("[Cache] Save error for '%s': %s", norm_key, exc)
