"""Keyless public Event Radar, sourced from Ticket Fairy's documented public event API.

The provider API is read-only, requires no account key, and covers *its own*
published events only. A server-side Ticketmaster key (when configured) can
still provide Ticketmaster data through ceyrl_features.call_tm.

All third-party endpoints and redirect policies are fixed and strict, to avoid
SSRF or arbitrary imported event data. Event details are cached inside only the
requester's private database for 30 minutes before explicit user import.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
import ceyrl_music
import ceyrl_gigora

PUBLIC_API = "https://www.ticketfairy.com/api/v1/events/listing"
CACHE_TTL = 300
IMPORT_TTL = 1800
_lock = threading.Lock()
_cache = {}


def _valid_event_url(url):
    if not isinstance(url,str) or len(url)>750:
        return None
    u=urlsplit(url)
    if u.scheme!="https" or u.hostname not in {"www.ticketfairy.com","ticketfairy.com"}:
        return None
    if u.username or u.password or u.port not in (None,443):
        return None
    if not re.fullmatch(r"/event/[A-Za-z0-9_-]{2,90}/?",u.path):
        return None
    return "https://www.ticketfairy.com"+u.path.rstrip("/")


def normalize_public_event(item):
    if not isinstance(item,dict):
        return None
    url=_valid_event_url(item.get("url"))
    if not url:
        return None
    slug=url.rsplit("/",1)[-1]
    starts=str(item.get("startDate") or "")
    if not starts or len(starts)>80:
        return None
    try:
        dt=datetime.fromisoformat(starts.replace("Z","+00:00"))
        if dt.tzinfo is None:
            return None
        utc=dt.astimezone(timezone.utc)
        if utc.year<2025 or utc.year>2040:
            return None
        dttext=utc.isoformat()
        local_date=dt.date().isoformat()
    except (TypeError,ValueError,OverflowError):
        return None
    venue=item.get("venue") or {}
    if not isinstance(venue,dict):
        venue={}
    name=str(item.get("displayName") or item.get("name") or "").strip()[:200]
    if not name:
        return None
    return {
      "id":"tf:"+slug, "name":name,
      "starts_at":dttext, "local_date":local_date,
      "venue":str(venue.get("name") or "")[:200],
      "city":str(venue.get("city") or "")[:120],
      "country":str(venue.get("country") or "").upper()[:100],
      "url":url, "category":"Event", "provider":"Ticket Fairy"
    }


def request_public(query,country):
    """Only approved fixed HTTPS endpoint, no redirect, max 15 public results."""
    params={"search":query,"section_type":"upcoming","sort":"start_date",
            "order":"asc","size":15}
    if country:
        params["country"]=country
    try:
        with httpx.Client(timeout=12,follow_redirects=False) as client:
            response=client.get(PUBLIC_API,params=params,
                                headers={"Accept":"application/json","User-Agent":"Ceyrl-EventRadar/1.0"})
        if response.status_code==429:
            raise HTTPException(429,"Public event provider is rate limited. Please try later.")
        if response.status_code!=200:
            raise HTTPException(502,"Public event search is temporarily unavailable.")
        if len(response.content)>1_500_000:
            raise HTTPException(502,"Event provider returned an oversized response.")
        data=response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError,ValueError,TypeError):
        raise HTTPException(502,"Public event provider could not be reached.")
    if not isinstance(data,dict):
        raise HTTPException(502,"Public event provider returned an invalid response.")
    batch=data.get("data") or {}
    if not isinstance(batch,dict) or not isinstance(batch.get("events"),list):
        raise HTTPException(502,"Public event provider returned an unsupported response.")
    results=[]
    seen=set()
    for row in batch["events"][:60]:
        normalized=normalize_public_event(row)
        if normalized and normalized["id"] not in seen:
            results.append(normalized)
            seen.add(normalized["id"])
        if len(results)>=15:
            break
    return results


def search_public(query,country):
    query=query.strip()
    country=country.strip().upper()
    if len(query)<2 or len(query)>80 or any(ord(x)<32 or ord(x)==127 for x in query):
        raise HTTPException(422,"Enter a valid event or artist name.")
    key=(query.casefold(),country)
    with _lock:
        item=_cache.get(key)
        if item and time.monotonic()<item[0]:
            return [dict(x) for x in item[1]]
    found=request_public(query,country)
    with _lock:
        if len(_cache)>250:
            _cache.clear()
        _cache[key]=(time.monotonic()+CACHE_TTL,found)
    return [dict(x) for x in found]


def _valid_provider_url(url):
    """Strict allowlist for provider links stored in our private import cache."""
    if _valid_event_url(url):
        return True
    if not isinstance(url,str) or len(url)>800:
        return False
    parts=urlsplit(url)
    if parts.scheme!="https" or parts.username or parts.password:
        return False
    if parts.port not in (None,443) or parts.fragment:
        return False
    # Gigora's documented page URLs include a harmless utm_source=ai query.
    # Validate its limited parameters before applying the strict no-query rule
    # to the other third-party sources.
    if parts.hostname in ("gigora.live","www.gigora.live"):
        return bool(ceyrl_gigora._hosted_url(url))
    if parts.query:
        return False
    if parts.hostname=="www.thesportsdb.com":
        return bool(re.fullmatch(r"/event/\d{1,12}",parts.path))
    if parts.hostname=="www.espn.com":
        return bool(re.fullmatch(r"/soccer/match/_/gameId/\d{1,12}",parts.path))
    if parts.hostname=="stungevents.com":
        return bool(re.fullmatch(r"/event/[a-zA-Z0-9_-]{4,135}",parts.path))
    if ceyrl_gigora._hosted_url(url):
        return True
    if ceyrl_music._safe_link(url):
        return True
    return False


def init_cache(db):
    db.execute("""CREATE TABLE IF NOT EXISTS x_radar_public_results(
        external_id TEXT PRIMARY KEY, payload TEXT NOT NULL, observed_at REAL NOT NULL
    )""")


def remember(db,events):
    init_cache(db)
    current=time.time()
    db.execute("DELETE FROM x_radar_public_results WHERE observed_at<?",
               (current-IMPORT_TTL,))
    for item in events:
        ident=item.get("id","")
        if not (re.fullmatch(r"tf:[A-Za-z0-9_-]{2,90}",ident) or
                re.fullmatch(r"sp:(?:ts|es):\d{1,12}",ident) or
                re.fullmatch(r"se:[A-Za-z0-9_-]{4,135}",ident) or
                re.fullmatch(r"td:[A-Za-z0-9_-]{6,70}",ident) or
                re.fullmatch(r"gi:[a-f0-9]{26}",ident)):
            continue
        if not _valid_provider_url(item.get("url")):
            continue
        db.execute("""INSERT INTO x_radar_public_results(external_id,payload,observed_at)
            VALUES(?,?,?) ON CONFLICT(external_id) DO UPDATE SET
            payload=excluded.payload,observed_at=excluded.observed_at""",
            (item["id"],json.dumps(item,ensure_ascii=False),current))
    db.execute("""DELETE FROM x_radar_public_results WHERE external_id NOT IN
        (SELECT external_id FROM x_radar_public_results ORDER BY observed_at DESC LIMIT 150)""")


def lookup(db,external_id):
    if not (re.fullmatch(r"tf:[A-Za-z0-9_-]{2,90}",external_id) or
            re.fullmatch(r"sp:(?:ts|es):\d{1,12}",external_id) or
            re.fullmatch(r"se:[A-Za-z0-9_-]{4,135}",external_id) or
            re.fullmatch(r"td:[A-Za-z0-9_-]{6,70}",external_id) or
            re.fullmatch(r"gi:[a-f0-9]{26}",external_id)):
        raise HTTPException(422,"Invalid event identifier.")
    init_cache(db)
    row=db.execute("""SELECT payload,observed_at FROM x_radar_public_results
          WHERE external_id=?""",(external_id,)).fetchone()
    if not row or (time.time()-row["observed_at"])>IMPORT_TTL:
        raise HTTPException(404,"Search for this event again before importing it.")
    try:
        record=json.loads(row["payload"])
    except (ValueError,TypeError):
        raise HTTPException(409,"Cached event details are invalid. Search again.")
    if record.get("id")!=external_id or not _valid_provider_url(record.get("url")):
        raise HTTPException(409,"Cached event source is invalid. Search again.")
    if not record.get("starts_at") or not record.get("name"):
        raise HTTPException(422,"The provider did not give a verifiable event time. Review the official source and add it manually.")
    return record


def rate_limit(auth_db,connection,user_id,kind,units=1):
    """Persistent per-account and global ceilings for public provider usage."""
    units=max(1,min(15,int(units)))
    stamp=time.time()
    minute=int(stamp//60)
    day=int(stamp//86400)
    # Separate rates for search, watch refresh and import.
    with connection(auth_db,True) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS x_radar_quota(
          user_id TEXT NOT NULL,kind TEXT NOT NULL,day INTEGER NOT NULL,
          minute INTEGER NOT NULL,calls INTEGER NOT NULL,
          PRIMARY KEY(user_id,kind,minute)
        )""")
        db.execute("DELETE FROM x_radar_quota WHERE day<?",(day-1,))
        user_minute=db.execute("SELECT COALESCE(SUM(calls),0) FROM x_radar_quota WHERE user_id=? AND minute=?",
                               (user_id,minute)).fetchone()[0]
        user_day=db.execute("SELECT COALESCE(SUM(calls),0) FROM x_radar_quota WHERE user_id=? AND day=?",
                            (user_id,day)).fetchone()[0]
        global_minute=db.execute("SELECT COALESCE(SUM(calls),0) FROM x_radar_quota WHERE minute=?",
                                 (minute,)).fetchone()[0]
        if user_minute+units>20:
            raise HTTPException(429,"Event Radar limit: up to 20 provider-search units per minute per account.")
        if user_day+units>150:
            raise HTTPException(429,"Event Radar daily limit reached. Try tomorrow.")
        if global_minute+units>105:
            raise HTTPException(429,"Event Radar is busy. Try again in a minute.")
        db.execute("""INSERT INTO x_radar_quota(user_id,kind,day,minute,calls)
          VALUES(?,?,?,?,?) ON CONFLICT(user_id,kind,minute)
          DO UPDATE SET calls=calls+excluded.calls""",(user_id,kind,day,minute,units))
