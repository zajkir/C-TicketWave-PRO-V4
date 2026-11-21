"""Ceyrl V6 intelligence: real DB data, no cross-account leakage, safe search."""
from datetime import datetime, timezone

from test_v5 import app_clients, signup, event, ticket


def test_v6_private_insights_and_search_are_isolated(app_clients):
    _, alice, bob, _ = app_clients
    assert alice.get('/api/v6/insights').status_code == 401
    assert alice.get('/api/v6/search?q=anything').status_code == 401

    alice_csrf = signup(alice, 'alice@example.com', 'Alice')
    signup(bob, 'bob@example.com', 'Bob')
    a_event = event(alice, alice_csrf, 'Alice Secret Tour')
    ticket(alice, alice_csrf, a_event)

    a_insights = alice.get('/api/v6/insights?days=30')
    b_insights = bob.get('/api/v6/insights?days=30')
    assert a_insights.status_code == 200, a_insights.text
    assert b_insights.status_code == 200, b_insights.text
    assert a_insights.json()['total_events'] == 1
    assert a_insights.json()['unfiled_lots'] == 1
    assert a_insights.json()['upcoming'][0]['title'] == 'Alice Secret Tour'
    assert b_insights.json()['total_events'] == 0
    assert b_insights.json()['upcoming'] == []
    assert b_insights.json()['unfiled_lots'] == 0

    a_search = alice.get('/api/v6/search?q=Alice')
    b_search = bob.get('/api/v6/search?q=Alice')
    assert a_search.status_code == 200, a_search.text
    assert b_search.status_code == 200, b_search.text
    assert any(row['kind']=='event' and row['title']=='Alice Secret Tour'
               for row in a_search.json()['results'])
    assert b_search.json()['results'] == []
    # Wildcards are searched literally, not accidentally applied to all records.
    assert alice.get('/api/v6/search?q=%25X').json()['results'] == []


def test_v6_sales_window_calculations_and_validations(app_clients):
    _, alice, _, _ = app_clients
    csrf = signup(alice,'sales@example.com','Sales')
    event_id = event(alice,csrf,'Margin Example')
    ticket_id = ticket(alice,csrf,event_id,2)

    sale = alice.post('/api/sales',json={
        'ticket_id':ticket_id,'quantity':1,'revenue':'120.00','fees':'12.00',
        'currency':'EUR','sold_at':datetime.now(timezone.utc).isoformat(),
    },headers={'x-csrf-token':csrf})
    assert sale.status_code == 200, sale.text

    data = alice.get('/api/v6/insights?days=7').json()
    assert data['metrics']['revenue_cents'] == 12000
    assert data['metrics']['fee_cents'] == 1200
    assert data['metrics']['sold_cost_cents'] == 5500
    assert data['metrics']['margin_cents'] == 5300
    assert data['metrics']['tickets'] == 1
    assert data['currency'] == 'EUR'

    assert alice.get('/api/v6/insights?days=1').status_code == 422
    assert alice.get('/api/v6/insights?days=366').status_code == 422
    assert alice.get('/api/v6/search?q=A').status_code == 422
    assert alice.get('/api/v6/search?q=' + 'a'*81).status_code == 422
