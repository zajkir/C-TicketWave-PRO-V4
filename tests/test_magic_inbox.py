"""Magic Inbox: encrypted staging, explicit review, Mailgun authentication, per-user isolation."""
import hashlib
import hmac
import io
import secrets
import sqlite3
import time
from email.message import EmailMessage

from test_v5 import app_clients, signup


def _confirm(client,csrf,draft_id,**kwargs):
    payload={
      "event_title":"NOVA Concert in Prague",
      "starts_at":"2027-06-21T18:30:00Z",
      "venue":"Main Arena","city":"Prague","country":"Czechia",
      "provider":"Ticketmaster","section":"421","row_label":"15",
      "seats":"25-26","quantity":2,"purchase_price":"79.50",
      "currency":"EUR","include_pdfs":True
    }
    payload.update(kwargs)
    return client.post(f"/api/inbox/drafts/{draft_id}/import",json=payload,
                       headers={"x-csrf-token":csrf})


def _sample_body():
    return (
      "Event: NOVA Concert in Prague\n"
      "Date: 2027-06-21\nTime: 18:30\nVenue: Main Arena\n"
      "City: Prague\nSection: 421\nRow: 15\nSeats: 25-26\n"
      "Quantity: 2\nPrice per ticket: €79.50\nTotal paid: €159.00\n"
    )


def test_paste_review_is_encrypted_private_and_idempotent(app_clients):
    _,alice,bob,data=app_clients
    assert alice.get("/api/inbox/settings").status_code==401
    a=signup(alice,"magic-alice@example.com","Magic Alice")
    b=signup(bob,"magic-bob@example.com","Magic Bob")
    status=alice.get("/api/inbox/settings")
    assert status.status_code==200
    assert status.json()["email_enabled"] is False
    assert status.json()["email"] is None
    assert status.json()["upload_enabled"] is True

    payload={"subject":"Your tickets for NOVA Concert","sender":"orders@example.com",
             "body":_sample_body()}
    unauthorized=alice.post("/api/inbox/paste",json=payload)
    assert unauthorized.status_code==403
    put=alice.post("/api/inbox/paste",json=payload,headers={"x-csrf-token":a})
    assert put.status_code==200,put.text
    assert put.json()["duplicate"] is False
    draft_id=put.json()["id"]
    repeat=alice.post("/api/inbox/paste",json=payload,headers={"x-csrf-token":a})
    assert repeat.status_code==200 and repeat.json()["duplicate"] is True
    assert repeat.json()["id"]==draft_id

    rows=alice.get("/api/inbox/drafts").json()
    assert len(rows)==1
    assert rows[0]["status"]=="pending"
    assert rows[0]["candidate"]["event_title"]=="NOVA Concert in Prague"
    assert rows[0]["candidate"]["local_date"]=="2027-06-21"
    assert rows[0]["candidate"]["purchase_price"]=="79.50"
    assert rows[0]["candidate"]["currency"]=="EUR"
    assert bob.get("/api/inbox/drafts").json()==[]
    assert bob.get(f"/api/inbox/drafts/{draft_id}").status_code==404
    assert alice.get("/api/events").json()==[]
    assert alice.get("/api/tickets").json()==[]

    uid=alice.get("/api/auth/state").json()["user"]["id"]
    with sqlite3.connect(data/"users"/uid/"inventory.sqlite3") as db:
        raw=db.execute("SELECT encrypted_payload FROM magic_inbox_drafts WHERE id=?",(draft_id,)).fetchone()[0]
        assert isinstance(raw,bytes) and b"NOVA Concert" not in raw
        assert b"orders@example.com" not in raw

    assert _confirm(alice,"invalid",draft_id).status_code==403
    assert bob.post(f"/api/inbox/drafts/{draft_id}/import",
        headers={"x-csrf-token":b},json={"event_title":"Fake","starts_at":"2027-01-01T12:00:00Z"}).status_code==404
    confirmed=_confirm(alice,a,draft_id)
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()["ticket_id"]==1
    assert confirmed.json()["event_id"]==1
    assert alice.get("/api/events").json()[0]["title"]=="NOVA Concert in Prague"
    tickets=alice.get("/api/tickets").json()
    assert tickets[0]["quantity"]==2
    assert tickets[0]["purchase_cents"]==7950
    assert bob.get("/api/events").json()==[]
    assert _confirm(alice,a,draft_id).status_code==409
    assert len(alice.get("/api/events").json())==1
    assert len(alice.get("/api/tickets").json())==1


