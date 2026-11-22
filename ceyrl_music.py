"""Ceyrl Event Radar: read-only multi-artist concert discovery.

StungEvents publishes a documented unauthenticated /search endpoint. Optional
Tickets.dev /v1/events (requires SERVER key, free discovery with an account)
indexes several major ticket platforms. Never fabricate events or extract
ticket availability from an event catalog; those are separate concerns.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

STUNG_SEARCH = "https://api.stungevents.com/search"
TICKETS_DEV_EVENTS = "https://api.tickets.dev/v1/events"
_CACHE_TTL = 600
_LOCK = threading.Lock()
_CACHE = {}
_MAX_RESPONSE = 1_800_000
_COUNTRIES = {
  "SK":"Slovakia","CZ":"Czechia","DE":"Germany","AT":"Austria",
  "PL":"Poland","GB":"United Kingdom","US":"United States",
  "FR":"France","IT":"Italy","ES":"Spain","NL":"Netherlands",
  "IE":"Ireland","BE":"Belgium","CH":"Switzerland","CA":"Canada"
}
_MUSIC = ("concert","festival","music","tour","live","gig","rock","pop",
          "rap","hip-hop","metal","k-pop","jazz","blues")
_SPORT = ("sport","football","soccer","rugby","nba","nfl","cricket","baseball","basketball")
_ALLOWED_EVENT_HOSTS = (
    "ticketmaster.com","ticketmaster.co.uk","ticketmaster.de","ticketmaster.fr",
    "ticketmaster.es","ticketmaster.it","ticketmaster.cz","ticketmaster.ca",
    "ticketmaster.com.au","axs.com","seatgeek.com","stubhub.com",
    "vividseats.com","viagogo.com","viagogo.co.uk",
    "ticketweb.com","tickets.stung_events.invalid",
    "stungevents.com"
)

def _parse_datetime(text):
    if not isinstance(text,str) or len(text)>60:
        return "", ""
    try:
        moment=datetime.fromisoformat(text.strip().replace("Z","+00:00"))
        if moment.tzinfo is None:
            return "", moment.date().isoformat()
        utc=moment.astimezone(timezone.utc)
        return utc.isoformat(), moment.date().isoformat()
    except (TypeError,ValueError,OverflowError):
        return "", ""

def _future(date_string):
    try:
        return datetime.strptime(date_string,"%Y-%m-%d").date()>=(
            datetime.now(timezone.utc).date()-timedelta(days=1))
    except (TypeError,ValueError):
        return False

def _cc_ok(requested,country):
    if not requested:
        return True
    if not country:
        return False
    country=str(country).strip().casefold()
    keys={requested.casefold(),_COUNTRIES.get(requested,"").casefold()}
    if requested=="GB":keys.update(("uk","england","scotland","wales","great britain"))
    if requested=="CZ":keys.add("czech republic")
    if requested=="US":keys.update(("usa","united states of america"))
    return country in keys

def _safe_link(url):
    if not isinstance(url,str) or len(url)>900:
        return ""
    try:
        u=urlsplit(url)
        if u.scheme!="https" or not u.hostname or u.username or u.password:
            return ""
        if u.port not in (None,443):
            return ""
        host=u.hostname.lower()
        if host in _ALLOWED_EVENT_HOSTS or host.endswith(".ticketmaster.com"):
            return url
    except ValueError:
        pass
    return ""

def _cat_allowed(cat,kind):
    cat=str(cat or "").casefold().strip()
    if kind=="sports":
        return False
    if kind!="music":
        return True
    if not cat:
        return True
    if any(x in cat for x in _SPORT):
        return False
    return any(x in cat for x in _MUSIC)

def stung_event(item,country="",kind="all"):
    if not isinstance(item,dict):
        return None
    slug=str(item.get("slug") or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{4,135}",slug):
        return None
    name=str(item.get("title") or item.get("name") or "").strip()[:200]
    if not name:
        return None
    typ=str(item.get("category") or "")
    if not _cat_allowed(typ,kind):
        return None
    utc,date=_parse_datetime(item.get("start_utc") or item.get("starts_at") or
                              item.get("datetime") or item.get("startDate"))
    if not date or not _future(date):
        return None
    cc=str(item.get("country") or item.get("country_name") or "").strip()[:100]
    if not _cc_ok(country,cc):
        return None
    return {
        "id":"se:"+slug,"name":name,"starts_at":utc,"local_date":date,
        "venue":str(item.get("venue_name") or item.get("venue") or "")[:200],
        "city":str(item.get("city") or "")[:120],
        "country":cc,"category":"Concert" if "concert" in typ.casefold() else
            "Festival" if "festival" in typ.casefold() else (typ[:60] or "Event"),
        "url":"https://stungevents.com/event/"+slug,
        "provider":"StungEvents",
    }

def tickets_dev_event(item,country="",kind="all"):
    if not isinstance(item,dict):
        return None
    uid=str(item.get("id") or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{6,70}",uid):
        return None
    venue=item.get("venue") or {}
    if not isinstance(venue,dict):
        venue={}
    cc=str(venue.get("country") or "")[:80]
    if not _cc_ok(country,cc):
        return None
    title=str(item.get("name") or "").strip()[:200]
    if not title:
        return None
    utc,date=_parse_datetime(item.get("eventDateUtc") or "")
    if not date:
        # Explicit local time without UTC cannot be safely imported.
        _,date=_parse_datetime(item.get("eventDateLocal") or "")
    if not date or not _future(date):
        return None
    original_local=item.get("eventDateLocal") or ""
    _,local_date=_parse_datetime(original_local)
    sources=item.get("sources") or []
    if not isinstance(sources,list):
        sources=[]
    url=""
    for row in sources:
        if not isinstance(row,dict):continue
        candidate=_safe_link(row.get("url"))
        if not candidate:continue
        # Prefer direct primary ticket provider when available.
        if row.get("marketplace") in ("ticketmaster","axs"):
            url=candidate
            break
        if not url:
            url=candidate
    if not url:
        return None
    # Catalog does not supply a reliable category; no speculative sports
    # classification. Music/all searches may show mixed events from sources.
    return {
        "id":"td:"+uid,"name":title,"starts_at":utc,
        "local_date":local_date or date,
        "venue":str(venue.get("name") or "")[:200],
        "city":str(venue.get("city") or "")[:120],
        "country":cc,"category":"Event","url":url,
        "provider":"Tickets.dev",
    }

def _get_json(url,params,headers=None):
    if url not in (STUNG_SEARCH,TICKETS_DEV_EVENTS):
        raise ValueError("Unsupported music source")
    with httpx.Client(timeout=11,follow_redirects=False) as client:
        response=client.get(url,params=params,headers={
            "Accept":"application/json",
            "User-Agent":"Ceyrl-EventRadar/1.0",
            **(headers or {})
        })
    if response.status_code!=200:
        raise ValueError("Music provider unavailable")
    if len(response.content)>_MAX_RESPONSE:
        raise ValueError("Oversized music response")
    result=response.json()
    if not isinstance(result,dict):
        raise ValueError("Invalid music response")
    return result

def _search_stung(query,country,kind):
    payload=_get_json(STUNG_SEARCH,{"q":query})
    if payload.get("ok") is False:
        raise ValueError("StungEvents rejected search")
    items=payload.get("events")
    if not isinstance(items,list):
        raise ValueError("StungEvents response format unsupported")
    out=[]
    for row in items[:90]:
        record=stung_event(row,country,kind)
        if record:
            out.append(record)
    return out[:20]

def _search_tickets_dev(query,country,kind):
    key=os.getenv("CTW_TICKETS_DEV_API_KEY","").strip()
    if not key:
        return []
    data=_get_json(TICKETS_DEV_EVENTS,{"query":query,"pageSize":30},
                   {"x-api-key":key})
    items=data.get("events")
    if not isinstance(items,list):
        raise ValueError("Tickets.dev response format unsupported")
    out=[]
    for item in items[:40]:
        record=tickets_dev_event(item,country,kind)
        if record:
            out.append(record)
    return out[:25]

def _distinct(rows):
    out=[]
    seen_ids=set()
    seen_events=set()
    for item in rows:
        ident=item["id"]
        # Single-source and cross-source ID deduplication.
        if ident in seen_ids:
            continue
        stem=re.sub(r"[^a-z0-9]","",item["name"].casefold())
        city=re.sub(r"[^a-z0-9]","",item.get("city","").casefold())
        day=item.get("local_date","")
        signature=(stem,day,city)
        if stem and day and signature in seen_events:
            continue
        seen_ids.add(ident)
        seen_events.add(signature)
        out.append(item)
    return out

def search(query,country="",kind="all"):
    key=(query.casefold().strip(),country.upper().strip(),kind,
         bool(os.getenv("CTW_TICKETS_DEV_API_KEY","").strip()))
    with _LOCK:
        old=_CACHE.get(key)
        if old and old[0]>time.monotonic():
            return [dict(x) for x in old[1]],dict(old[2])
    events=[]
    sources=[]
    warnings=[]
    try:
        events += _search_stung(query,country,kind)
        sources.append("StungEvents")
    except (httpx.HTTPError,ValueError,TypeError):
        warnings.append("StungEvents event catalog unavailable")
    if key[3]:
        try:
            events += _search_tickets_dev(query,country,kind)
            sources.append("Tickets.dev")
        except (httpx.HTTPError,ValueError,TypeError):
            warnings.append("Tickets.dev event catalog unavailable")
    result=_distinct(events)[:35]
    diag={"checked":sources,"errors":warnings,
          "status":"ok" if sources else "unavailable"}
    with _LOCK:
        if len(_CACHE)>200:
            _CACHE.clear()
        _CACHE[key]=(time.monotonic()+_CACHE_TTL,result,diag)
    return [dict(x) for x in result],dict(diag)
