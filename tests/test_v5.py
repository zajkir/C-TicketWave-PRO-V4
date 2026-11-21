"""Regression checks for *per-user* data isolation and account security."""
import importlib.util
import io
import os
import secrets
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_clients(tmp_path, monkeypatch):
    monkeypatch.setenv('CTW_DATA_DIR',str(tmp_path/'persistent'))
    monkeypatch.setenv('CTW_LOCAL_DEV_TOKENS','1')
    monkeypatch.setenv('CTW_SECURE_COOKIES','0')
    monkeypatch.setenv('CTW_PUBLIC_BASE_URL','http://127.0.0.1:8765')
    monkeypatch.delenv('CTW_SMTP_HOST',raising=False)
    monkeypatch.delenv('CTW_GOOGLE_CLIENT_ID',raising=False)
    monkeypatch.delenv('CTW_GOOGLE_CLIENT_SECRET',raising=False)
    path=Path(__file__).resolve().parents[1]/'app.py'
    spec=importlib.util.spec_from_file_location('ticketwavev5_'+secrets.token_hex(5),path)
    m=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=m
    spec.loader.exec_module(m)
    with TestClient(m.app,base_url='http://testserver') as alice, TestClient(m.app,base_url='http://testserver') as bob:
        yield m,alice,bob,tmp_path/'persistent'


def signup(client,email,name):
    res=client.post('/api/auth/register',json={'email':email,'name':name,'password':'StrongPassword2026!'})
    assert res.status_code==200,res.text
    assert 'dev_verification_token' in res.json()
    res=client.post('/api/auth/verify',json={'token':res.json()['dev_verification_token']})
    assert res.status_code==200,res.text
    res=client.post('/api/auth/login',json={'email':email,'password':'StrongPassword2026!'})
    assert res.status_code==200,res.text
    return res.json()['csrf']


def event(client,csrf,title):
    date=(datetime.now(timezone.utc)+timedelta(days=25)).isoformat()
    res=client.post('/api/events',headers={'x-csrf-token':csrf},json={
        'title':title,'starts_at':date,'venue':'Main Arena','city':'Prague','country':'Czechia'})
    assert res.status_code==200,res.text
    return res.json()['id']


def ticket(client,csrf,event_id,quantity=3):
    res=client.post('/api/tickets',headers={'x-csrf-token':csrf},json={
        'event_id':event_id,'provider':'Ticketmaster','section':'421','row_label':'15','seats':'1-3',
        'quantity':quantity,'purchase_price':'55.00','currency':'EUR'})
    assert res.status_code==200,res.text
    return res.json()['id']


def test_private_databases_events_and_pdf_are_isolated(app_clients):
    m,alice,bob,data=app_clients
    assert alice.get('/health').json()['status']=='ok'
    assert alice.get('/api/events').status_code==401
    a=signup(alice,'alice@example.com','Alice Tickets')
    b=signup(bob,'bob@example.com','Bob Tickets')
    ea=event(alice,a,'Alice Concert')
    ta=ticket(alice,a,ea)
    eb=event(bob,b,'Bob Sports')
    tb=ticket(bob,b,eb,2)
    alice_events=alice.get('/api/events').json()
    bob_events=bob.get('/api/events').json()
    assert len(alice_events)==1 and alice_events[0]['title']=='Alice Concert'
    assert len(bob_events)==1 and bob_events[0]['title']=='Bob Sports'
    assert ea==eb and ta==tb # same IDs must NOT grant cross-user access
    alice_tickets=alice.get('/api/tickets').json()
    bob_tickets=bob.get('/api/tickets').json()
    assert alice_tickets[0]['event_title']=='Alice Concert'
    assert bob_tickets[0]['event_title']=='Bob Sports'
    # The *same ID* resolves to different private stores; Bob cannot download Alice's attachment.
    pdf=b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF'
    uploaded=alice.post(f'/api/tickets/{ta}/pdf',headers={'x-csrf-token':a},files={
        'file':('alice_ticket.pdf',io.BytesIO(pdf),'application/pdf')})
    assert uploaded.status_code==200,uploaded.text
    attachment=uploaded.json()['id']
    assert bob.get(f'/api/tickets/{tb}/pdfs').json()==[]
    assert bob.get(f'/api/tickets/{tb}/pdfs/{attachment}').status_code==404
    dl=alice.get(f'/api/tickets/{ta}/pdfs/{attachment}')
    assert dl.status_code==200 and dl.content==pdf
    userdirs=list((data/'users').iterdir())
    assert len(userdirs)==2
    assert all((p/'inventory.sqlite3').exists() for p in userdirs)
    assert all((p/'vault').exists() for p in userdirs)
    assert alice.get('/api/auth/state').json()['user']['id'] != bob.get('/api/auth/state').json()['user']['id']


def test_sales_atomically_update_only_own_inventory(app_clients):
    m,alice,bob,_=app_clients
    a=signup(alice,'alice@example.com','Alice')
    b=signup(bob,'bob@example.com','Bob')
    t=ticket(alice,a,event(alice,a,'Test Event'),2)
    assert alice.post('/api/sales',json={'ticket_id':t,'quantity':1,'revenue':'120','fees':'12',
        'currency':'EUR','sold_at':datetime.now(timezone.utc).isoformat()},
        headers={'x-csrf-token':a}).status_code==200
    assert alice.get('/api/tickets').json()[0]['sold_quantity']==1
    # Bob cannot sell Alice's ticket in Bob's independent database
    assert bob.post('/api/sales',json={'ticket_id':t,'quantity':1,'revenue':'120','fees':'12',
        'currency':'EUR','sold_at':datetime.now(timezone.utc).isoformat()},
        headers={'x-csrf-token':b}).status_code==404
    assert alice.post('/api/sales',json={'ticket_id':t,'quantity':2,'revenue':'240','fees':'0',
        'currency':'EUR','sold_at':datetime.now(timezone.utc).isoformat()},
        headers={'x-csrf-token':a}).status_code==409
    report=alice.get('/api/recaps').json()[0]
    assert report['revenue_cents']==12000
    assert report['fee_cents']==1200
    assert report['sold_cost_cents']==5500
    assert report['profit_cents']==5300
    assert bob.get('/api/recaps').json()==[]


def test_csrf_and_google_start_require_safe_configuration(app_clients):
    _,alice,bob,_=app_clients
    csrf=signup(alice,'alice@example.com','Alice')
    assert alice.get('/api/auth/state').json()['google_enabled'] is False
    assert alice.get('/api/auth/google/start').status_code==503
    future=(datetime.now(timezone.utc)+timedelta(days=20)).isoformat()
    payload={'title':'CSRF Test','starts_at':future}
    assert alice.post('/api/events',json=payload).status_code==403
    assert alice.post('/api/events',json=payload,headers={'x-csrf-token':'fake'}).status_code==403
    assert alice.post('/api/events',json=payload,headers={'x-csrf-token':csrf}).status_code==200


def test_production_registration_requires_email_provider_or_google(app_clients,monkeypatch):
    m,_,_,_=app_clients
    monkeypatch.setattr(m,'DEV_TOKENS',False)
    with TestClient(m.app) as client:
        resp=client.post('/api/auth/register',json={'email':'test@example.com','name':'User',
          'password':'StrongPassword2026!'})
        assert resp.status_code==503