def test_eml_pdf_staging_and_attach_only_after_approval(app_clients):
    _,alice,_,data=app_clients
    a=signup(alice,"magic-eml@example.com","PDF Reviewer")
    msg=EmailMessage()
    msg["From"]="Shop <orders@realshop.example>"
    msg["To"]="test@my.example"
    msg["Subject"]="Ticket purchase confirmed"
    msg["Message-ID"]="<magic-order-123@realshop.example>"
    msg.set_content(_sample_body())
    pdf=b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
    msg.add_attachment(pdf,maintype="application",subtype="pdf",filename="ticket-seat.pdf")

    eml=msg.as_bytes()
    uploaded=alice.post("/api/inbox/upload",headers={"x-csrf-token":a},
                        files={"file":("confirmation.eml",io.BytesIO(eml),"message/rfc822")})
    assert uploaded.status_code==200,uploaded.text
    draft_id=uploaded.json()["id"]
    detail=alice.get(f"/api/inbox/drafts/{draft_id}").json()
    assert detail["status"]=="pending"
    assert detail["pdfs"]==[{"filename":"ticket-seat.pdf","size":len(pdf)}]
    assert alice.get("/api/tickets").json()==[]

    uid=alice.get("/api/auth/state").json()["user"]["id"]
    stage=list((data/"users"/uid/"vault"/"inbox").glob("*.encrypted"))
    assert len(stage)==1 and b"%PDF" not in stage[0].read_bytes()
    duplicate=alice.post("/api/inbox/upload",headers={"x-csrf-token":a},
                        files={"file":("confirmation.eml",io.BytesIO(eml),"message/rfc822")})
    assert duplicate.status_code==200 and duplicate.json()["duplicate"]
    assert len(list((data/"users"/uid/"vault"/"inbox").glob("*.encrypted")))==1

    imported=_confirm(alice,a,draft_id)
    assert imported.status_code==200,imported.text
    assert imported.json()["attached_pdfs"]==1
    docs=alice.get("/api/tickets/1/pdfs").json()
    assert docs[0]["filename"]=="ticket-seat.pdf"
    downloaded=alice.get(f"/api/tickets/1/pdfs/{docs[0]['id']}")
    assert downloaded.status_code==200 and downloaded.content==pdf
    assert _confirm(alice,a,draft_id).status_code==409


def test_dismiss_draft_deletes_staged_pdf_without_touching_other_users(app_clients):
    _,alice,bob,data=app_clients
    a=signup(alice,"magic-dismiss@example.com","Alice")
    b=signup(bob,"magic-second@example.com","Bob")
    msg=EmailMessage()
    msg["From"]="shop@example.org"
    msg["Subject"]="Your tickets for private show"
    msg.set_content("Event: Private Show\nDate: 2027-09-19\nQuantity: 1")
    msg.add_attachment(b"%PDF-1.4\nprivate PDF\n%%EOF",
                       maintype="application",subtype="pdf",filename="secret.pdf")
    raw=msg.as_bytes()
    da=alice.post("/api/inbox/upload",headers={"x-csrf-token":a},
                  files={"file":("a.eml",raw,"message/rfc822")}).json()["id"]
    db=bob.post("/api/inbox/upload",headers={"x-csrf-token":b},
                files={"file":("b.eml",raw,"message/rfc822")}).json()["id"]
    ua=alice.get("/api/auth/state").json()["user"]["id"]
    ub=bob.get("/api/auth/state").json()["user"]["id"]
    a_dir=data/"users"/ua/"vault"/"inbox"
    b_dir=data/"users"/ub/"vault"/"inbox"
    assert len(list(a_dir.glob("*.encrypted")))==1
    assert len(list(b_dir.glob("*.encrypted")))==1
    deleted=alice.post(f"/api/inbox/drafts/{da}/dismiss",headers={"x-csrf-token":a})
    assert deleted.status_code==200,deleted.text
    assert len(list(a_dir.glob("*.encrypted")))==0
    assert len(list(b_dir.glob("*.encrypted")))==1
    assert bob.get(f"/api/inbox/drafts/{db}").json()["status"]=="pending"
    assert _confirm(alice,a,da).status_code==409


