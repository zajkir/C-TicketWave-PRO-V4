"""Sale Recap is private, currency-safe, and based only on stored sale data."""
from datetime import datetime, timezone

from test_v5 import app_clients, signup, event, ticket


def record(client, csrf, tid, revenue="150", fees="10", units=1, currency="EUR"):
    r=client.post("/api/sales",headers={"x-csrf-token":csrf},json={
        "ticket_id":tid,"quantity":units,"revenue":revenue,"fees":fees,
        "currency":currency,"sold_at":datetime.now(timezone.utc).isoformat(),
        "channel":"Direct","reference":"REC-REFERENCE-0001"
    })
    assert r.status_code==200,r.text
    return r.json()["id"]


def test_sale_details_require_signin_and_are_isolated(app_clients):
    _,alice,bob,_=app_clients
    assert alice.get("/api/sales/1").status_code==401
    a=signup(alice,"recap-alice@example.com","Recap Alice")
    b=signup(bob,"recap-bob@example.com","Recap Bob")
    ta=ticket(alice,a,event(alice,a,"Recap concert"),3)
    tb=ticket(bob,b,event(bob,b,"Another concert"),3)
    sa=record(alice,a,ta)
    assert bob.get(f"/api/sales/{sa}").status_code==404
    sb=record(bob,b,tb)
    # Identical numeric IDs are legitimate in distinct private account DBs.
    assert sa==sb
    assert alice.get(f"/api/sales/{sa}").json()["event_title"]=="Recap concert"
    assert bob.get(f"/api/sales/{sb}").json()["event_title"]=="Another concert"
    assert alice.get("/api/sales/0").status_code==404
    assert alice.get("/api/sales/99999").status_code==404


def test_margin_roi_and_nonexistent_payout_are_accurate(app_clients):
    _,alice,_,_=app_clients
    key=signup(alice,"recap-finance@example.com","Recap Finance")
    t=ticket(alice,key,event(alice,key,"Finance example"),4)
    sid=record(alice,key,t,revenue="200",fees="20",units=2)
    r=alice.get(f"/api/sales/{sid}")
    assert r.status_code==200
    x=r.json()
    assert x["quantity"]==2
    assert x["purchase_cents"]==5500
    assert x["sold_purchase_cost_cents"]==11000
    assert x["revenue_cents"]==20000
    assert x["fee_cents"]==2000
    assert x["net_receipts_cents"]==18000
    assert x["sale_margin_cents"]==7000
    assert x["sale_roi_percent"]==round(7000*100/11000,2)
    assert x["margin_excludes_event_expenses"] is True
    assert x["payout_status"] is None
    assert "not tracked" in x["payout_note"]
    assert x["reference"]=="REC-REFERENCE-0001"
    assert x["event_title"]=="Finance example"


def test_cross_currency_sale_never_invents_profit(app_clients):
    _,alice,_,_=app_clients
    key=signup(alice,"recap-mixed@example.com","Mixed Money")
    t=ticket(alice,key,event(alice,key,"Mixed currency concert"),2)
    sid=record(alice,key,t,revenue="100",fees="5",currency="GBP")
    r=alice.get(f"/api/sales/{sid}")
    assert r.status_code==200
    x=r.json()
    assert x["currency"]=="GBP"
    assert x["purchase_currency"]=="EUR"
    assert x["net_receipts_cents"]==9500
    assert x["sale_margin_cents"] is None
    assert x["sold_purchase_cost_cents"] is None
    assert x["sale_roi_percent"] is None
    assert x["currency_mismatch"] is True


def test_negative_margin_and_missing_investment(app_clients):
    _,alice,_,_=app_clients
    key=signup(alice,"recap-loss@example.com","Loss Example")
    t=ticket(alice,key,event(alice,key,"Loss Concert"),2)
    sid=record(alice,key,t,revenue="20",fees="2")
    x=alice.get(f"/api/sales/{sid}").json()
    assert x["sale_margin_cents"]==-3700
    assert x["sale_roi_percent"]<0


def test_sale_recap_frontend_is_last_and_has_a11y_data_controls(app_clients):
    _,alice,_,_=app_clients
    response=alice.get("/")
    assert response.status_code==200
    html=response.text
    assert "/static/sale-recap.css?v=sale-1" in html
    assert "/static/sale-recap.js?v=sale-1" in html
    assert html.index("experience.js?v=experience-5")<html.index("sale-recap.js?v=sale-1")
    assert html.index("experience.css?v=experience-5")<html.index("sale-recap.css?v=sale-1")
    js=alice.get("/static/sale-recap.js").text
    css=alice.get("/static/sale-recap.css").text
    for term in [
        "api('/sales/'+id)", "renderSales=async function renderSalesWithRecaps",
        "data-ceyrl-sale-open", "data-sale-mode", "data-sale-tab",
        "sale-recap-sheet", "sale-recap-aurora",
        "previousShowAuth=showAuth", "aria-modal", "role=\"tabpanel\"",
        "Marža", "Stav výplaty", "Neevidovaný", "margin_excludes_event_expenses",
    ]:
        # UI refers to actual computed fields, not simulated provider outcomes.
        assert term in (js+css)
    for term in ["prefers-reduced-motion:reduce", "body.motion-off", "@media print",
                 "sale-orbit-1", "sale-wave-flow", "sale-full-reveal"]:
        assert term in css
    assert "buyer_score" not in js
    assert "payout_processed" not in js
    assert "Verified buyer" not in js
