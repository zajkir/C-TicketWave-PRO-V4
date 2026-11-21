"""V3: integration secrets, official API search and event recap totals."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from test_app import clients, bootstrap, write, event_body


class MockHTTPResponse:
    def __init__(self, json_data, code=200):
        self.body = json_data
        self.status_code = code
    def json(self): return self.body
    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError('mocked provider error')


class MockProviderClient:
    def __init__(self, **kwargs): self.kwargs=kwargs
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    async def get(self, url, **kwargs):
        if 'ticketmaster.com' in url:
            assert kwargs['params']['apikey'] == 'TESTKEY123456'
            return MockHTTPResponse({'_embedded':{'events':[{
              'id':'TM123','name':'Noah Kahan - Boston',
              'dates':{'start':{'dateTime':'2027-05-30T19:00:00Z'}},
              '_embedded':{'venues':[{'name':'Fenway Park',
                'city':{'name':'Boston'},'country':{'name':'United States'}}]}
            }]}})
        assert kwargs['headers']['Accept']=='application/hal+json'
        return MockHTTPResponse({'total_items':2,'_embedded':{'items':[{'id':123},{'id':124}]}})
    async def post(self, url, **kwargs):
        assert url=='https://account.viagogo.com/oauth2/token'
        return MockHTTPResponse({'access_token':'this-is-sensitive','refresh_token':'refresh-secret',
            'scope':'read:sellerlistings write:sellerlistings read:events read:sales','expires_in':3600})


def test_personal_ticketmaster_key_search_and_storage(clients, monkeypatch):
    mod,admin,operator,viewer,data=clients
    csrf=bootstrap(admin)
    monkeypatch.setattr(mod.httpx, 'AsyncClient', MockProviderClient)
    conn=write(admin,'/integrations/ticketmaster',{'api_key':'TESTKEY123456'},csrf,method='PUT')
    assert conn.status_code==200,conn.text
    meta=admin.get('/api/integrations').json()
    assert meta['ticketmaster_discovery'] is True
    assert meta['ticketmaster_source']=='personal'
    assert 'TESTKEY123456' not in (data/'ticketwave.sqlite3').read_bytes().decode('latin1')
    search=admin.get('/api/discovery?q=Noah&city=Boston&country=US')
    assert search.status_code==200,search.text
    results=search.json(); assert results[0]['title']=='Noah Kahan - Boston'
    imported=write(admin,'/discovery/import',results[0],csrf)
    assert imported.status_code==200,imported.text
    assert len(admin.get('/api/events').json())==1
    w=write(admin,'/watchlist',{'keyword':'Noah Kahan','country':'US'},csrf)
    assert w.status_code==200
    sync=write(admin,'/watchlist/sync',{},csrf)
    assert sync.status_code==200,sync.text
    assert sync.json()['added']==0
    drop=write(admin,'/integrations/ticketmaster',{},csrf,method='DELETE')
    assert drop.status_code==200
    assert not admin.get('/api/integrations').json()['ticketmaster_discovery']


def test_viagogo_oauth_start_callback_connect(clients, monkeypatch):
    mod,admin,other,viewer,data=clients
    csrf=bootstrap(admin)
    save=write(admin,'/integrations/viagogo/app',{'client_id':'client456','client_secret':'secret456789'},csrf,method='PUT')
    assert save.status_code==200,save.text
    assert 'secret456789' not in (data/'ticketwave.sqlite3').read_bytes().decode('latin1')
    # Official Viagogo OAuth rejects plain HTTP callbacks.
    plain=write(admin,'/integrations/viagogo/authorize',{},csrf)
    assert plain.status_code==412
    # A configured public HTTPS URL enables authorization.
    monkeypatch.setenv('CTW_PUBLIC_BASE_URL','https://ticketwave.example.test')
    oauth=write(admin,'/integrations/viagogo/authorize',{},csrf)
    assert oauth.status_code==200,oauth.text
    url=oauth.json()['authorization_url']
    query=parse_qs(urlparse(url).query)
    assert query['client_id']==['client456']
    assert query['redirect_uri']==['https://ticketwave.example.test/api/integrations/viagogo/callback']
    assert 'write:sellerlistings' in query['scope'][0]
    monkeypatch.setattr(mod.httpx,'AsyncClient',MockProviderClient)
    state=query['state'][0]
    cb=other.get('/api/integrations/viagogo/callback',params={'state':state,'code':'authorized-test'},follow_redirects=False)
    assert cb.status_code==303,cb.text
    assert cb.headers['location']=='/?#integrations'
    meta=admin.get('/api/integrations').json()
    assert meta['viagogo']['status']=='connected'
    assert 'this-is-sensitive' not in str(meta)
    assert 'this-is-sensitive' not in (data/'ticketwave.sqlite3').read_bytes().decode('latin1')
    listing=admin.get('/api/integrations/viagogo/listings')
    assert listing.status_code==200,listing.text
    assert listing.json()['total_items']==2
    replay=other.get('/api/integrations/viagogo/callback',params={'state':state,'code':'again'})
    assert replay.status_code==400
    assert write(admin,'/integrations/viagogo',{},csrf,method='DELETE').status_code==200
    assert admin.get('/api/integrations').json()['viagogo']['status']=='not_configured'


def test_event_recap_backend_is_calculated(clients):
    mod,admin,operator,viewer,data=clients
    csrf=bootstrap(admin)
    eid=write(admin,'/events',event_body('2027 Boston Recap'),csrf).json()['id']
    ticket=admin.post('/api/tickets',data={'event_id':eid,'quantity':3,'section':'A','cost':'80',
        'currency_code':'EUR','source':'Ticketmaster','type':'E-Ticket'},
        headers={'X-CSRF-Token':csrf})
    assert ticket.status_code==200,ticket.text
    tid=ticket.json()['id']
    assert write(admin,'/sales',{'ticket_id':tid,'quantity':2,'amount':'400','fees':'30','channel':'viagogo'},csrf).status_code==200
    assert write(admin,'/expenses',{'event_id':eid,'label':'Delivery','amount':'10','currency':'EUR'},csrf).status_code==200
    recap=admin.get(f'/api/events/{eid}/recap')
    assert recap.status_code==200,recap.text
    r=recap.json()['summary']
    assert r['sold']==2 and r['quantity']==3
    assert r['sold_cost_cents']==16000 and r['revenue_cents']==40000
    assert r['fees_cents']==3000 and r['expenses_cents']==1000
    assert r['net_profit_cents']==20000
    assert r['roi_pct']==round(20000/17000*100,1)
    insights=admin.get('/api/insights').json()
    assert insights['top_events'][0]['id']==eid
    assert insights['top_events'][0]['net_profit_cents']==20000
