"""Gigora keyless concert tour dates for Ceyrl Event Radar.

The Gigora documented read-only GET endpoint returns upcoming shows by artist,
without requiring a per-user or server API key. This is a limited external
catalog, not a guarantee of ticket availability or tour announcements.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qsl

import httpx

BASE_URL="https://gigora.live/api/ai/events"
_CACHED={}
_MUTEX=threading.Lock()
_CACHE_SECONDS=360

COUNTRIES={
    "SK":"Slovakia","CZ":"Czechia","DE":"Germany","AT":"Austria","PL":"Poland",
    "GB":"United Kingdom","US":"United States","FR":"France","IT":"Italy",
    "ES":"Spain","NL":"Netherlands","BE":"Belgium","CH":"Switzerland",
    "CA":"Canada","AU":"Australia","IE":"Ireland","HU":"Hungary",
}

def _as_text(value,limit=150):
    return str(value).strip()[:limit] if value is not None else ""

def _hosted_url(raw):
    """Accept only Gigora's own HTTPS pages, with documented UTM source."""
    if not isinstance(raw,str) or len(raw)>950:
        return None
    try:
        parts=urlsplit(raw)
        if (parts.scheme!="https" or parts.hostname not in {"gigora.live","www.gigora.live"}
             or parts.port not in (None,443) or parts.username or parts.password
             or parts.fragment or not parts.path.startswith("/")
             or parts.path in ("","/") or parts.path.startswith("/api/")):
            return None
        if parts.query:
            args=parse_qsl(parts.query,keep_blank_values=True)
            if any(k not in ("utm_source","utm_medium","utm_campaign") or len(v)>120 for k,v in args):
                return None
        return raw
    except ValueError:
        return None

def _future_iso(value):
    if not isinstance(value,str) or len(value)>72:
        return "", ""
    try:
        original=datetime.fromisoformat(value.replace("Z","+00:00"))
        if original.tzinfo is None:
            return "", original.date().isoformat()
        utc=original.astimezone(timezone.utc)
        if utc < datetime.now(timezone.utc)-timedelta(hours=36):
            return "", ""
        return utc.isoformat(),original.date().isoformat()
    except (ValueError,TypeError,OverflowError):
        return "", ""

def _place(record):
    venue=record.get("venue") or {}
    if isinstance(venue,dict):
        location=venue.get("location") or {}
        if not isinstance(location,dict):location={}
        return (
          _as_text(venue.get("name") or venue.get("title"),200),
          _as_text(record.get("city") or venue.get("city") or location.get("city"),120),
          _as_text(record.get("country") or venue.get("country") or location.get("country"),100)
        )
    return (_as_text(venue,200),_as_text(record.get("city"),120),_as_text(record.get("country"),100))

def _country_match(filter_code,country):
    if not filter_code:
        return True
    value=(country or "").casefold().strip()
    if not value:return False
    allowed={filter_code.casefold(),COUNTRIES.get(filter_code,"").casefold()}
    if filter_code=="GB":allowed.update({"england","scotland","wales","uk"})
    if filter_code=="CZ":allowed.add("czech republic")
    if filter_code=="US":allowed.add("usa")
    return value in allowed

def normalize(item,artist="",country=""):
    if not isinstance(item,dict):
        return None
    title=_as_text(item.get("title") or item.get("name"),200)
    if not title:return None
    gigora_url=_hosted_url(item.get("gigora_url") or item.get("url"))
    if not gigora_url:
        return None
    utc,local_date=_future_iso(item.get("starts_at") or item.get("startsAt"))
    if not local_date:return None
    venue,city,country_name=_place(item)
    if not _country_match(country,country_name):
        return None
    if artist:
        # The server-side artist filter must be supported by record metadata;
        # do not knowingly show unrelated events returned by a broad search.
        artist_name=_as_text(item.get("headliner") or item.get("artist") or "",200)
        wanted=artist.casefold()
        if artist_name and wanted not in artist_name.casefold() and wanted not in title.casefold():
            return None
    signature=hashlib.sha256(gigora_url.encode("utf-8")).hexdigest()[:26]
    return {
       "id":"gi:"+signature,"name":title,"starts_at":utc,
       "local_date":local_date,"venue":venue,"city":city,"country":country_name,
       "category":"Concert","provider":"Gigora",
       "url":gigora_url
    }

def request_gigora(artist,country):
    """Fixed endpoint, bounded response and no redirects or user-provided URLs."""
    params={"artist":artist,"limit":50}
    if country:
        params["country"]=COUNTRIES.get(country,country)
    with httpx.Client(timeout=12,follow_redirects=False) as client:
        response=client.get(BASE_URL,params=params,
            headers={"Accept":"application/json","User-Agent":"Ceyrl-EventRadar/1.0"})
    if response.status_code==429:
        raise ValueError("Gigora rate-limited the public search")
    if response.status_code!=200:
        raise ValueError("Gigora provider did not return 200")
    if len(response.content)>1_800_000:
        raise ValueError("Gigora response is too large")
    content=response.json()
    if not isinstance(content,dict) or not isinstance(content.get("events"),list):
        raise ValueError("Gigora response format unsupported")
    return content["events"]

def search(artist,country="",kind="all"):
    if kind=="sports":
        return [],{"checked":[],"errors":[]}
    key=(artist.casefold().strip(),country.upper(),kind)
    with _MUTEX:
        prev=_CACHED.get(key)
        if prev and time.monotonic()<prev[0]:
            return [dict(item) for item in prev[1]],dict(prev[2])
    try:
        data=request_gigora(artist,country)
        results=[]
        seen=set()
        for item in data[:100]:
            x=normalize(item,artist,country)
            if x and x["id"] not in seen:
                results.append(x)
                seen.add(x["id"])
        results=results[:40]
        diagnostics={"checked":["Gigora"],"errors":[]}
    except (httpx.HTTPError,ValueError,TypeError):
        results=[]
        diagnostics={"checked":[],"errors":["Gigora concert feed unavailable"]}
    with _MUTEX:
        if len(_CACHED)>200:
            _CACHED.clear()
        _CACHED[key]=(time.monotonic()+_CACHE_SECONDS,results,diagnostics)
    return [dict(item) for item in results],dict(diagnostics)
