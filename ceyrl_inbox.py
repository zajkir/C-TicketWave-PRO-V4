"""Magic Inbox: isolated encrypted purchase-confirmation drafts.

Inbound e-mail (Mailgun Routes, optional), .eml and pasted text all enter the
SAME review queue. Absolutely no automatic event/ticket creation. The user
must approve corrected values before inventory changes.

Webhook signing key is NOT a Mailgun API key. The timestamp + token HMAC is
checked before any private account routing. Inbound sender headers and parsed
email content are untrusted; always review actual order confirmations.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, Request, UploadFile, File, Query
from pydantic import BaseModel, Field
from ceyrl_shield import guard_ticket_create

MAX_EML = 3 * 1024 * 1024
MAX_WEBHOOK = 12 * 1024 * 1024
MAX_PDF = 4 * 1024 * 1024
MAX_PDF_TOTAL = 9 * 1024 * 1024
MAX_PDFS = 3
MAX_BODY_CHARS = 36_000
MAX_DRAFTS = 250

def now_stamp():
    return datetime.now(timezone.utc).isoformat()

def _domain():
    value = os.getenv("CTW_MAGIC_INBOX_DOMAIN", "").strip().lower().strip(".")
    if len(value) > 253 or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", value):
        return ""
    if any(label.startswith("-") or label.endswith("-") for label in value.split(".")):
        return ""
    return value

def _signing_key():
    return os.getenv("CTW_MAILGUN_WEBHOOK_SIGNING_KEY", "").strip()

def _enabled():
    return bool(_domain() and _signing_key())

def _identity_tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS magic_inbox_aliases (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        alias TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )""")

