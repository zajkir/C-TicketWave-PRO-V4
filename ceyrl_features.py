"""Ceyrl X optional modules: per-user radar, delivery, shield and read-only copilot."""
from __future__ import annotations
import json
import os
import re
from urllib.parse import urlsplit
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field
from ceyrl_shield import shield_report, delivery_score, VALID_METHODS
import ceyrl_ai
import ceyrl_radar
import ceyrl_concerthub
import ceyrl_sports

TM_EVENTS="https://app.ticketmaster.com/discovery/v2/events.json"
TM_ONE="https://app.ticketmaster.com/discovery/v2/events/"
TM_COUNTRIES={"", "SK","CZ","DE","AT","PL","GB","US","IE","FR","ES","IT","NL","BE","CH","HU","CA","AU"}

class DeliveryUpdate(BaseModel):
    method: str = Field(default="unknown", max_length=30)
    transfer_confirmed: bool = False
    possession_confirmed: bool = False
    restrictions_checked: bool = False
    availability_confirmed: bool = False
    notes: str = Field(default="", max_length=500)

class TMKeyInput(BaseModel):
    api_key: str = Field(min_length=8,max_length=180)

class RadarWatchInput(BaseModel):
    query: str = Field(min_length=2,max_length=80)
    country: str = Field(default="",max_length=2)

class CopilotInput(BaseModel):
    question: str = Field(min_length=2,max_length=500)
    use_ai: bool = False
    web_search: bool = False
    include_inventory: bool = False


