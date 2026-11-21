"""Ceyrl V6 read-only intelligence layer.

All queries take their database path from the authenticated session via user_db.
No user ID, path, account ID or storage key is accepted from the browser.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import Query, Request


def install_v6_routes(app, *, user_db, connection, select):
    def eur_window(db, lower, upper=None):
        where = "s.currency='EUR' AND t.currency='EUR' AND s.sold_at>=?"
        params = [lower]
        if upper is not None:
            where += " AND s.sold_at<?"
            params.append(upper)
        row = db.execute(
            "SELECT COUNT(*) AS transactions, "
            "COALESCE(SUM(s.quantity),0) AS tickets, "
            "COALESCE(SUM(s.revenue_cents),0) AS revenue_cents, "
            "COALESCE(SUM(s.fee_cents),0) AS fee_cents, "
            "COALESCE(SUM(s.quantity*t.purchase_cents),0) AS sold_cost_cents "
            "FROM sales s JOIN tickets t ON t.id=s.ticket_id WHERE " + where,
            tuple(params)
        ).fetchone()
        result = dict(row)
        result['margin_cents'] = result['revenue_cents'] - result['fee_cents'] - result['sold_cost_cents']
        return result

    @app.get('/api/v6/insights')
    def v6_insights(request: Request, days: int = Query(default=30, ge=7, le=365)):
        _, path = user_db(request)
        today = datetime.now(timezone.utc)
        start = (today - timedelta(days=days)).isoformat()
        prev_start = (today - timedelta(days=days * 2)).isoformat()
        with connection(path) as db:
            window = eur_window(db, start)
            previous = eur_window(db, prev_start, start)
            next_rows = select(db, '''
                SELECT e.id, e.title, e.starts_at, e.venue, e.city,
                       COALESCE(SUM(t.quantity - t.sold_quantity),0) AS available,
                       COUNT(t.id) AS ticket_lots
                FROM events e
                LEFT JOIN tickets t ON t.event_id=e.id
                WHERE e.archived=0 AND e.starts_at>=?
                GROUP BY e.id ORDER BY e.starts_at ASC LIMIT 25
            ''', (today.isoformat(),))
            next_events = []
            for event in next_rows:
                try:
                    start_at = datetime.fromisoformat(event['starts_at'].replace('Z', '+00:00'))
                    if start_at.tzinfo is None:
                        start_at = start_at.replace(tzinfo=timezone.utc)
                    days_until = max(0, (start_at - today).total_seconds() / 86400)
                except (TypeError, ValueError):
                    continue
                if days_until > 30:
                    continue
                next_events.append({
                    'id': event['id'], 'title': event['title'],
                    'starts_at': event['starts_at'],
                    'venue': event['venue'], 'city': event['city'],
                    'available': event['available'],
                    'days_until': int(days_until),
                    'ticket_lots': event['ticket_lots']
                })
            unfiled = db.execute('''
                SELECT COUNT(*) FROM tickets t
                WHERE t.quantity>t.sold_quantity
                AND NOT EXISTS (
                    SELECT 1 FROM attachments a WHERE a.ticket_id=t.id
                )
            ''').fetchone()[0]
            drafts = db.execute("SELECT COUNT(*) FROM listings WHERE status='draft'").fetchone()[0]
            all_events = db.execute("SELECT COUNT(*) FROM events WHERE archived=0").fetchone()[0]
            all_tickets = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]

        alerts = []
        if next_events:
            soon = [event for event in next_events if event['days_until'] <= 7]
            if soon:
                alerts.append({
                    'kind': 'upcoming', 'severity': 'attention',
                    'title': str(len(soon)) + ' event(s) in the next 7 days',
                    'description': 'Review your upcoming event dates and delivery requirements.',
                    'page': 'events', 'count': len(soon)
                })
        if unfiled:
            alerts.append({
                'kind': 'pdf', 'severity': 'info',
                'title': str(unfiled) + ' ticket lot(s) without PDF files',
                'description': 'Check whether these tickets need a PDF; some tickets use mobile transfer.',
                'page': 'tickets', 'count': unfiled
            })
        if drafts:
            alerts.append({
                'kind': 'drafts', 'severity': 'info',
                'title': str(drafts) + ' local draft listing(s)',
                'description': 'Review your local listing drafts. They are not automatically published.',
                'page': 'listings', 'count': drafts
            })
        if not all_events:
            alerts.append({
                'kind': 'welcome', 'severity': 'start',
                'title': 'Create your first event',
                'description': 'Build your private calendar to start managing tickets.',
                'page': 'events', 'count': 0
            })
        return {
            'days': days,
            'range_start': start,
            'metrics': window,
            'previous_metrics': previous,
            'total_events': all_events,
            'total_ticket_lots': all_tickets,
            'unfiled_lots': unfiled,
            'draft_listings': drafts,
            'upcoming': next_events[:6],
            'alerts': alerts[:6],
            'currency': 'EUR',
            'note': 'Window margin = EUR sales − EUR fees − purchase cost of sold tickets. Other currencies and event expenses are excluded from this window metric.'
        }

    @app.get('/api/v6/search')
    def v6_search(request: Request, q: str = Query(min_length=2, max_length=80)):
        _, path = user_db(request)
        q = q.strip()
        if len(q) < 2:
            return {'results': []}
        # Quote LIKE wildcards so user input is a literal search term.
        pattern = '%' + q.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        results = []
        with connection(path) as db:
            events = select(db, '''
                SELECT id,title,city,starts_at
                FROM events
                WHERE title LIKE ? ESCAPE '!' OR venue LIKE ? ESCAPE '!'
                      OR city LIKE ? ESCAPE '!'
                ORDER BY starts_at DESC LIMIT 6
            ''', (pattern, pattern, pattern))
            for event in events:
                results.append({
                    'kind':'event', 'id':event['id'], 'title':event['title'],
                    'detail':event['city'] + ' · ' + event['starts_at'][:10],
                    'page':'events', 'query':event['title']
                })
            tickets = select(db, '''
                SELECT t.id,t.section,t.seats,t.provider,e.title AS event_title
                FROM tickets t JOIN events e ON e.id=t.event_id
                WHERE e.title LIKE ? ESCAPE '!' OR t.section LIKE ? ESCAPE '!'
                      OR t.seats LIKE ? ESCAPE '!' OR t.provider LIKE ? ESCAPE '!'
                ORDER BY t.id DESC LIMIT 6
            ''', (pattern,pattern,pattern,pattern))
            for ticket in tickets:
                results.append({
                    'kind':'ticket', 'id':ticket['id'],
                    'title':ticket['event_title'],
                    'detail':'Lot #' + str(ticket['id']) + ' · ' + (ticket['section'] or 'General admission'),
                    'page':'tickets', 'query':ticket['event_title']
                })
            listings = select(db, '''
                SELECT l.id,l.marketplace,l.status,e.title AS event_title
                FROM listings l JOIN tickets t ON t.id=l.ticket_id
                JOIN events e ON e.id=t.event_id
                WHERE e.title LIKE ? ESCAPE '!' OR l.marketplace LIKE ? ESCAPE '!'
                ORDER BY l.id DESC LIMIT 5
            ''', (pattern,pattern))
            for listing in listings:
                results.append({
                    'kind':'listing','id':listing['id'], 'title':listing['event_title'],
                    'detail':listing['marketplace'] + ' · ' + listing['status'],
                    'page':'listings','query':listing['event_title']
                })
        return {'results':results[:16]}