def _user_tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS magic_inbox_drafts (
        id INTEGER PRIMARY KEY,
        source_hash TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','imported','dismissed')),
        encrypted_payload BLOB NOT NULL,
        event_id INTEGER REFERENCES events(id),
        ticket_id INTEGER REFERENCES tickets(id),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_magic_drafts_status ON magic_inbox_drafts(status,created_at)")

def _get_alias(user_id, auth_db, connection, rotate=False):
    with connection(auth_db, True) as db:
        _identity_tables(db)
        row=db.execute("SELECT alias FROM magic_inbox_aliases WHERE user_id=?",(user_id,)).fetchone()
        if row and not rotate:
            return row["alias"]
        for _ in range(8):
            alias="inbox-"+secrets.token_hex(16)
            try:
                db.execute("""INSERT INTO magic_inbox_aliases(user_id,alias,created_at)
                    VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                    alias=excluded.alias,created_at=excluded.created_at""",
                    (user_id,alias,now_stamp()))
                return alias
            except Exception as exc:
                # Random 128-bit aliases practically never collide. Unexpected DB
                # errors must not be silently swallowed.
                if "UNIQUE constraint failed: magic_inbox_aliases.alias" not in str(exc):
                    raise
    raise HTTPException(500, "Could not allocate a private inbox address.")

def _lookup_alias(recipient, auth_db, connection):
    address=(recipient or "").strip().lower()
    if len(address)>260 or "@" not in address:
        return None
    name, domain=address.rsplit("@",1)
    if domain!=_domain() or not re.fullmatch(r"inbox-[a-f0-9]{32}",name):
        return None
    with connection(auth_db) as db:
        _identity_tables(db)
        row=db.execute("""SELECT u.id FROM magic_inbox_aliases a JOIN users u ON u.id=a.user_id
            WHERE a.alias=? AND u.enabled=1 AND u.verified=1""",(name,)).fetchone()
        return row["id"] if row else None

class _TextOnlyHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out=[]
        self.hide=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","head"):
            self.hide+=1
        elif tag in ("p","div","br","li","tr","td","h1","h2","h3"):
            self.out.append("\n")
    def handle_endtag(self,tag):
        if tag in ("script","style","head"):
            self.hide=max(0,self.hide-1)
        elif tag in ("p","div","li","tr"):
            self.out.append("\n")
    def handle_data(self,data):
        if self.hide==0:
            self.out.append(data)

def html_to_text(value):
    parser=_TextOnlyHTML()
    parser.feed((value or "")[:MAX_BODY_CHARS*2])
    return html.unescape("".join(parser.out))[:MAX_BODY_CHARS]

def _eml_parts(raw):
    if len(raw)>MAX_EML:
        raise HTTPException(413,"Email file is too large. Maximum 3 MB.")
    try:
        msg=BytesParser(policy=policy.default).parsebytes(raw)
        sender=str(msg.get("From",""))[:255]
        subject=str(msg.get("Subject",""))[:300]
        message_id=str(msg.get("Message-ID",""))[:250]
        date=str(msg.get("Date",""))[:100]
        plain=[]
        html_parts=[]
        files=[]
        for part in msg.walk():
            if part.is_multipart():
                continue
            typ=part.get_content_type().lower()
            disposition=part.get_content_disposition()
            if disposition=="attachment" or part.get_filename():
                if typ=="application/pdf" and len(files)<MAX_PDFS:
                    blob=part.get_payload(decode=True) or b""
                    if len(blob)<=MAX_PDF and blob.startswith(b"%PDF-"):
                        files.append((str(part.get_filename() or "ticket.pdf"),blob))
                continue
            if typ=="text/plain":
                plain.append(part.get_content())
            elif typ=="text/html":
                html_parts.append(part.get_content())
        body="\n".join(plain) if plain else html_to_text("\n".join(html_parts))
        return {"sender":sender,"subject":subject,"message_id":message_id,
                "body":body[:MAX_BODY_CHARS],"source_date":date}, files
    except HTTPException:
        raise
    except (ValueError,TypeError,UnicodeError,LookupError) as exc:
        raise HTTPException(422,"Cannot parse this email file.") from exc

def _field(body, label, max_len=200):
    # RFC mail bodies include forwards/quoted messages; use explicit labeled
    # lines anywhere in the message but never trust such data until approval.
    terms={
      "event":r"(?:event|event name|concert|koncert|podujatie|artist|interpret)",
      "date":r"(?:event date|date of event|event starts|datum (?:koncertu|podujatia)|dátum (?:koncertu|podujatia)|dátum|date)",
      "time":r"(?:event time|time|cas|čas)",
      "venue":r"(?:venue|stadium|arena|location|miesto|hala)",
      "city":r"(?:city|mesto)",
      "section":r"(?:section|sector|sektor|block)",
      "row":r"(?:row|rada|rad|reihe)",
      "seats":r"(?:seats?|sedadlá|sedadla|sedadlo|platz)",
      "quantity":r"(?:quantity|qty|tickets?|počet (?:lístkov|listkov)|anzahl)",
      "price":r"(?:price per ticket|unit price|cena za (?:jeden )?lístok|cena za listok)",
      "total":r"(?:order total|total paid|total price|grand total|celkom|spolu)",
      "currency":r"(?:currency|mena)",
      "provider":r"(?:provider|ticket provider|vendor|predajca)",
    }
    term=terms[label]
    expr=r"(?im)^\s*(?:"+term+r")\s*[:\-–]\s*(.{1,"+str(max_len)+r"})$"
    m=re.search(expr,body[:MAX_BODY_CHARS])
    return (m.group(1).strip() if m else "")[:max_len]

def _amount(text):
    if not text:return ""
    # Normalize common prices: €120.50; 120,50 EUR; 1 230,99
    num=re.search(r"(?:€|EUR|USD|GBP|CZK|Kč|\$|£)?\s*(\d[\d .,'’]*\d|\d)(?:\s*(?:€|EUR|USD|GBP|CZK|Kč|\$|£))?",text,re.I)
    if not num:return ""
    raw=num.group(1).replace(" ","").replace("'","").replace("’","")
    if raw.count(",")==1 and raw.count(".")==1:
        raw=raw.replace(".","").replace(",",".") if raw.rfind(",")>raw.rfind(".") else raw.replace(",","")
    elif "," in raw:
        raw=raw.replace(",",".") if len(raw.split(",")[-1])<=2 else raw.replace(",","")
    elif "." in raw and len(raw.split(".")[-1])==3:
        raw=raw.replace(".","")
    try:
        value=Decimal(raw)
        if value<0 or value>100_000_000:return ""
        return str(value)
    except Exception:return ""

def extract_candidate(subject,body):
    body=(body or "")[:MAX_BODY_CHARS]
    title=_field(body,"event")
    if not title:
        m=re.search(r"(?i)(?:tickets? (?:for|to)|confirmation (?:for|of))\s*[:\-–]?\s*(.+)",subject)
        if m:title=m.group(1).strip()[:200]
    date=_field(body,"date",120)
    time=_field(body,"time",40)
    quantity=_field(body,"quantity",35)
    qm=re.search(r"\b(\d{1,3})\b",quantity)
    currency="EUR"
    unit=_field(body,"price",80)
    total=_field(body,"total",80)
    currency_text=" ".join((unit,total,_field(body,"currency",20))).upper()
    for key,mark in (("GBP","GBP"),("USD","USD"),("CZK","CZK"),("EUR","EUR"),
                     ("PLN","PLN"),("CHF","CHF")):
        if key in currency_text:
            currency=mark;break
    if "KČ" in currency_text:currency="CZK"
    if "$" in currency_text and "USD" not in currency_text:currency="USD"
    if "£" in currency_text:currency="GBP"
    candidate={
        "event_title":title[:200],
        "date_hint":date,
        "time_hint":time,
        "venue":_field(body,"venue"),
        "city":_field(body,"city"),
        "provider":_field(body,"provider",100),
        "section":_field(body,"section",100),
        "row_label":_field(body,"row",70),
        "seats":_field(body,"seats",150),
        "quantity":int(qm.group(1)) if qm else None,
        "purchase_price":_amount(unit),
        "total_price":_amount(total),
        "currency":currency,
    }
    # Only unambiguous ISO dates are prefills. Local timezones aren't inferred.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):
        candidate["local_date"]=date
    else:
        candidate["local_date"]=""
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",time):
        candidate["local_time"]=time
    else:
        candidate["local_time"]=""
    confidence=sum(bool(candidate.get(x)) for x in
                   ("event_title","date_hint","venue","section","row_label","seats","purchase_price"))
    warnings=[]
    if not candidate["event_title"]:warnings.append("Event name was not recognized. Enter it manually.")
    if not candidate["date_hint"]:warnings.append("Event date was not recognized. Confirm its date and local time.")
    if candidate["total_price"] and not candidate["purchase_price"]:
        warnings.append("Only a total order amount was found. Enter the per-ticket purchase price manually.")
    if not candidate["quantity"]:warnings.append("Ticket quantity is unknown. Confirm it before saving.")
    warnings.append("Forwarded emails are untrusted. Compare details with the original order and official event.")
    candidate["warnings"]=warnings
    candidate["confidence"]="strong" if confidence>=5 else "partial" if confidence>=3 else "manual_review"
    return candidate

def _source_hash(sender, subject, body, message_id):
    # Content fingerprint is idempotent even if the same message is sent twice.
    key="\0".join((sender.strip().lower(),subject.strip(),message_id.strip(),
                    hashlib.sha256(body.encode("utf-8")).hexdigest()))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def _sanitize_name(value):
    name=Path(str(value or "ticket.pdf").replace("\\","/")).name
    return (re.sub(r"[^a-zA-Z0-9._ -]","_",name)[:120] or "ticket.pdf")

def _draft_summary(row, cipher):
    try:
        payload=json.loads(cipher.decrypt(row["encrypted_payload"]).decode("utf-8"))
    except Exception:
        raise HTTPException(500,"Cannot decrypt Magic Inbox data; restore your account key.")
    return {
        "id":row["id"],"status":row["status"],
        "subject":payload["subject"],"sender":payload["sender"],
        "candidate":payload["candidate"],"body_preview":payload["body"][:12000],
        "pdfs":[{"filename":x["filename"],"size":x["size"]} for x in payload["pdfs"]],
        "event_id":row["event_id"],"ticket_id":row["ticket_id"],
        "created_at":row["created_at"]
    }

def _record_draft(user_id,path,*, sender,subject,body,message_id,pdfs,
                  connection,personal_key,storage_dir):
    sender=(sender or "")[:255].strip()
    subject=(subject or "")[:300].strip()
    body=(body or "")[:MAX_BODY_CHARS].strip()
    if not subject and not body:
        raise HTTPException(422,"The email has no readable subject or text.")
    if not body:
        body="No text body found. Review the purchase details manually."
    unique=_source_hash(sender,subject,body,message_id or "")
    files=[]
    cipher=personal_key(user_id)
    with connection(path,True) as db:
        _user_tables(db)
        row=db.execute("SELECT id FROM magic_inbox_drafts WHERE source_hash=?",(unique,)).fetchone()
        if row:return {"id":row["id"],"duplicate":True}
        count=db.execute("SELECT COUNT(*) FROM magic_inbox_drafts").fetchone()[0]
        if count>=MAX_DRAFTS:
            raise HTTPException(413,"Your Magic Inbox has reached its 250-message safety limit.")
        staged=[]
        try:
            if len(pdfs)>MAX_PDFS or sum(len(x[1]) for x in pdfs)>MAX_PDF_TOTAL:
                raise HTTPException(413,"Too many PDF attachments (max 3 PDFs / 9 MB).")
            for fname,blob in pdfs:
                if len(blob)>MAX_PDF or not blob.startswith(b"%PDF-"):
                    continue
                sub=storage_dir(user_id)/"vault"/"inbox"
                sub.mkdir(parents=True,exist_ok=True)
                name=secrets.token_hex(20)+".encrypted"
                file_path=sub/name
                with file_path.open("xb") as handle:
                    handle.write(cipher.encrypt(blob))
                staged.append(file_path)
                files.append({"filename":_sanitize_name(fname),"size":len(blob),
                              "path":"inbox/"+name,"sha256":hashlib.sha256(blob).hexdigest()})
            payload={
              "sender":sender,"subject":subject,"body":body[:MAX_BODY_CHARS],
              "candidate":extract_candidate(subject,body),
              "pdfs":files,
            }
            encoded=cipher.encrypt(json.dumps(payload,ensure_ascii=False).encode("utf-8"))
            cur=db.execute("""INSERT INTO magic_inbox_drafts
              (source_hash,status,encrypted_payload,created_at,updated_at)
              VALUES(?,'pending',?,?,?)""",(unique,encoded,now_stamp(),now_stamp()))
            return {"id":cur.lastrowid,"duplicate":False}
        except Exception:
            for file_path in staged:file_path.unlink(missing_ok=True)
            raise

def _verify_mailgun(timestamp,token,signature):
    key=_signing_key()
    if not key or not re.fullmatch(r"\d{9,12}",timestamp or ""):
        raise HTTPException(401,"Invalid Mailgun webhook authentication.")
    if not re.fullmatch(r"[A-Za-z0-9._~$+-]{20,180}",token or ""):
        raise HTTPException(401,"Invalid Mailgun webhook authentication.")
    if not re.fullmatch(r"[a-fA-F0-9]{64}",signature or ""):
        raise HTTPException(401,"Invalid Mailgun webhook authentication.")
    if abs(datetime.now(timezone.utc).timestamp()-int(timestamp))>900:
        raise HTTPException(401,"Mailgun webhook timestamp expired.")
    expected=hmac.new(key.encode("utf-8"),(timestamp+token).encode("utf-8"),
                      hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature.lower()):
        raise HTTPException(401,"Invalid Mailgun webhook signature.")

async def _read_small_form(request):
    """Enforce a hard body limit *before* multipart decoding or writing uploads."""
    header=request.headers.get("content-length")
    if header:
        try:
            if int(header)>MAX_WEBHOOK:raise HTTPException(413,"Inbound message too large.")
        except ValueError:
            raise HTTPException(400,"Invalid Content-Length.")
    raw=bytearray()
    async for chunk in request.stream():
        if len(raw)+len(chunk)>MAX_WEBHOOK:
            raise HTTPException(413,"Inbound message too large.")
        raw.extend(chunk)
    sent=False
    async def once():
        nonlocal sent
        if not sent:
            sent=True
            return {"type":"http.request","body":bytes(raw),"more_body":False}
        return {"type":"http.request","body":b"","more_body":False}
    cloned=Request(request.scope,once)
    return await cloned.form(max_files=5,max_fields=60,max_part_size=MAX_PDF_TOTAL)

class PasteEmail(BaseModel):
    subject: str = Field(default="",max_length=300)
    sender: str = Field(default="",max_length=255)
    body: str = Field(min_length=2,max_length=MAX_BODY_CHARS)

class ImportDraft(BaseModel):
    event_title: str = Field(min_length=2,max_length=200)
    starts_at: str
    existing_event_id: int|None = Field(default=None,gt=0)
    venue: str = Field(default="",max_length=200)
    city: str = Field(default="",max_length=120)
    country: str = Field(default="",max_length=100)
    provider: str = Field(default="",max_length=100)
    ticket_type: str = Field(default="E-Ticket",max_length=100)
    section: str = Field(default="",max_length=100)
    row_label: str = Field(default="",max_length=70)
    seats: str = Field(default="",max_length=150)
    quantity: int = Field(default=1,ge=1,le=1000)
    purchase_price: Decimal = Decimal("0")
    currency: str = "EUR"
    include_pdfs: bool = True

def install_magic_inbox(app,*,user_db,connection,select,personal_key,storage_dir,
                        auth_db,init_user_db,log,stamp,date_utc,cents,currency):
    @app.get("/api/inbox/settings")
    def settings(request:Request):
        user,_=user_db(request)
        alias=_get_alias(user["id"],auth_db,connection)
        domain=_domain()
        return {
            "email":alias+"@"+domain if _enabled() else None,
            "email_enabled":_enabled(),
            "upload_enabled":True,
            "provider":"Mailgun Routes" if _enabled() else None,
            "hint":"Email forwarding requires an inbound email domain, Mailgun MX/route and signed webhook. Until then, upload .eml or paste an order confirmation."
        }

    @app.post("/api/inbox/rotate")
    def rotate(request:Request):
        user,_=user_db(request,True)
        alias=_get_alias(user["id"],auth_db,connection,rotate=True)
        return {"ok":True,"email":alias+"@"+_domain() if _enabled() else None,
                "message":"Old inbox address was disabled immediately."}

    @app.get("/api/inbox/drafts")
    def drafts(request:Request,status:str=Query(default="all",pattern=r"^(all|pending|imported|dismissed)$")):
        user,path=user_db(request)
        cipher=personal_key(user["id"])
        with connection(path,True) as db:
            _user_tables(db)
            where="" if status=="all" else "WHERE status=?"
            args=() if status=="all" else (status,)
            rows=select(db,f"""SELECT id,status,encrypted_payload,event_id,ticket_id,created_at
              FROM magic_inbox_drafts {where} ORDER BY id DESC LIMIT 100""",args)
        return [_draft_summary(row,cipher) for row in rows]

    @app.get("/api/inbox/drafts/{draft_id}")
    def draft_detail(draft_id:int,request:Request):
        user,path=user_db(request)
        cipher=personal_key(user["id"])
        with connection(path,True) as db:
            _user_tables(db)
            row=select(db,"""SELECT id,status,encrypted_payload,event_id,ticket_id,created_at
                FROM magic_inbox_drafts WHERE id=?""",(draft_id,),True)
        if not row:raise HTTPException(404,"Inbox confirmation not found.")
        return _draft_summary(row,cipher)

    @app.post("/api/inbox/paste")
    def paste(payload:PasteEmail,request:Request):
        user,path=user_db(request,True)
        return _record_draft(user["id"],path,sender=payload.sender,subject=payload.subject,
                             body=payload.body,message_id="",pdfs=[],
                             connection=connection,personal_key=personal_key,storage_dir=storage_dir)

    @app.post("/api/inbox/upload")
    async def upload(request:Request,file:UploadFile=File(...)):
        user,path=user_db(request,True)
        if not (file.filename or "").lower().endswith(".eml"):
            raise HTTPException(415,"Upload a .eml email file, not an arbitrary attachment.")
        raw=await file.read(MAX_EML+1)
        if len(raw)>MAX_EML:
            raise HTTPException(413,"Email file must be 3 MB or smaller.")
        payload,pdfs=_eml_parts(raw)
        return _record_draft(user["id"],path,**payload,pdfs=pdfs,
                             connection=connection,personal_key=personal_key,storage_dir=storage_dir)

    @app.post("/api/inbox/mailgun")
    async def mailgun(request:Request):
        if not _enabled():
            raise HTTPException(503,"Inbound email is not configured on this server.")
        content_type=request.headers.get("content-type","").lower()
        if not (content_type.startswith("multipart/form-data") or
                content_type.startswith("application/x-www-form-urlencoded")):
            raise HTTPException(415,"Expected Mailgun form post; JSON endpoints are not supported.")
        form=await _read_small_form(request)
        try:
            timestamp=str(form.get("timestamp") or "")
            token=str(form.get("token") or "")
            signature=str(form.get("signature") or "")
            _verify_mailgun(timestamp,token,signature)
            recipient=str(form.get("recipient") or "")
            uid=_lookup_alias(recipient,auth_db,connection)
            if not uid:
                # Do not disclose whether any particular alias exists.
                return {"ok":True,"accepted":False}
            body=str(form.get("stripped-text") or form.get("body-plain") or "")[:MAX_BODY_CHARS]
            if not body and form.get("body-html"):
                body=html_to_text(str(form.get("body-html") or ""))
            subject=str(form.get("subject") or "")[:300]
            sender=str(form.get("sender") or form.get("from") or "")[:255]
            message_id=str(form.get("Message-Id") or form.get("message-id") or "")[:250]
            pdfs=[]
            for i in range(1,MAX_PDFS+1):
                attachment=form.get("attachment-"+str(i))
                if isinstance(attachment,UploadFile):
                    blob=await attachment.read(MAX_PDF+1)
                    if len(blob)<=MAX_PDF and blob.startswith(b"%PDF-"):
                        pdfs.append((attachment.filename or "ticket.pdf",blob))
            return {"ok":True,**_record_draft(uid,init_user_db(uid),
                sender=sender,subject=subject,body=body,message_id=message_id,pdfs=pdfs,
                connection=connection,personal_key=personal_key,storage_dir=storage_dir)}
        finally:
            await form.close()

    @app.post("/api/inbox/drafts/{draft_id}/import")
    def approve(draft_id:int,payload:ImportDraft,request:Request):
        user,path=user_db(request,True)
        title=payload.event_title.strip()
        if not title:
            raise HTTPException(422,"Confirm an event title.")
        moment=date_utc(payload.starts_at)
        cost=cents(payload.purchase_price)
        ccy=currency(payload.currency)
        cipher=personal_key(user["id"])
        with connection(path,True) as db:
            _user_tables(db)
            row=select(db,"SELECT * FROM magic_inbox_drafts WHERE id=?",(draft_id,),True)
            if not row:raise HTTPException(404,"Inbox confirmation not found.")
            if row["status"]!="pending":
                raise HTTPException(409,"This confirmation has already been reviewed.")
            try:
                original=json.loads(cipher.decrypt(row["encrypted_payload"]).decode("utf-8"))
            except Exception:
                raise HTTPException(500,"Cannot decrypt the Inbox draft.")
            if payload.existing_event_id is None:
                cur=db.execute("""INSERT INTO events(title,starts_at,venue,city,country,category,notes,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""",(title,moment,payload.venue.strip(),payload.city.strip(),
                    payload.country.strip(),"Concert",
                    "Reviewed Magic Inbox purchase confirmation #"+str(draft_id),stamp()))
                event_id=cur.lastrowid
                log(db,"inbox-create","event",event_id)
            else:
                event_id=payload.existing_event_id
                if not db.execute("SELECT 1 FROM events WHERE id=? AND archived=0",(event_id,)).fetchone():
                    raise HTTPException(404,"Selected event does not exist in your account.")
            guard_ticket_create(db,SimpleNamespace(event_id=event_id,section=payload.section,
                row_label=payload.row_label,seats=payload.seats))
            cur=db.execute("""INSERT INTO tickets(
                 event_id,provider,ticket_type,section,row_label,seats,quantity,
                 purchase_cents,currency,notes,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 (event_id,payload.provider.strip(),payload.ticket_type,
                  payload.section.strip(),payload.row_label.strip(),payload.seats.strip(),
                  payload.quantity,cost,ccy,
                  "Imported from reviewed Magic Inbox confirmation #"+str(draft_id),stamp()))
            ticket_id=cur.lastrowid
            attached=0
            if payload.include_pdfs:
                for pdf in original.get("pdfs",[]):
                    safe=storage_dir(user["id"])/"vault"/pdf["path"]
                    if not safe.is_file():
                        raise HTTPException(409,"An inbox PDF is missing. Review your vault backup.")
                    if db.execute("SELECT 1 FROM attachments WHERE ticket_id=? AND sha256=?",
                                   (ticket_id,pdf["sha256"])).fetchone():
                        continue
                    db.execute("""INSERT INTO attachments(ticket_id,filename,path,sha256,size,created_at)
                        VALUES(?,?,?,?,?,?)""",
                        (ticket_id,pdf["filename"],pdf["path"],pdf["sha256"],pdf["size"],stamp()))
                    attached+=1
            db.execute("""UPDATE magic_inbox_drafts SET status='imported',event_id=?,ticket_id=?,
                         updated_at=? WHERE id=?""",(event_id,ticket_id,stamp(),draft_id))
            log(db,"inbox-import","ticket",ticket_id)
        return {"ok":True,"event_id":event_id,"ticket_id":ticket_id,"attached_pdfs":attached}

    @app.post("/api/inbox/drafts/{draft_id}/dismiss")
    def dismiss(draft_id:int,request:Request):
        user,path=user_db(request,True)
        with connection(path,True) as db:
            _user_tables(db)
            row=db.execute("SELECT status FROM magic_inbox_drafts WHERE id=?",(draft_id,)).fetchone()
            if not row:raise HTTPException(404,"Inbox confirmation not found.")
            if row["status"]!="pending":raise HTTPException(409,"Only pending drafts can be dismissed.")
            db.execute("UPDATE magic_inbox_drafts SET status='dismissed',updated_at=? WHERE id=?",
                       (stamp(),draft_id))
        return {"ok":True}
