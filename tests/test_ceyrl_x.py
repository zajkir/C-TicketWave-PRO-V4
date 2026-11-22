"""Functional regression tests for Ceyrl's four optional modules."""
from datetime import datetime,timezone
import io

from test_v5 import app_clients, signup, event, ticket


def test_shield_rejects_same_seat_and_pauses_local_listing(app_clients):
    _, alice, bob, _ = app_clients
    a=signup(alice,'shield-alice@example.com','Shield Alice')
    b=signup(bob,'shield-bob@example.com','Shield Bob')
    eid=event(alice,a,'Same Seat Concert')
    tid=ticket(alice,a,eid,3)
    # Known sector/row and explicit seat tokens must be blocked.
    dup=alice.post('/api/tickets',headers={'x-csrf-token':a},json={
        'event_id':eid,'provider':'Ticketmaster','section':'421','row_label':'15',
        'seats':'2,3','quantity':2,'purchase_price':'55','currency':'EUR'
    })
    assert dup.status_code==409,dup.text
    # Another user is independent, even if database IDs coincide.
    eb=event(bob,b,'Bob Concert')
    assert ticket(bob,b,eb,3)==tid
    shield=alice.get('/api/x/shield')
    assert shield.status_code==200
    assert shield.json()['status']=='clear'

    listing=alice.post('/api/listings',headers={'x-csrf-token':a},json={
       'ticket_id':tid,'marketplace':'viagogo','price':'120',
       'currency':'EUR','status':'listed'
    })
    assert listing.status_code==200,listing.text
    sold=alice.post('/api/sales',headers={'x-csrf-token':a},json={
       'ticket_id':tid,'quantity':1,'revenue':'120','fees':'12','currency':'EUR',
       'sold_at':datetime.now(timezone.utc).isoformat(),'channel':'viagogo',
       'reference':'ORDER-123'
    })
    assert sold.status_code==200,sold.text
    assert sold.json()['paused_local_listings']==1
    listings=alice.get('/api/listings').json()
    assert listings[0]['status']=='paused'
    assert bob.get('/api/listings').json()==[]
    duplicate_sale=alice.post('/api/sales',headers={'x-csrf-token':a},json={
       'ticket_id':tid,'quantity':1,'revenue':'120','fees':'12','currency':'EUR',
       'sold_at':datetime.now(timezone.utc).isoformat(),'channel':'viagogo',
       'reference':'ORDER-123'
    })
    assert duplicate_sale.status_code==409
    assert alice.get('/api/tickets').json()[0]['sold_quantity']==1


def test_delivery_readiness_updates_are_private(app_clients):
    _,alice,bob,_=app_clients
    a=signup(alice,'delivery-a@example.com','Delivery Alice')
    signup(bob,'delivery-b@example.com','Delivery Bob')
    tid=ticket(alice,a,event(alice,a,'Delivery Concert'))
    rows=alice.get('/api/x/delivery').json()
    assert len(rows)==1
    assert rows[0]['readiness']['score']<100
    assert bob.get('/api/x/delivery').json()==[]

    updated=alice.put(f'/api/x/delivery/{tid}',headers={'x-csrf-token':a},json={
        'method':'pdf','transfer_confirmed':False,'possession_confirmed':False,
        'restrictions_checked':True,'availability_confirmed':True,
        'notes':'Verified terms and delivery availability.'
    })
    assert updated.status_code==200,updated.text
    pdf=b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF'
    upload=alice.post(f'/api/tickets/{tid}/pdf',headers={'x-csrf-token':a},files={
        'file':('delivery.pdf',io.BytesIO(pdf),'application/pdf')
    })
    assert upload.status_code==200,upload.text
    row=alice.get('/api/x/delivery').json()[0]
    assert row['readiness']['score']==100,row['readiness']
    assert row['readiness']['tasks']==[]
    assert row['readiness']['status']=='ready_to_review'
    assert bob.put(f'/api/x/delivery/{tid}',headers={'x-csrf-token':'invalid'},json={
        'method':'pdf'
    }).status_code in (403,404)


def test_radar_encryption_search_watch_refresh_import_per_account(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    a=signup(alice,'radar-a@example.com','Radar Alice')
    signup(bob,'radar-b@example.com','Radar Bob')
    assert alice.get('/api/x/radar/status').json()['connected'] is True
    import ceyrl_features
    key_saved=alice.put('/api/x/radar/key',headers={'x-csrf-token':a},
                        json={'api_key':'MyDiscoveryAPIKEY1234567890'})
    assert key_saved.status_code==200,key_saved.text
    assert alice.get('/api/x/radar/status').json()['personal_key'] is True
    assert bob.get('/api/x/radar/status').json()['connected'] is True

    calls=[]
    mocked={
      'id':'Z7r9jZ1A1aBcd','name':'Verified Artist Tour',
      'dates':{'start':{'dateTime':'2027-06-12T18:00:00Z','localDate':'2027-06-12'}},
      '_embedded':{'venues':[{'name':'Great Arena','city':{'name':'Boston'},
                              'country':{'name':'United States'}}]},
      'url':'https://www.ticketmaster.com/event'
    }
    def fake_tm(key,params,one_id=None):
        calls.append((key,params,one_id))
        return mocked if one_id else {'_embedded':{'events':[mocked]}}
    monkeypatch.setattr(ceyrl_features,'call_tm',fake_tm)

    search=alice.get('/api/x/radar/search?q=Artist&country=US')
    assert search.status_code==200,search.text
    assert search.json()['events'][0]['name']=='Verified Artist Tour'
    watch=alice.post('/api/x/radar/watches',headers={'x-csrf-token':a},
        json={'query':'Verified Artist','country':'US'})
    assert watch.status_code==200,watch.text
    refresh=alice.post('/api/x/radar/refresh',headers={'x-csrf-token':a})
    assert refresh.status_code==200,refresh.text
    assert refresh.json()['new']==1
    repeat=alice.post('/api/x/radar/refresh',headers={'x-csrf-token':a})
    assert repeat.status_code==200 and repeat.json()['skipped']==1
    assert len(alice.get('/api/x/radar/watches').json()['hits'])==1
    assert bob.get('/api/x/radar/watches').json()['hits']==[]
    imported=alice.post('/api/x/radar/import/Z7r9jZ1A1aBcd',
                        headers={'x-csrf-token':a})
    assert imported.status_code==200,imported.text
    assert alice.get('/api/events').json()[0]['title']=='Verified Artist Tour'
    assert bob.get('/api/events').json()==[]
    assert all(c[0]=='MyDiscoveryAPIKEY1234567890' for c in calls)


def test_private_local_copilot_is_read_only_and_opt_in(app_clients):
    _,alice,bob,_=app_clients
    a=signup(alice,'copilot-a@example.com','Copilot Alice')
    signup(bob,'copilot-b@example.com','Copilot Bob')
    ticket(alice,a,event(alice,a,'Alice Tour'))
    assert alice.post('/api/x/copilot',json={'question':'Which PDFs are missing?'}).status_code==403
    response=alice.post('/api/x/copilot',headers={'x-csrf-token':a},
            json={'question':'Which PDFs are missing?','use_ai':False})
    assert response.status_code==200,response.text
    assert response.json()['mode']=='local'
    assert response.json()['snapshot']['lots_without_pdf']==1
    assert '1 available ticket lot' in response.json()['answer']
    other=bob.get('/api/x/shield')
    assert other.status_code==200 and other.json()['status']=='clear'
    assert bob.get('/api/events').json()==[]
