/* Ceyrl Studio V3: an actual overview layout, not recolored legacy markup.
   All cards use authenticated account APIs and existing action handlers. */
'use strict';
(function installCeyrlStudioDashboard() {
  const safe = value => escapeHtml(value == null ? '' : value);
  const fmt = value => num(Number(value) || 0);
  const btn = (text, action, variant) =>
    '<button type="button" class="studio3-btn ' + (variant || '') + '" data-action="' +
    safe(action) + '">' + safe(text) + '</button>';
  const nav = (text, page, variant) =>
    '<button type="button" class="studio3-btn ' + (variant || '') + '" data-v6-go="' +
    safe(page) + '">' + safe(text) + '</button>';
  const cash = (value, currency) => money(value || 0, currency || 'EUR');
  const metric = (label, value, note, icon, tone) =>
    '<article class="studio3-stat studio3-' + tone + '"><div class="studio3-stat-top">' +
    '<span>' + safe(label) + '</span><span class="studio3-stat-icon" aria-hidden="true">' +
    safe(icon) + '</span></div><strong>' + safe(value) + '</strong>' +
    '<small>' + safe(note) + '</small></article>';
  const sectionHead = (eyebrow, title, sub, extra) =>
    '<div class="studio3-section-title"><div><span class="studio3-kicker">' + safe(eyebrow) +
    '</span><h2>' + safe(title) + '</h2>' + (sub ? '<p>' + safe(sub) + '</p>' : '') +
    '</div>' + (extra || '') + '</div>';
  const eventRows = rows => rows.length
    ? rows.map(event =>
      '<div class="studio3-event-row"><span class="studio3-event-date">' +
      '<b>' + safe(niceDate(event.starts_at).slice(0,2)) + '</b>' +
      '<small>' + safe(niceDate(event.starts_at).slice(3,6)) + '</small></span>' +
      '<span class="studio3-event-info"><strong>' + safe(event.title) + '</strong>' +
      '<small>' + safe([event.venue,event.city].filter(Boolean).join(' · ') || 'Location not provided') + '</small></span>' +
      '<span class="studio3-event-count">' + fmt(event.available) + ' seats</span></div>'
    ).join('')
    : '<div class="studio3-empty"><strong>No upcoming events</strong>' +
      '<p>Once you add an event, its schedule appears here automatically.</p>' +
      btn('Add an event', 'new-event', 'studio3-quiet') + '</div>';
  const saleRows = rows => rows.length
    ? rows.slice(0,4).map(sale =>
      '<div class="studio3-sale-row"><span class="studio3-sale-icon" aria-hidden="true">↗</span>' +
      '<span class="studio3-sale-info"><strong>' + safe(sale.event_title) + '</strong>' +
      '<small>' + safe(niceDate(sale.sold_at)) + ' · ' + fmt(sale.quantity) + ' ticket(s)</small></span>' +
      '<b>' + safe(cash(sale.revenue_cents,sale.currency)) + '</b></div>'
    ).join('')
    : '<div class="studio3-empty"><strong>No sales recorded</strong><p>Your recorded transactions will appear here.</p>' +
      btn('Record your first sale', 'new-sale', 'studio3-quiet') + '</div>';

  renderOverview = async function renderStudio3Overview() {
    const root = document.getElementById('page-content');
    root.innerHTML = '<div class="studio3-loading" role="status"><span class="studio3-spinner"></span>Loading your overview…</div>';
    let data, events;
    try {
      [data, events] = await Promise.all([api('/dashboard'), api('/events')]);
    } catch (error) {
      if (app.page !== 'overview') return;
      root.innerHTML = '<div class="studio3-load-error" role="alert"><h2>Could not load the overview</h2>' +
        '<p>' + safe(error.message || 'Your data is temporarily unavailable.') + '</p>' +
        '<button type="button" class="studio3-btn" data-studio3-retry>Try again</button></div>';
      return;
    }
    if (app.page !== 'overview') return;
    app.dashboard = data;
    app.events = Array.isArray(events) ? events : [];
    const now = Date.now();
    const upcoming = app.events.filter(e => {
      const d = new Date(e.starts_at).getTime();
      return Number.isFinite(d) && d > now;
    }).sort((a,b) => new Date(a.starts_at) - new Date(b.starts_at)).slice(0,5);
    const next = upcoming[0];
    const firstName = String(app.user.display_name || app.user.email || 'there').trim().split(/\s+/)[0];
    const dateLabel = new Intl.DateTimeFormat('en-GB', {day:'numeric', month:'long', year:'numeric'}).format(new Date());
    const quickActions =
      '<div class="studio3-actions-list">' +
        '<button type="button" data-action="new-event"><span class="studio3-action-icon">▤</span><span><strong>Create event</strong><small>Keep your dates organised</small></span><b>↗</b></button>' +
        '<button type="button" data-action="new-ticket"><span class="studio3-action-icon">▧</span><span><strong>Add tickets</strong><small>Inventory and encrypted PDFs</small></span><b>↗</b></button>' +
        '<button type="button" data-action="new-sale"><span class="studio3-action-icon">↗</span><span><strong>Record a sale</strong><small>Update quantities and income</small></span><b>↗</b></button>' +
        '<button type="button" data-v6-go="radar"><span class="studio3-action-icon">⌾</span><span><strong>Discover events</strong><small>Search connected live sources</small></span><b>↗</b></button>' +
      '</div>';
    root.innerHTML =
      '<div class="studio3-overview">' +
        '<div class="studio3-toolbar"><div><span class="studio3-kicker">MY PRIVATE WORKSPACE</span>' +
        '<h1>Overview<span class="studio3-heading-dot">.</span></h1>' +
        '<p>Your tickets, events and sales in one place.</p></div>' +
        '<div class="studio3-toolbar-end"><span class="studio3-today">' + safe(dateLabel) + '</span>' +
        nav('View analytics ↗','analytics','studio3-quiet') + '</div></div>' +
        '<div class="studio3-hero-grid"><section class="studio3-hero-primary">' +
          '<div class="studio3-hero-top"><span class="studio3-hero-brand">CEYRL STUDIO</span>' +
            '<span class="studio3-live"><i></i> Private workspace</span></div>' +
          '<div class="studio3-hero-copy"><span class="studio3-hero-welcome">WELCOME BACK, ' + safe(firstName.toUpperCase()) + '</span>' +
          '<h2>Everything in place.<br><em>Everything in view.</em></h2>' +
          '<p>Manage your next event, keep track of tickets and see how your sales are performing.</p>' +
          '<div class="studio3-hero-buttons">' + btn('+ Add tickets','new-ticket','studio3-light') +
          nav('Explore Event Radar ↗','radar','studio3-glass') + '</div></div>' +
        '</section><section class="studio3-next-card">' +
          '<div class="studio3-next-top"><span>UP NEXT</span><span aria-hidden="true">▤</span></div>' +
          (next ? '<div class="studio3-next-date">' + safe(niceDate(next.starts_at)) + '</div>' +
              '<h3>' + safe(next.title) + '</h3><p>' +
              safe([next.venue,next.city].filter(Boolean).join(' · ') || 'Location not provided') + '</p>' +
              '<div class="studio3-next-footer"><span>' + fmt(next.available) +
              ' tickets available</span>' + nav('View events ↗','events','studio3-quiet') + '</div>'
            : '<div class="studio3-next-placeholder"><h3>Your next event starts here.</h3>' +
              '<p>Create an event to build your private calendar.</p>' +
              btn('Create event ↗','new-event','studio3-quiet') + '</div>') +
        '</section></div>' +
        '<div class="studio3-stats">' +
          metric('Net profit',cash(data.profit_cents),'Realised · EUR','↗',data.profit_cents >= 0 ? 'green':'red') +
          metric('Sales revenue',cash(data.revenue_cents),'Recorded · EUR','€','purple') +
          metric('Available tickets',fmt(data.available),'Seats remaining','▧','blue') +
          metric('Tickets sold',fmt(data.sold),'Individual seats','◇','gold') +
        '</div>' +
        '<div class="studio3-workspace-grid"><section class="studio3-panel studio3-chart-panel">' +
          sectionHead('PERFORMANCE','Sales overview','Revenue recorded from your private transactions.',
            nav('All sales ↗','sales','studio3-text-button')) +
          '<div class="studio3-chart">' + chart(data.revenue_trend || []) + '</div>' +
          '<div class="studio3-chart-foot"><span><i></i> Actual sales revenue</span><span>EUR</span></div>' +
        '</section><section class="studio3-panel studio3-actions-panel">' +
          sectionHead('WORKSPACE','Quick actions','Pick up where you left off.') +
          quickActions + '</section></div>' +
        '<div class="studio3-workspace-grid studio3-bottom-grid">' +
          '<section class="studio3-panel studio3-upcoming-panel">' +
          sectionHead('CALENDAR','Upcoming events','Your next scheduled dates.',
            nav('View all ↗','events','studio3-text-button')) +
          eventRows(upcoming) + '</section>' +
          '<section class="studio3-panel studio3-sales-panel">' +
          sectionHead('ACTIVITY','Recent sales','Latest transactions.',
            nav('Sales tracker ↗','sales','studio3-text-button')) +
          saleRows(Array.isArray(data.recent_sales) ? data.recent_sales : []) +
          '</section></div>' +
        '<div class="studio3-footnote"><span>Data shown is private to your Ceyrl account.</span>' +
        '<span>Event search results depend on connected providers.</span></div>' +
      '</div>';
  };
  document.getElementById('page-content')?.addEventListener('click', event => {
    if (event.target.closest('[data-studio3-retry]')) {
      renderOverview().catch(notifyError);
    }
  });
})();
