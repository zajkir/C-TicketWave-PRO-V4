"""Read-only keyless sports discovery for Ceyrl Event Radar.

TheSportsDB v1 publishes a documented limited free demo key (123). ESPN
scoreboard is a public, unofficial read endpoint; it is *not* a ticket
seller. Both provider hosts/paths are fixed. No users' account data is sent,
and nothing here claims ticket availability or official resale permission.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import httpx

SPORTS_API = "https://www.thesportsdb.com/api/v1/json/123"
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer"
LOCK = threading.Lock()
CACHE = {}
CACHE_TTL = 300
# Exact, audited league slugs. Unknown user text NEVER becomes a URL path.
LEAGUES = {
    "nations": ("uefa.nations", 4490, "UEFA Nations League"),
    "champions": ("uefa.champions", 4480, "UEFA Champions League"),
    "europa": ("uefa.europa", None, "UEFA Europa League"),
    "premier": ("eng.1", 4328, "English Premier League"),
    "serie": ("ita.1", 4332, "Italian Serie A"),
    "bundesliga": ("ger.1", 4331, "German Bundesliga"),
    "laliga": ("esp.1", 4335, "Spanish La Liga"),
    "worldcup": ("fifa.world", None, "FIFA World Cup"),
}
COUNTRIES = {
    "SK":"Slovakia","CZ":"Czechia","DE":"Germany","AT":"Austria",
    "PL":"Poland","GB":"United Kingdom","US":"United States",
    "IE":"Ireland","FR":"France","ES":"Spain","IT":"Italy",
    "NL":"Netherlands","BE":"Belgium","CH":"Switzerland","HU":"Hungary",
    "CA":"Canada","AU":"Australia",
}
SPORT_HINTS = re.compile(
    r"\b(nations?\s*league|champions?\s*league|europa\s*league|premier\s*league|"
    r"bundesliga|serie\s*a|la\s*liga|world\s*cup|fifa|uefa|football|soccer|"
    r"futbal|sport|nba|nhl|nfl|liga\s*narodov|liga\s*národov)\b",re.I
)

def _flat(value):
    return unicodedata.normalize("NFKD",str(value or "")).casefold()

def _match_league(query):
    q=_flat(query)
    if ("nations" in q and "league" in q) or ("liga" in q and ("narodov" in q or "národov" in q)):
        return "nations"
    if "champions" in q and "league" in q:
        return "champions"
    if "europa" in q and "league" in q:
        return "europa"
    if "premier" in q and "league" in q:
        return "premier"
    if "serie" in q and "a" in q.split():
        return "serie"
    if "bundesliga" in q:
        return "bundesliga"
    if "la liga" in q:
        return "laliga"
    if "world cup" in q or "fifa" in q:
        return "worldcup"
    return None

def should_search(query,kind="all"):
    return kind=="sports" or bool(_match_league(query)) or bool(SPORT_HINTS.search(query))

def _iso_utc(value):
    if not isinstance(value,str) or not value:
        return "", ""
    try:
        moment=datetime.fromisoformat(value.replace("Z","+00:00"))
        if moment.tzinfo is None:
            return "", moment.date().isoformat()
        return moment.astimezone(timezone.utc).isoformat(), moment.date().isoformat()
    except (TypeError,ValueError,OverflowError):
        return "", ""

def _country_ok(cc,city,country):
    if not cc:return True
    country=_flat(country).strip()
    if not country:return False
    names=[cc.casefold(),_flat(COUNTRIES.get(cc,""))]
    if cc=="GB":names.extend(["england","scotland","wales","united kingdom"])
    return any(country==n or n in country for n in names if n)

def _sportsdb_event(row,country):
    if not isinstance(row,dict):return None
    event_id=str(row.get("idEvent") or "")
    if not re.fullmatch(r"\d{1,12}",event_id):return None
    name=str(row.get("strEvent") or "").strip()[:200]
    if not name:return None
    iso,local=_iso_utc(row.get("strTimestamp"))
    if not local:
        rawdate=str(row.get("dateEvent") or "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}",rawdate):
            local=rawdate
    if not local:return None
    today=datetime.now(timezone.utc).date()
    try:
        if datetime.fromisoformat(local).date()<today-timedelta(days=1):
            return None
    except ValueError:return None
    place=str(row.get("strCountry") or "").strip()[:100]
    city=str(row.get("strCity") or "").strip()[:120]
    if not _country_ok(country,city,place):return None
    return {"id":"sp:ts:"+event_id,"name":name,"starts_at":iso,"local_date":local,
        "venue":str(row.get("strVenue") or "")[:200],
        "city":city,"country":place,"category":"Sports",
        "url":"https://www.thesportsdb.com/event/"+event_id,"provider":"TheSportsDB"}

def _espn_event(row,country):
    if not isinstance(row,dict):return None
    eid=str(row.get("id") or "")
    if not re.fullmatch(r"\d{1,12}",eid):return None
    name=str(row.get("name") or row.get("shortName") or "")[:200].strip()
    utc,local=_iso_utc(row.get("date"))
    if not name or not utc:return None
    try:
        if datetime.fromisoformat(utc)<datetime.now(timezone.utc)-timedelta(days=1):
            return None
    except ValueError:return None
    contests=row.get("competitions") or []
    contest=contests[0] if isinstance(contests,list) and contests and isinstance(contests[0],dict) else {}
    venue=contest.get("venue") or {}
    if not isinstance(venue,dict):venue={}
    address=venue.get("address") or {}
    if not isinstance(address,dict):address={}
    cc=str(address.get("country") or "")[:100]
    city=str(address.get("city") or "")[:120]
    if not _country_ok(country,city,cc):return None
    return {"id":"sp:es:"+eid,"name":name,"starts_at":utc,"local_date":local,
        "venue":str(venue.get("fullName") or "")[:200],
        "city":city,"country":cc,"category":"Sports",
        "url":"https://www.espn.com/soccer/match/_/gameId/"+eid,"provider":"ESPN"}

def _fetch_json(url,params):
    with httpx.Client(timeout=11,follow_redirects=False) as client:
        response=client.get(url,params=params,
            headers={"Accept":"application/json","User-Agent":"Ceyrl-EventRadar/1.0"})
    if response.status_code!=200:
        raise ValueError("sports source returned a non-success response")
    if len(response.content)>2_000_000:
        raise ValueError("sports source response too large")
    body=response.json()
    if not isinstance(body,dict):
        raise ValueError("unexpected sports source response")
    return body

def _espn_events(slug,country):
    now=datetime.now(timezone.utc)
    # ESPN supports an explicit calendar window. It may not publish far-ahead
    # fixtures; this is a partial feed, NOT a complete ticket/events catalog.
    end=now+timedelta(days=210)
    data=_fetch_json(ESPN_API+"/"+slug+"/scoreboard",{
        "dates":now.strftime("%Y%m%d")+"-"+end.strftime("%Y%m%d"),
        "limit":100
    })
    rows=data.get("events")
    if not isinstance(rows,list):raise ValueError("unsupported ESPN schedule response")
    result=[]
    for row in rows[:150]:
        event=_espn_event(row,country)
        if event:result.append(event)
    return result

def _sportsdb_events(query,league_id,country):
    # Only safe documented endpoints with limited free 123 demonstration quota.
    calls=[("searchevents.php",{"e":query})]
    if league_id:
        calls.insert(0,("eventsnextleague.php",{"id":str(league_id)}))
    matches=[]
    failed=0
    for endpoint,params in calls:
        try:
            data=_fetch_json(SPORTS_API+"/"+endpoint,params)
            rows=data.get("events") or []
            if isinstance(rows,list):
                for row in rows[:20]:
                    event=_sportsdb_event(row,country)
                    if event:matches.append(event)
        except (ValueError,TypeError,httpx.HTTPError):
            failed+=1
    if failed==len(calls):raise ValueError("SportsDB search unavailable")
    return matches

def search(query,country="",kind="all"):
    """Return events, provider diagnostics and whether any source succeeded.

    Never convert failed providers into a misleading '0 matching events' answer.
    """
    key=(_flat(query),country.upper(),kind)
    with LOCK:
        previous=CACHE.get(key)
        if previous and time.monotonic()<previous[0]:
            results,diagnostics=previous[1:]
            return [dict(x) for x in results],dict(diagnostics)
    league=_match_league(query)
    if not should_search(query,kind):
        return [],{"checked":[],"errors":[],"status":"not_sport"}
    successes=[]
    errors=[]
    rows=[]
    if league:
        slug,league_id,_=LEAGUES[league]
        try:
            rows+=_espn_events(slug,country)
            successes.append("ESPN schedules")
        except (httpx.HTTPError,ValueError,TypeError):
            errors.append("ESPN schedules temporarily unavailable")
    try:
        rows+=_sportsdb_events(query,LEAGUES[league][1] if league else None,country)
        successes.append("TheSportsDB")
    except (httpx.HTTPError,ValueError,TypeError):
        errors.append("TheSportsDB temporarily unavailable")
    seen=set()
    result=[]
    for item in rows:
        # Cross-source duplicate names are rare; preserve source-labelled
        # records without treating different event IDs as the same match.
        if item["id"] not in seen:
            result.append(item);seen.add(item["id"])
    result.sort(key=lambda x:(x.get("starts_at") or "9999",x.get("name","")))
    result=result[:25]
    diagnostics={"checked":successes,"errors":errors,
                 "status":"ok" if successes else "unavailable"}
    with LOCK:
        if len(CACHE)>200:CACHE.clear()
        CACHE[key]=(time.monotonic()+CACHE_TTL,result,diagnostics)
    return [dict(x) for x in result],dict(diagnostics)
