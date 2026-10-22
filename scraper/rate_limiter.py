"""
scraper/rate_limiter.py — In-memory & SQLite rate limiting and daily quota enforcement.

Enforces:
1. Per-IP rate limiting (e.g. 30 requests per minute).
2. Daily cap on paid calls (Google Places API, OpenRouter API).
3. In-flight lookup deduplication for the same company.
4. Returns 429 HTTP status with clear error messages when limits are exceeded.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import sqlite3
import time
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

# Max requests per minute per IP
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

# Daily caps on paid API calls
DAILY_PLACES_CAP = int(os.getenv("DAILY_PLACES_CAP", "1000"))
DAILY_OPENROUTER_CAP = int(os.getenv("DAILY_OPENROUTER_CAP", "500"))

# In-memory sliding window for IP rate limiting: ip -> list of float timestamps
_ip_request_timestamps: dict[str, list[float]] = {}
_ip_lock = asyncio.Lock()

# In-memory tracking for in-flight lookups: normalised_name -> asyncio.Task
_in_flight_tasks: dict[str, asyncio.Task] = {}
_in_flight_lock = asyncio.Lock()


class QuotaExceededError(Exception):
    """Raised when rate limit or daily paid quota is exceeded."""
    def __init__(self, message: str, status_code: int = 429) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def check_ip_rate_limit(client_ip: str) -> None:
    """
    Check if client_ip has exceeded RATE_LIMIT_PER_MINUTE in the last 60 seconds.
    Raises QuotaExceededError if limit is reached.
    """
    if not client_ip:
        return

    now = time.time()
    cutoff = now - 60.0

    async with _ip_lock:
        timestamps = _ip_request_timestamps.setdefault(client_ip, [])
        # Evict timestamps older than 60s
        _ip_request_timestamps[client_ip] = [t for t in timestamps if t > cutoff]

        if len(_ip_request_timestamps[client_ip]) >= RATE_LIMIT_PER_MINUTE:
            logger.warning("[RateLimit] IP %s exceeded limit of %d req/min", client_ip, RATE_LIMIT_PER_MINUTE)
            raise QuotaExceededError(
                f"Rate limit exceeded: maximum {RATE_LIMIT_PER_MINUTE} requests per minute allowed.",
                status_code=429,
            )

        _ip_request_timestamps[client_ip].append(now)


def _get_today_date_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _init_usage_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_api_usage (
            usage_date TEXT PRIMARY KEY,
            places_calls INTEGER DEFAULT 0,
            openrouter_calls INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def check_and_increment_places_quota(db_path: Optional[str] = None) -> None:
    """
    Check if the daily cap for Google Places API calls has been exceeded.
    Increments the counter if within quota, otherwise raises QuotaExceededError.
    """
    if not db_path:
        db_path = str(os.path.join(os.path.dirname(__file__), "..", "data", "archscale.db"))

    today = _get_today_date_str()
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            _init_usage_table(conn)
            cur = conn.execute(
                "SELECT places_calls FROM daily_api_usage WHERE usage_date = ?", (today,)
            )
            row = cur.fetchone()
            current = row[0] if row else 0

            if current >= DAILY_PLACES_CAP:
                logger.warning("[Quota] Daily Places API cap of %d exceeded on %s", DAILY_PLACES_CAP, today)
                raise QuotaExceededError(
                    f"Daily paid quota for Google Places searches exceeded ({DAILY_PLACES_CAP} calls/day).",
                    status_code=429,
                )

            conn.execute(
                """
                INSERT INTO daily_api_usage (usage_date, places_calls, openrouter_calls)
                VALUES (?, 1, 0)
                ON CONFLICT(usage_date) DO UPDATE SET
                    places_calls = places_calls + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (today,),
            )
            conn.commit()
    except QuotaExceededError:
        raise
    except Exception as exc:
        logger.debug("[Quota] Could not update places quota in DB: %s", exc)


def check_and_increment_openrouter_quota(db_path: Optional[str] = None) -> None:
    """
    Check if the daily cap for OpenRouter LLM calls has been exceeded.
    Increments the counter if within quota, otherwise raises QuotaExceededError.
    """
    if not db_path:
        db_path = str(os.path.join(os.path.dirname(__file__), "..", "data", "archscale.db"))

    today = _get_today_date_str()
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            _init_usage_table(conn)
            cur = conn.execute(
                "SELECT openrouter_calls FROM daily_api_usage WHERE usage_date = ?", (today,)
            )
            row = cur.fetchone()
            current = row[0] if row else 0

            if current >= DAILY_OPENROUTER_CAP:
                logger.warning("[Quota] Daily OpenRouter cap of %d exceeded on %s", DAILY_OPENROUTER_CAP, today)
                raise QuotaExceededError(
                    f"Daily paid quota for OpenRouter LLM extractions exceeded ({DAILY_OPENROUTER_CAP} calls/day).",
                    status_code=429,
                )

            conn.execute(
                """
                INSERT INTO daily_api_usage (usage_date, places_calls, openrouter_calls)
                VALUES (?, 0, 1)
                ON CONFLICT(usage_date) DO UPDATE SET
                    openrouter_calls = openrouter_calls + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (today,),
            )
            conn.commit()
    except QuotaExceededError:
        raise
    except Exception as exc:
        logger.debug("[Quota] Could not update OpenRouter quota in DB: %s", exc)


async def execute_deduplicated_lookup(
    key: str,
    coroutine_func: Callable[[], Coroutine[Any, Any, dict[str, Any]]],
) -> dict[str, Any]:
    """
    Deduplicate in-flight lookups for the same key.
    If a lookup for `key` is currently running, subsequent requests wait for that task
    and return the identical result without repeating network calls.
    """
    norm_key = " ".join(key.lower().split())

    async with _in_flight_lock:
        existing_task = _in_flight_tasks.get(norm_key)
        if existing_task and not existing_task.done():
            logger.info("[Deduplication] Awaiting existing in-flight lookup for '%s'", norm_key)
            task_to_await = existing_task
        else:
            # Launch new task
            task = asyncio.create_task(coroutine_func())
            _in_flight_tasks[norm_key] = task
            task_to_await = task

    try:
        return await task_to_await
    finally:
        async with _in_flight_lock:
            # Clean up finished task
            if norm_key in _in_flight_tasks and _in_flight_tasks[norm_key].done():
                del _in_flight_tasks[norm_key]
