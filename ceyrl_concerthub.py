"""Keyless public Polish concert discovery from ConcertHub's documented JSON-RPC API.

Only the fixed provider endpoint is contacted. Results are event discovery,
NOT real-time ticket availability. Date-only listings are intentionally not
given an invented start time and cannot be auto-imported as timed events.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timezone

import httpx
from fastapi import HTTPException

RPC_URL = "https://concerthub.pl/api/rpc"
CACHE_TTL = 600
_MAX_BYTES = 1_500_000
_slug = re.compile(r"^[a-z0-9][a-z0-9-]{3,129}$")
_cache = {}
_lock = threading.Lock()


def normalize_concerthub(item):
    if not isinstance(item, dict):
        return None
    slug = item.get("slug")
    if not isinstance(slug, str) or not _slug.fullmatch(slug):
        return None
    name = item.get("title") or item.get("artist")
    if not isinstance(name, str) or not name.strip() or len(name) > 250:
        return None
    start = item.get("date")
    if not isinstance(start, str) or len(start) > 35:
        return None
    try:
        local_date = date.fromisoformat(start[:10]).isoformat()
        if local_date < datetime.now(timezone.utc).date().isoformat():
            return None
    except ValueError:
        return None

    # An ISO date is not an exact UTC time. Do not assume local midnight.
    starts_at = ""
    if "T" in start:
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                starts_at = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return {
        "id": "ch:" + slug,
        "name": name.strip()[:200],
        "starts_at": starts_at,
        "local_date": local_date,
        "venue": str(item.get("venue") or "")[:200],
        "city": str(item.get("city") or "")[:120],
        "country": "PL",
        "url": "https://concerthub.pl/en/event/" + slug,
        "category": "Concert",
        "provider": "ConcertHub",
    }


def request_concerthub(query):
    payload = {
        "jsonrpc": "2.0",
        "method": "events.search",
        "params": {"query": query, "page": 1, "per_page": 20},
        "id": 1,
    }
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            response = client.post(RPC_URL, json=payload, headers={
                "Accept": "application/json",
                "User-Agent": "Ceyrl-EventRadar/1.0 (https://github.com/zajkir/C-TicketWave-PRO-V4)",
            })
        if response.status_code == 429:
            raise HTTPException(429, "ConcertHub search is rate-limited; try again shortly.")
        if response.status_code != 200 or len(response.content) > _MAX_BYTES:
            raise HTTPException(502, "ConcertHub public search is unavailable.")
        data = response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(502, "ConcertHub public search could not be reached.")
    if not isinstance(data, dict) or data.get("error"):
        raise HTTPException(502, "ConcertHub returned a provider error.")
    result = data.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("events"), list):
        raise HTTPException(502, "ConcertHub returned an unsupported event listing.")
    output, seen = [], set()
    for item in result["events"][:60]:
        normalized = normalize_concerthub(item)
        if normalized and normalized["id"] not in seen:
            output.append(normalized)
            seen.add(normalized["id"])
        if len(output) >= 20:
            break
    return output


def search_concerthub(query, country=""):
    query = query.strip()
    country = country.strip().upper()
    if country not in ("", "PL"):
        return []
    if len(query) < 2 or len(query) > 80 or any(ord(ch) < 32 or ord(ch) == 127 for ch in query):
        raise HTTPException(422, "Enter a valid concert or artist.")
    key = query.casefold()
    with _lock:
        found = _cache.get(key)
        if found and time.monotonic() < found[0]:
            return [dict(row) for row in found[1]]
    events = request_concerthub(query)
    with _lock:
        if len(_cache) > 250:
            _cache.clear()
        _cache[key] = (time.monotonic() + CACHE_TTL, events)
    return [dict(row) for row in events]
