"""Ceyrl Shield: explicit-seat collision detection, listing checks and delivery score."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from fastapi import HTTPException

def seat_tokens(value: str):
    """Only normalize unambiguous seats. Unclear labels are deliberately not blocked."""
    source = (value or "").upper().strip().replace("–", "-").replace("—", "-")
    source = re.sub(r"\b(SEATS?|SITZ|SEDADL[OÁ])\s*[:#]?\s*", "", source)
    if not source or any(word in source for word in ("GENERAL", "GA", "STANDING", "FREE SEATING")):
        return set()
    chunks = re.split(r"[,;/]+", source)
    tokens = set()
    for part in chunks:
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"([A-Z]{0,3})(\d{1,4})\s*-\s*([A-Z]{0,3})(\d{1,4})", part)
        if match:
            p1, a, p2, b = match.groups()
            p2 = p2 or p1
            left, right = int(a), int(b)
            if p1 != p2 or left > right or right-left > 100:
                continue
            tokens.update(f"{p1}{n}" for n in range(left, right + 1))
        elif re.fullmatch(r"[A-Z]{0,3}\d{1,4}", part):
            tokens.add(part)
        # Anything else can be a description, not a provable seat identity.
    return tokens

def normalize_location(section, row):
    return ((section or "").strip().casefold(), (row or "").strip().casefold())

def seat_collisions(db, event_id, section, row, seats, exclude_id=None):
    location = normalize_location(section, row)
    incoming = seat_tokens(seats)
    if not all(location) or not incoming:
        return []
    others = db.execute(
        "SELECT id,section,row_label,seats FROM tickets WHERE event_id=?",
        (event_id,)
    ).fetchall()
    collisions = []
    for item in others:
        if exclude_id is not None and item["id"] == exclude_id:
            continue
        if normalize_location(item["section"], item["row_label"]) != location:
            continue
        overlap = sorted(incoming.intersection(seat_tokens(item["seats"])))
        if overlap:
            collisions.append({"ticket_id":item["id"], "seats":overlap[:40]})
    return collisions

def guard_ticket_create(db, payload):
    conflicts = seat_collisions(db,payload.event_id,payload.section,payload.row_label,payload.seats)
    if conflicts:
        details = ", ".join(", ".join(c["seats"]) for c in conflicts[:2])
        raise HTTPException(409,
            "Double-Sale Shield: these exact seats already exist in your inventory (" +
            details + "). Review the existing ticket lot.")

def shield_report(db):
    rows=db.execute("""
      SELECT t.id,t.event_id,t.section,t.row_label,t.seats,t.quantity,t.sold_quantity,
             e.title AS event_title
      FROM tickets t JOIN events e ON e.id=t.event_id ORDER BY t.id
    """).fetchall()
    conflicts=[]
    visited=set()
    for row in rows:
        for match in seat_collisions(db,row["event_id"],row["section"],row["row_label"],row["seats"],row["id"]):
            key=tuple(sorted((row["id"],match["ticket_id"])))
            if key not in visited:
                visited.add(key)
                conflicts.append({
                    "kind":"duplicate_seat", "ticket_ids":list(key),
                    "event_title":row["event_title"],
                    "seats":match["seats"],
                    "message":"Possibly duplicate exact seats in separate ticket lots."
                })
    active=db.execute("""
      SELECT ticket_id,COUNT(*) AS count,GROUP_CONCAT(id) AS ids
      FROM listings WHERE status IN ('ready','listed')
      GROUP BY ticket_id HAVING COUNT(*) > 1
    """).fetchall()
    for row in active:
        conflicts.append({
          "kind":"multiple_active_listings", "ticket_ids":[row["ticket_id"]],
          "listing_ids":[int(x) for x in row["ids"].split(",")],
          "message":"Multiple local active listings refer to the same ticket lot."
        })
    stale=db.execute("""
      SELECT l.id AS listing_id,l.ticket_id FROM listings l
      JOIN tickets t ON t.id=l.ticket_id
      WHERE l.status IN ('ready','listed') AND t.sold_quantity>=t.quantity
    """).fetchall()
    for row in stale:
        conflicts.append({
            "kind":"sold_out_listing","ticket_ids":[row["ticket_id"]],
            "listing_ids":[row["listing_id"]],
            "message":"A sold-out ticket lot still has a local active listing."
        })
    return {
        "status":"attention" if conflicts else "clear",
        "conflicts":conflicts[:100],
        "warning":"Local inventory safety only. External marketplace listings must be paused or cancelled on each provider separately."
    }

VALID_METHODS={"unknown","pdf","mobile_transfer","mobile_app","physical","will_call"}
def delivery_score(ticket, delivery, pdf_count):
    method=(delivery or {}).get("method","unknown")
    score=0
    tasks=[]
    if ticket["starts_at"]:
        score+=20
    else: tasks.append("Confirm the event date.")
    if (ticket["section"] and ticket["row_label"] and ticket["seats"]) or (
        (ticket["ticket_type"] or "").lower().startswith(("general","standing"))
    ):
        score+=10
    else:
        tasks.append("Confirm seating details or the general-admission ticket type.")
    if method!="unknown":
        score+=20
    else: tasks.append("Choose the actual delivery method.")
    if method=="pdf":
        if pdf_count:
            score+=20
        else:
            tasks.append("Attach the PDF for PDF delivery.")
    elif method in ("mobile_transfer","mobile_app"):
        if (delivery or {}).get("transfer_confirmed"):
            score+=20
        else: tasks.append("Confirm that transfer is currently permitted by the ticket provider.")
    elif method in ("physical","will_call"):
        if (delivery or {}).get("possession_confirmed"):
            score+=20
        else: tasks.append("Confirm possession or collection instructions.")
    else:
        tasks.append("Confirm when and how the ticket can actually be delivered.")
    if (delivery or {}).get("restrictions_checked"):
        score+=20
    else: tasks.append("Review provider transfer, resale and ticket-personalization restrictions.")
    if (delivery or {}).get("availability_confirmed"):
        score+=10
    else: tasks.append("Confirm when the ticket becomes available for delivery.")
    score=min(100,score)
    return {
        "score":score,
        "status":"ready_to_review" if score>=85 else "needs_attention",
        "tasks":tasks,
        "method":method,
        "notice":"This is a completeness checklist, not verification that a ticket is valid, transferable, accepted by a venue or actually delivered."
    }