def ensure_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS x_delivery(
        ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
        method TEXT NOT NULL DEFAULT 'unknown',
        transfer_confirmed INTEGER NOT NULL DEFAULT 0,
        possession_confirmed INTEGER NOT NULL DEFAULT 0,
        restrictions_checked INTEGER NOT NULL DEFAULT 0,
        availability_confirmed INTEGER NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS x_integrations(
        name TEXT PRIMARY KEY, encrypted_secret BLOB NOT NULL, updated_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS x_radar_watches(
        id INTEGER PRIMARY KEY, query TEXT NOT NULL,country TEXT NOT NULL DEFAULT '',
        last_checked TEXT,created_at TEXT NOT NULL,
        UNIQUE(query,country))""")
    db.execute("""CREATE TABLE IF NOT EXISTS x_radar_hits(
        id INTEGER PRIMARY KEY,watch_id INTEGER NOT NULL REFERENCES x_radar_watches(id) ON DELETE CASCADE,
        external_id TEXT NOT NULL, name TEXT NOT NULL, starts_at TEXT NOT NULL,
        venue TEXT NOT NULL DEFAULT '',city TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'new',
        first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
        UNIQUE(watch_id,external_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS x_radar_imports(
        external_id TEXT PRIMARY KEY,event_id INTEGER NOT NULL REFERENCES events(id),
        created_at TEXT NOT NULL)""")

# Only render images and external links from approved provider-owned hosts.
# Do not pass arbitrary provider strings into clickable links or image requests.
_TM_LISTING_HOSTS = re.compile(
    r"(?:www\.)?ticketmaster\.(?:com|co\.uk|de|fr|es|it|nl|be|ch|ca|ie|cz|pl|at|hu|com\.au)$",
    re.IGNORECASE,
)
_TM_IMAGE_HOSTS = {"s1.ticketm.net", "images1.ticketmaster.com", "images.ticketmaster.com"}


def safe_tm_url(value, *, image=False):
    if not isinstance(value, str) or len(value) > 1000:
        return ""
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or not host or parsed.username or
                parsed.password or parsed.port not in (None, 443)):
            return ""
        if image:
            if host not in _TM_IMAGE_HOSTS:
                return ""
        elif not _TM_LISTING_HOSTS.fullmatch(host):
            return ""
        return value
    except ValueError:
        return ""


def normalize_tm(item):
    start=(item.get("dates") or {}).get("start") or {}
    address=((item.get("_embedded") or {}).get("venues") or [{}])[0]
    loc=address.get("city") or {}
    raw_url=item.get("url") or ""
    images=item.get("images") or []
    image_url=""
    for candidate in images if isinstance(images,list) else []:
        if isinstance(candidate,dict) and candidate.get("ratio")=="16_9":
            image_url=safe_tm_url(candidate.get("url"),image=True)
            if image_url:
                break
    return {
        "id":str(item.get("id",""))[:100], "name":str(item.get("name",""))[:200],
        "starts_at":str(start.get("dateTime") or "")[:35],
        "local_date":str(start.get("localDate") or "")[:12],
        "venue":str(address.get("name",""))[:200],
        "city":str(loc.get("name",""))[:120],
        "country":str((address.get("country") or {}).get("name") or "")[:100],
        "url":safe_tm_url(raw_url),
        "image_url":image_url,
        "category":str(((item.get("classifications") or [{}])[0].get("segment") or {}).get("name") or "Concert")[:80],
        "provider":"Ticketmaster"
    }

def call_tm(key,params,one_id=None):
    try:
        if one_id is not None:
            # Ticketmaster event IDs must never become arbitrary URL paths.
            if not re.fullmatch(r"[A-Za-z0-9@_-]{3,100}",one_id):
                raise HTTPException(422,"Invalid event identifier.")
            url=TM_ONE+one_id+".json"
        else:
            url=TM_EVENTS
        with httpx.Client(timeout=12,follow_redirects=False) as client:
            response=client.get(url,params={**params,"apikey":key})
        if response.status_code==429:
            raise HTTPException(429,"Ticketmaster API rate limit reached. Try again later.")
        if response.status_code in (401,403):
            raise HTTPException(403,"Ticketmaster API key is invalid or lacks required access.")
        if response.status_code==404:
            raise HTTPException(404,"Event not found on Ticketmaster.")
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError,ValueError,TypeError):
        raise HTTPException(502,"Could not retrieve Ticketmaster events. Check API connectivity.")

def install_ceyrl_x(app, *,user_db,connection,select,personal_key,stamp,log,auth_db):
    def get_key(user,path):
        # The server key is shared securely with all registered users; it never
        # leaves the backend. Prefer it over stale personal integrations.
        shared=os.getenv("CTW_TICKETMASTER_API_KEY","").strip() or os.getenv("TICKETMASTER_API_KEY","").strip()
        if shared:
            return shared
        # Keep previously configured per-user keys usable without exposing a
        # personal-key setup prompt in the interface.
        with connection(path,True) as db:
            ensure_schema(db)
            row=db.execute("SELECT encrypted_secret FROM x_integrations WHERE name='ticketmaster'").fetchone()
        if row:
            try:
                return personal_key(user["id"]).decrypt(row["encrypted_secret"]).decode()
            except Exception:
                raise HTTPException(500,"Cannot decrypt the legacy Ticketmaster integration.")
        return ""

    def require_tm(user,path):
        key=get_key(user,path)
        if not key:
            raise HTTPException(503,"Connect a Ticketmaster Discovery API key in Event Radar settings.")
        return key

    def discover_events(user,path,query,country,kind="all"):
        """Read only from providers that we have actually verified reachable.

        Gigora returned HTTP 402 and StungEvents HTTP 410 in live CI probes
        on 2026-11-22. Do not call or advertise them as keyless sources.
        """
        events=[]
        sources=[]
        warnings=[]
        key=get_key(user,path)
        sport_query=ceyrl_sports.should_search(query,kind)
        if key and kind!="sports":
            params={"keyword":query.strip(),"size":30,"sort":"date,asc"}
            if country:params["countryCode"]=country
            try:
                payload=call_tm(key,params)
                events += [normalize_tm(e) for e in
                    ((payload.get("_embedded") or {}).get("events") or [])[:30]]
                sources.append("Ticketmaster")
            except HTTPException:
                warnings.append("Ticketmaster connection failed; verify the server key, API quota or provider status.")
        if kind!="sports" and not events:
            try:
                events += ceyrl_radar.search_public(query,country)
                sources.append("Ticket Fairy")
            except HTTPException:
                warnings.append("Ticket Fairy is currently unavailable.")
        # Additional keyless concerts from the documented ConcertHub JSON-RPC
        # catalog. It covers Poland ONLY: never pretend those results apply to
        # an explicitly selected other country.
        if kind!="sports" and country in ("","PL") and (country=="PL" or not events):
            try:
                events += ceyrl_concerthub.search_concerthub(query,country)
                sources.append("ConcertHub (Poland)")
            except HTTPException:
                warnings.append("ConcertHub's Polish concert catalog is temporarily unavailable.")
        if sport_query:
            sports,info=ceyrl_sports.search(query,country,kind)
            events += sports
            sources += info.get("checked",[])
            warnings += info.get("errors",[])
        if not sources:
            raise HTTPException(502,"Event sources could not be reached. Please try again or use the direct official search links.")
        unique={}
        for item in events:
            if item.get("id") and item.get("name"):
                unique.setdefault(item["id"],item)
        results=list(unique.values())[:40]
        coverage=(
            "Global Ticketmaster search is enabled on this server. Listings are from "
            "third-party catalogs and do not guarantee ticket availability."
            if key else
            "Search works without an API key using public event sources. "
            "Ticket Fairy covers its published listings; ConcertHub adds Poland concerts. "
            "These public catalogs do not contain every global tour. "
            "Use the official search links for additional artist dates."
        )
        return results," + ".join(dict.fromkeys(sources)),{
            "sources_checked":list(dict.fromkeys(sources)),
            "provider_warnings":warnings,
            "partial_outage":bool(warnings),
            "requires_server_key":not bool(key) and kind!="sports",
            "coverage_note":coverage
        }

    @app.get("/api/x/shield")
    def shield(request:Request):
        _,path=user_db(request)
        with connection(path) as db:
            return shield_report(db)

    @app.get("/api/x/delivery")
    def delivery_list(request:Request):
        _,path=user_db(request)
        with connection(path,True) as db:
            ensure_schema(db)
            rows=select(db,"""SELECT t.id,t.event_id,t.section,t.row_label,t.seats,
                 t.ticket_type,t.quantity,t.sold_quantity,e.title AS event_title,
                 e.starts_at,COALESCE(d.method,'unknown') AS method,
                 COALESCE(d.transfer_confirmed,0) AS transfer_confirmed,
                 COALESCE(d.possession_confirmed,0) AS possession_confirmed,
                 COALESCE(d.restrictions_checked,0) AS restrictions_checked,
                 COALESCE(d.availability_confirmed,0) AS availability_confirmed,
                 COALESCE(d.notes,'') AS delivery_notes,
                 (SELECT COUNT(*) FROM attachments a WHERE a.ticket_id=t.id) AS pdf_count
                 FROM tickets t JOIN events e ON e.id=t.event_id
                 LEFT JOIN x_delivery d ON d.ticket_id=t.id ORDER BY t.id DESC""")
        return [{**t,"readiness":delivery_score(t,t,t["pdf_count"])} for t in rows]

    @app.put("/api/x/delivery/{ticket_id}")
    def delivery_update(ticket_id:int,payload:DeliveryUpdate,request:Request):
        _,path=user_db(request,True)
        if payload.method not in VALID_METHODS:
            raise HTTPException(422,"Unsupported delivery method.")
        with connection(path,True) as db:
            ensure_schema(db)
            ticket=db.execute("SELECT id FROM tickets WHERE id=?",(ticket_id,)).fetchone()
            if not ticket:
                raise HTTPException(404,"This ticket lot is not in your account.")
            db.execute("""INSERT INTO x_delivery(ticket_id,method,transfer_confirmed,
                 possession_confirmed,restrictions_checked,availability_confirmed,notes,updated_at)
                 VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET
                 method=excluded.method,transfer_confirmed=excluded.transfer_confirmed,
                 possession_confirmed=excluded.possession_confirmed,
                 restrictions_checked=excluded.restrictions_checked,
                 availability_confirmed=excluded.availability_confirmed,
                 notes=excluded.notes,updated_at=excluded.updated_at""",
                 (ticket_id,payload.method,int(payload.transfer_confirmed),int(payload.possession_confirmed),
                 int(payload.restrictions_checked),int(payload.availability_confirmed),
                 payload.notes.strip(),stamp()))
            log(db,"delivery-review","ticket",ticket_id)
        return {"ok":True}

    @app.get("/api/x/radar/status")
    def radar_status(request:Request):
        user,path=user_db(request)
        with connection(path,True) as db:
            ensure_schema(db)
            personal=bool(db.execute("SELECT 1 FROM x_integrations WHERE name='ticketmaster'").fetchone())
            count=db.execute("SELECT COUNT(*) FROM x_radar_watches").fetchone()[0]
        shared=bool(os.getenv("CTW_TICKETMASTER_API_KEY","").strip() or
                    os.getenv("TICKETMASTER_API_KEY","").strip())
        return {"connected":True,"key_required":False,"personal_key":personal,
                "server_ticketmaster":shared,"watch_count":count,
                "provider":("Ticketmaster + Ticket Fairy + ConcertHub Poland + sports"
                            if shared or personal else
                            "Ticket Fairy + ConcertHub Poland + sports"),
                "global_concerts_enabled":bool(shared or personal),
                "keyless_search_enabled":True,
                "keyless_sources":["Ticket Fairy","ConcertHub (Poland)","Sports fixtures"],
                "coverage_note":("You can search events directly without your own key. "
                                 "Ticketmaster and public source catalogs can be incomplete." if shared or personal else
                                 "Search with no API key. Public sources cover only their listed events "
                                 "(including Polish concerts); worldwide tour coverage is incomplete. "
                                 "Use official links for more listings."),
                "refresh_note":"Watchlist refreshes on demand. No background scheduler is active."}

    # Deprecated optional personal integration endpoints remain for existing users.
    # The new interface never asks users to configure an API key.
    @app.put("/api/x/radar/key")
    def radar_key(payload:TMKeyInput,request:Request):
        user,path=user_db(request,True)
        key=payload.api_key.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,180}",key):
            raise HTTPException(422,"Check the Ticketmaster API key format.")
        encrypted=personal_key(user["id"]).encrypt(key.encode())
        with connection(path,True) as db:
            ensure_schema(db)
            db.execute("""INSERT INTO x_integrations(name,encrypted_secret,updated_at)
              VALUES('ticketmaster',?,?) ON CONFLICT(name) DO UPDATE SET
              encrypted_secret=excluded.encrypted_secret,updated_at=excluded.updated_at""",(encrypted,stamp()))
        return {"ok":True,"note":"Your existing key remains encrypted and private."}

    @app.delete("/api/x/radar/key")
    def delete_radar_key(request:Request):
        _,path=user_db(request,True)
        with connection(path,True) as db:
            ensure_schema(db)
            db.execute("DELETE FROM x_integrations WHERE name='ticketmaster'")
        return {"ok":True}

    @app.get("/api/x/radar/search")
    def radar_search(request:Request,q:str=Query(min_length=2,max_length=80),
                     country:str=Query(default="",max_length=2),
                     kind:str=Query(default="all",pattern=r"^(all|music|sports)$")):
        user,path=user_db(request)
        cc=country.upper().strip()
        if cc not in TM_COUNTRIES:raise HTTPException(422,"Unsupported country code.")
        q=q.strip()
        if len(q)<2 or any(ord(ch)<32 or ord(ch)==127 for ch in q):
            raise HTTPException(422,"Enter an artist or event name.")
        ceyrl_radar.rate_limit(auth_db,connection,user["id"],"search")
        events,source,diagnostics=discover_events(user,path,q,cc,kind)
        with connection(path,True) as db:
            ensure_schema(db)
            ceyrl_radar.remember(db,events)
        return {"events":events,"source":source,**diagnostics}

    @app.get("/api/x/radar/watches")
    def radar_watches(request:Request):
        _,path=user_db(request)
        with connection(path,True) as db:
            ensure_schema(db)
            watches=select(db,"SELECT * FROM x_radar_watches ORDER BY id DESC")
            hits=select(db,"""SELECT h.*,w.query AS watch_query FROM x_radar_hits h
                JOIN x_radar_watches w ON w.id=h.watch_id
                ORDER BY h.last_seen DESC LIMIT 80""")
        return {"watches":watches,"hits":hits}

    @app.post("/api/x/radar/watches")
    def radar_watch_add(payload:RadarWatchInput,request:Request):
        _,path=user_db(request,True)
        country=payload.country.upper().strip()
        if country not in TM_COUNTRIES:raise HTTPException(422,"Unsupported country code.")
        query=payload.query.strip()
        with connection(path,True) as db:
            ensure_schema(db)
            if db.execute("SELECT COUNT(*) FROM x_radar_watches").fetchone()[0]>=15:
                raise HTTPException(409,"Maximum 15 event watches per account.")
            if db.execute("SELECT id FROM x_radar_watches WHERE query=? COLLATE NOCASE AND country=?",
                          (query,country)).fetchone():
                raise HTTPException(409,"You are already watching this search.")
            cur=db.execute("INSERT INTO x_radar_watches(query,country,created_at) VALUES(?,?,?)",
                            (query,country,stamp()))
            log(db,"radar-follow","watch",cur.lastrowid)
        return {"id":cur.lastrowid}

    @app.delete("/api/x/radar/watches/{watch_id}")
    def radar_watch_delete(watch_id:int,request:Request):
        _,path=user_db(request,True)
        with connection(path,True) as db:
            ensure_schema(db)
            if not db.execute("SELECT 1 FROM x_radar_watches WHERE id=?",(watch_id,)).fetchone():
                raise HTTPException(404,"Watch not found.")
            db.execute("DELETE FROM x_radar_watches WHERE id=?",(watch_id,))
        return {"ok":True}

    @app.post("/api/x/radar/refresh")
    def radar_refresh(request:Request):
        user,path=user_db(request,True)
        with connection(path,True) as db:
            ensure_schema(db)
            watches=select(db,"SELECT id,query,country,last_checked FROM x_radar_watches ORDER BY id ASC LIMIT 15")
        ceyrl_radar.rate_limit(auth_db,connection,user["id"],"refresh",units=max(1,len(watches)))
        fresh=0;updated=0;errors=[];skipped=0
        for watch in watches:
            try:
                last=watch["last_checked"]
                if last:
                    try:
                        age=(datetime.now(timezone.utc)-datetime.fromisoformat(last.replace("Z","+00:00"))).total_seconds()
                        if 0 <= age < 300:
                            skipped+=1
                            continue
                    except (TypeError,ValueError):
                        pass
                matches,provider,_=discover_events(user,path,watch["query"],watch["country"])
                with connection(path,True) as db:
                    ceyrl_radar.remember(db,matches)
                    for x in matches:
                        if not x["id"]:continue
                        old=select(db,"""SELECT id,starts_at,venue FROM x_radar_hits
                              WHERE watch_id=? AND external_id=?""",(watch["id"],x["id"]),True)
                        if old:
                            changed=(old["starts_at"]!=x["starts_at"] or old["venue"]!=x["venue"])
                            db.execute("""UPDATE x_radar_hits SET name=?,starts_at=?,venue=?,city=?,url=?,
                              status=CASE WHEN ? THEN 'updated' ELSE status END,last_seen=? WHERE id=?""",
                               (x["name"],x["starts_at"],x["venue"],x["city"],x["url"],
                                int(changed),stamp(),old["id"]))
                            if changed:updated+=1
                        else:
                            db.execute("""INSERT INTO x_radar_hits(
                               watch_id,external_id,name,starts_at,venue,city,url,first_seen,last_seen)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                               (watch["id"],x["id"],x["name"],x["starts_at"],x["venue"],
                                x["city"],x["url"],stamp(),stamp()))
                            fresh+=1
                    db.execute("UPDATE x_radar_watches SET last_checked=? WHERE id=?",
                               (stamp(),watch["id"]))
            except HTTPException as exc:
                errors.append({"watch_id":watch["id"],"error":str(exc.detail)})
                if exc.status_code==429:break
        return {"new":fresh,"updated":updated,"checked":len(watches)-skipped,"skipped":skipped,"errors":errors,
                "notice":"In-app observations only. External event details are not automatically added to your inventory."}

    @app.post("/api/x/radar/import/{external_id}")
    def radar_import(external_id:str,request:Request):
        user,path=user_db(request,True)
        ceyrl_radar.rate_limit(auth_db,connection,user["id"],"import")
        if external_id.startswith(("tf:","sp:","ch:")):
            with connection(path,True) as db:
                tm=ceyrl_radar.lookup(db,external_id)
        else:
            key=get_key(user,path)
            if not key:
                raise HTTPException(404,"Search for this event again before importing.")
            tm=normalize_tm(call_tm(key,{},external_id))
        if not tm.get("starts_at"):
            raise HTTPException(422,"Event source did not provide a reliable UTC time.")
        try:
            when=datetime.fromisoformat(tm["starts_at"].replace("Z","+00:00"))
            if when.tzinfo is None:
                raise ValueError("timezone required")
            starts_at=when.astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError):
            raise HTTPException(422,"Event source date is not valid.")
        with connection(path,True) as db:
            ensure_schema(db)
            old=db.execute("SELECT event_id FROM x_radar_imports WHERE external_id=?",
                           (external_id,)).fetchone()
            if old:return {"id":old["event_id"],"already_exists":True}
            cur=db.execute("""INSERT INTO events(title,starts_at,venue,city,country,category,notes,created_at)
                     VALUES(?,?,?,?,?,?,?,?)""",
                     (tm["name"],starts_at,tm["venue"],tm["city"],tm["country"],
                      tm["category"],"Imported from "+
                      tm.get("provider","public event provider")+
                      ". Verify date and ticket details at the official source.",stamp()))
            db.execute("INSERT INTO x_radar_imports(external_id,event_id,created_at) VALUES(?,?,?)",
                       (external_id,cur.lastrowid,stamp()))
            log(db,"radar-import","event",cur.lastrowid)
            return {"id":cur.lastrowid,"already_exists":False}

    @app.get("/api/x/copilot/status")
    def copilot_status(request:Request):
        user,_=user_db(request)
        return ceyrl_ai.get_status(user["id"],auth_db,connection)

    @app.get("/api/x/copilot/history")
    def copilot_history(request:Request):
        user,path=user_db(request)
        encrypted=personal_key(user["id"])
        with connection(path,True) as db:
            messages=ceyrl_ai.load_chat(db,encrypted,limit=60)
        return {"messages":messages}

    @app.delete("/api/x/copilot/history")
    def copilot_clear(request:Request):
        user,path=user_db(request,True)
        with connection(path,True) as db:
            ceyrl_ai.init_chat_db(db)
            db.execute("DELETE FROM x_ai_messages")
        return {"ok":True}

    @app.post("/api/x/copilot")
    def copilot(payload:CopilotInput,request:Request):
        user,path=user_db(request,True)
        if payload.use_ai:
            return ceyrl_ai.generate(payload.question,user["id"],path,auth_db=auth_db,
               connection=connection,personal_key=personal_key,
               web_search=payload.web_search,include_inventory=payload.include_inventory)
        with connection(path,True) as db:
            ensure_schema(db)
            events=db.execute("SELECT COUNT(*) FROM events WHERE archived=0").fetchone()[0]
            lots=db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
            unfiled=db.execute("""SELECT COUNT(*) FROM tickets t WHERE t.quantity>t.sold_quantity AND
                   NOT EXISTS(SELECT 1 FROM attachments a WHERE a.ticket_id=t.id)""").fetchone()[0]
            pending=db.execute("SELECT COUNT(*) FROM listings WHERE status IN ('ready','listed')").fetchone()[0]
            revenue=db.execute("SELECT COALESCE(SUM(revenue_cents),0) FROM sales WHERE currency='EUR'").fetchone()[0]
            fees=db.execute("SELECT COALESCE(SUM(fee_cents),0) FROM sales WHERE currency='EUR'").fetchone()[0]
            sold=db.execute("SELECT COALESCE(SUM(quantity),0) FROM sales").fetchone()[0]
            collisions=shield_report(db)["conflicts"]
        snapshot={"events":events,"ticket_lots":lots,"lots_without_pdf":unfiled,
                  "active_local_listings":pending,"revenue_eur":round(revenue/100,2),
                  "fees_eur":round(fees/100,2),"sold_tickets":sold,"shield_alerts":len(collisions)}
        q=payload.question.lower()
        if any(k in q for k in ("pdf","document","súbor","subor")):
            answer=f"{unfiled} available ticket lot(s) have no PDF attached. This may be normal for mobile-transfer tickets. Open Delivery Readiness to review them."
            pages=["delivery","tickets"]
        elif any(k in q for k in ("duplicate","double","duplicit","dvojit","shield","risk","rizik")):
            answer=f"Double-Sale Shield currently identifies {len(collisions)} local risk(s). Check exact seat overlaps and local active listings. Marketplace availability is not synchronized."
            pages=["shield","listings"]
        elif any(k in q for k in ("profit","sales","sale","zisk","zarob","tržb","trzb","predaj","revenue")):
            answer=f"Your recorded EUR sales total €{revenue/100:,.2f}, with €{fees/100:,.2f} in fees, across {sold} sold ticket(s). For net profit after purchase costs and expenses open Analytics."
            pages=["analytics","sales"]
        elif any(k in q for k in ("event","concert","koncert","radar","interpret")):
            answer=f"You currently have {events} saved event(s). Open Event Radar to discover Ticketmaster dates, or My Events to manage your own calendar."
            pages=["radar","events"]
        else:
            answer="The offline helper cannot answer general questions or verify current event dates. Connect GPT-5.4 mini and enable web search for a real conversational answer. I can still summarize your local tickets, PDFs or recorded sales."
            pages=["actions","delivery"]
        return {"mode":"local","answer":answer,"pages":pages,"snapshot":snapshot,
                "notice":"Offline rules, not an AI model. No data was sent outside Ceyrl."}