def test_signed_mailgun_alias_routing_rotation_and_expiry(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    a=signup(alice,"magic-route-a@example.com","Route A")
    b=signup(bob,"magic-route-b@example.com","Route B")
    monkeypatch.setenv("CTW_MAGIC_INBOX_DOMAIN","inbox.example-mail.test")
    monkeypatch.setenv("CTW_MAILGUN_WEBHOOK_SIGNING_KEY","test-mailgun-secret-not-an-api-key")
    addr_a=alice.get("/api/inbox/settings").json()["email"]
    addr_b=bob.get("/api/inbox/settings").json()["email"]
    assert addr_a!=addr_b
    assert addr_a.endswith("@inbox.example-mail.test")

    def form_for(recipient, timestamp=None, token=None):
        timestamp=timestamp or str(int(time.time()))
        token=token or secrets.token_hex(25)
        sig=hmac.new(b"test-mailgun-secret-not-an-api-key",
                     (timestamp+token).encode(),hashlib.sha256).hexdigest()
        return {"timestamp":timestamp,"token":token,"signature":sig,
                "recipient":recipient,"sender":"orders@ticketmaster.example",
                "subject":"Your tickets for NOVA Concert",
                "body-plain":_sample_body(),"Message-Id":"<distinct-order-A>"}

    invalid=form_for(addr_a);invalid["signature"]="0"*64
    assert alice.post("/api/inbox/mailgun",data=invalid).status_code==401
    expired=form_for(addr_a,timestamp=str(int(time.time())-1900))
    assert alice.post("/api/inbox/mailgun",data=expired).status_code==401
    assert alice.get("/api/inbox/drafts").json()==[]

    received=alice.post("/api/inbox/mailgun",data=form_for(addr_a))
    assert received.status_code==200,received.text
    assert received.json()["duplicate"] is False
    assert len(alice.get("/api/inbox/drafts").json())==1
    assert bob.get("/api/inbox/drafts").json()==[]
    # Duplicate retry must not create a second confirmation.
    duplicated=alice.post("/api/inbox/mailgun",data=form_for(addr_a))
    assert duplicated.status_code==200 and duplicated.json()["duplicate"] is True

    change=alice.post("/api/inbox/rotate",headers={"x-csrf-token":a})
    assert change.status_code==200
    new_addr=change.json()["email"]
    assert new_addr!=addr_a
    dropped=alice.post("/api/inbox/mailgun",data=form_for(addr_a))
    assert dropped.status_code==200 and dropped.json()["accepted"] is False
    new_message=form_for(new_addr)
    new_message["body-plain"]=new_message["body-plain"]+"Reference: different order"
    assert alice.post("/api/inbox/mailgun",data=new_message).status_code==200
    assert len(alice.get("/api/inbox/drafts").json())==2
    # A separate account has a different alias and receives only its own mail.
    assert bob.post("/api/inbox/mailgun",data=form_for(addr_b)).status_code==200
    assert len(bob.get("/api/inbox/drafts").json())==1
    assert len(alice.get("/api/inbox/drafts").json())==2
    assert not alice.get("/api/events").json()
    assert not bob.get("/api/tickets").json()


def test_magic_inbox_does_not_guess_event_dates_or_import_without_confirmation(app_clients):
    _,alice,_,_=app_clients
    token=signup(alice,"magic-uncertain@example.com","Review Alice")
    draft=alice.post("/api/inbox/paste",headers={"x-csrf-token":token},json={
        "subject":"Your order was received",
        "body":"Thank you for shopping. Your order will be processed soon. Total paid: 99 EUR"
    }).json()["id"]
    candidate=alice.get(f"/api/inbox/drafts/{draft}").json()["candidate"]
    assert candidate["event_title"]==""
    assert candidate["local_date"]==""
    assert candidate["purchase_price"]==""
    assert candidate["total_price"]=="99"
    assert candidate["warnings"]
    assert _confirm(alice,token,draft,starts_at="tomorrow").status_code==422
    assert alice.get("/api/events").json()==[]
    assert alice.get("/api/tickets").json()==[]
