/* Ceyrl V6 – operational dashboard, period insights and private command search.
 * Requires static/app.js and existing authenticated API; no external dependencies.
 */
'use strict';

let ceyrlPeriod = 30;
let ceyrlSearchActive = false;
let ceyrlSearchSequence = 0;
let ceyrlSearchTimer = null;

const v6Money = (n) => money(n || 0, 'EUR');
const v6Number = (n) => num(n || 0);
const v6Safe = (s) => escapeHtml(s ?? '');
const v6Day = (n) => String(Math.max(0, Math.round(n))) + 'd';

function v6Comparison(current, previous, suffix = '') {
  if (!previous) return current > 0 ? 'New activity in this period' : 'No prior-period activity';
  const delta = (current - previous) / Math.abs(previous) * 100;
  const trend = delta >= 0 ? '↗' : '↘';
  return trend + ' ' + (delta >= 0 ? '+' : '') + delta.toFixed(1) + '%' + suffix + ' vs previous period';
}

function v6PeriodSelector() {
  return '<div class="v6-periods" role="group" aria-label="Sales period">' +
    [7, 30, 90].map(d =>
      '<button type="button" class="v6-period ' + (d === ceyrlPeriod ? 'selected' : '') +
      '" data-v6-days="' + d + '" aria-pressed="' + String(d === ceyrlPeriod) + '">' + d + ' days</button>'
    ).join('') + '</div>';
}

function v6QuickActions() {
  const actions = [
    {name:'Add event',glyph:'▤',action:'new-event'},
    {name:'Add tickets',glyph:'▧',action:'new-ticket'},
    {name:'Record a sale',glyph:'↗',action:'new-sale'},
    {name:'Open vault',glyph:'◈',page:'tickets'}
  ];
  return '<div class="v6-quick-actions">' + actions.map(x =>
    '<button class="v6-quick" type="button" ' +
      (x.page ? 'data-v6-go="' + x.page + '"' : 'data-action="' + x.action + '"') + '>' +
      '<span aria-hidden="true">' + x.glyph + '</span><b>' + x.name + '</b><em>↗</em></button>'
  ).join('') + '</div>';
}

function v6Metrics(data) {
  const m = data.metrics || {};
  const p = data.previous_metrics || {};
  return [
    {label:'Revenue',value:v6Money(m.revenue_cents),icon:'€',trend:v6Comparison(m.revenue_cents,p.revenue_cents),tone:'violet'},
    {label:'Sales margin',value:v6Money(m.margin_cents),icon:'↗',trend:'Before event expenses · EUR only',tone:(m.margin_cents||0)<0?'danger':'green'},
    {label:'Tickets sold',value:v6Number(m.tickets),icon:'▧',trend:v6Comparison(m.tickets,p.tickets),tone:'blue'},
    {label:'Transactions',value:v6Number(m.transactions),icon:'◇',trend:v6Comparison(m.transactions,p.transactions),tone:'amber'}
  ].map(x => '<div class="v6-metric ' + x.tone + '">' +
    '<div class="v6-metric-top"><span>' + x.label + '</span><i>' + x.icon + '</i></div>' +
    '<strong>' + x.value + '</strong><small>' + x.trend + '</small></div>').join('');
}

function v6Alerts(data, compact = false) {
  const alerts = data.alerts || [];
  if (!alerts.length) {
    return '<div class="v6-all-clear"><span>✓</span><div><strong>Your workspace is up to date</strong><small>No immediate reminders from your recorded data.</small></div></div>';
  }
  const list = compact ? alerts.slice(0, 2) : alerts;
  return '<div class="v6-alert-list">' + list.map(a =>
    '<button class="v6-alert" type="button" data-v6-go="' + v6Safe(a.page) + '">' +
    '<span class="v6-alert-icon ' + v6Safe(a.severity) + '">' +
      (a.kind === 'upcoming' ? '▤' : a.kind === 'pdf' ? '▧' : a.kind === 'drafts' ? '◇' : '✦') +
    '</span><span class="v6-alert-content"><b>' + v6Safe(a.title) +
    '</b><small>' + v6Safe(a.description) + '</small></span><span class="v6-alert-arrow">↗</span></button>'
  ).join('') + '</div>';
}

function v6Upcoming(data) {
  const events = data.upcoming || [];
  if (!events.length) {
    return '<div class="v6-empty-next">No events in the next 30 days. ' +
      '<button type="button" data-action="new-event">Create an event ↗</button></div>';
  }
  return '<div class="v6-upcoming-list">' + events.map(e =>
    '<button class="v6-upcoming-event" type="button" data-v6-go="events">' +
    '<span class="v6-countdown">' + v6Day(e.days_until) + '</span>' +
    '<span class="v6-upcoming-label"><strong>' + v6Safe(e.title) + '</strong>' +
    '<small>' + v6Safe(e.city || e.venue || 'Location not specified') +
    ' · ' + v6Safe(niceDate(e.starts_at)) + '</small></span>' +
    '<span class="v6-upcoming-seats">' + v6Number(e.available) + ' seats</span></button>'
  ).join('') + '</div>';
}

async function decorateV6Overview() {
  const root = $('#page-content');
  const hero = root?.querySelector('.hero-panel');
  if (!hero || app.page !== 'overview') return;
  try {
    const data = await api('/v6/insights?days=30');
    if (app.page !== 'overview' || !root.contains(hero)) return;
    hero.insertAdjacentHTML('afterend',
      '<div class="v6-overview-tools">' +
        '<div class="v6-overview-title"><span class="v6-live-pulse"></span><div><b>YOUR ACTION CENTER</b>' +
        '<small>Live from your private ticket database</small></div></div>' +
        '<button type="button" data-v6-go="actions" class="v6-all-actions">Open Action Center ↗</button>' +
      '</div>' +
      '<div class="v6-overview-alerts">' + v6Alerts(data, true) + '</div>' +
      v6QuickActions()
    );
  } catch (error) {
    // The rest of the dashboard must remain usable even if insights fail.
    console.warn('Ceyrl Action Center temporarily unavailable', error);
  }
}

async function renderV6Actions() {
  $('#page-content').innerHTML = heading('Action Center',
    'Your upcoming events, ticket tasks and financial pulse — all private to your account.',
    button('Create event','new-event') + button('Record sale','new-sale','outline')) +
    '<div class="v6-loading">Reading your private workspace…</div>';
  let data;
  try {
    data = await api('/v6/insights?days=' + ceyrlPeriod);
  } catch (error) {
    $('#page-content').insertAdjacentHTML('beforeend',
      '<div class="v6-api-error">Insights could not load. Your event and ticket records are still available in the other sections.</div>');
    throw error;
  }
  if (app.page !== 'actions') return;
  $('#page-content').innerHTML =
    heading('Action Center', 'A private operations cockpit with reminders and live sales performance.',
      button('+ Add tickets','new-ticket') + button('+ Record sale','new-sale','outline')) +
    '<section class="v6-actions-hero"><div>' +
      '<span class="v6-kicker"><span class="v6-live-pulse"></span> CEYRL • OPERATIONS INTELLIGENCE</span>' +
      '<h2>Everything important.<br><em>One clear view.</em></h2>' +
      '<p>Prioritize upcoming events, check ticket documents and review local listing drafts.' +
      ' Every figure comes from your own records.</p></div>' +
      '<div class="v6-hero-orbit" aria-hidden="true"><span>◈</span><i>€</i></div></section>' +
    '<section class="v6-section-header"><div><h2>Sales performance</h2>' +
      '<p>EUR sales in your selected window, compared with the previous window</p></div>' +
      v6PeriodSelector() + '</section>' +
    '<div class="v6-metrics">' + v6Metrics(data) + '</div>' +
    '<div class="v6-panel-grid">' +
      '<section class="v6-panel"><div class="v6-panel-title"><div><h2>Needs your attention</h2>' +
      '<p>Based on your events, tickets and draft listings</p></div><span class="v6-panel-pill">' +
      v6Number(data.alerts.length) + ' items</span></div>' + v6Alerts(data) + '</section>' +
      '<section class="v6-panel"><div class="v6-panel-title"><div><h2>Next 30 days</h2>' +
      '<p>Upcoming dates in your private calendar</p></div>' +
      '<button class="v6-text-link" type="button" data-v6-go="events">All events ↗</button></div>' +
      v6Upcoming(data) + '</section>' +
    '</div>' +
    '<div class="v6-section-header"><div><h2>Quick actions</h2><p>Jump straight into your workflow</p></div></div>' +
    v6QuickActions() +
    '<p class="v6-calculation-note">ⓘ ' + v6Safe(data.note) +
    ' All-time realized profit, including event expenses, remains in Analytics.</p>';
}

function openCeyrlSearch() {
  if (!app.user) return;
  const dialog = $('#v6-search-dialog');
  const input = $('#v6-search-input');
  if (!dialog || !input) return;
  dialog.classList.remove('hidden');
  dialog.setAttribute('aria-hidden', 'false');
  ceyrlSearchActive = true;
  input.value = '';
  showV6SearchShortcuts();
  requestAnimationFrame(() => input.focus());
}

function closeCeyrlSearch() {
  const dialog = $('#v6-search-dialog');
  if (!dialog) return;
  dialog.classList.add('hidden');
  dialog.setAttribute('aria-hidden', 'true');
  ceyrlSearchActive = false;
  clearTimeout(ceyrlSearchTimer);
  ceyrlSearchSequence += 1;
}

function showV6SearchShortcuts() {
  const dest = $('#v6-search-results');
  if (!dest) return;
  dest.innerHTML =
    '<div class="v6-search-hint">QUICK NAVIGATION</div>' +
    [['overview','Overview','Dashboard and portfolio'],
     ['actions','Action Center','Alerts, event dates and sales pulse'],
     ['events','My Events','Manage your events'],
     ['tickets','Ticket Inventory','Search ticket lots and PDFs'],
     ['sales','Sales Tracker','Track your sales and revenue']].map(([page,title,sub]) =>
       '<button class="v6-result" type="button" data-v6-go="' + page + '">' +
       '<span class="v6-result-icon">⌕</span><span><b>' + title + '</b><small>' + sub +
       '</small></span><em>↗</em></button>').join('');
}

async function searchCeyrl(q) {
  const seq = ++ceyrlSearchSequence;
  const dest = $('#v6-search-results');
  if (!dest || !ceyrlSearchActive) return;
  if (q.trim().length < 2) {
    showV6SearchShortcuts();
    return;
  }
  dest.innerHTML = '<div class="v6-search-loading">Searching your private workspace…</div>';
  try {
    const data = await api('/v6/search?q=' + encodeURIComponent(q.trim()));
    if (seq !== ceyrlSearchSequence || !ceyrlSearchActive) return;
    if (!data.results.length) {
      dest.innerHTML = '<div class="v6-search-loading">No matching events, tickets or listings.</div>';
      return;
    }
    dest.innerHTML = '<div class="v6-search-hint">' + data.results.length + ' MATCHES</div>' +
      data.results.map(result =>
        '<button type="button" class="v6-result" data-v6-go="' + v6Safe(result.page) +
        '" data-v6-query="' + v6Safe(result.query || '') + '">' +
        '<span class="v6-result-icon">' + (result.kind === 'event' ? '▤' : result.kind === 'ticket' ? '▧' : '◇') + '</span>' +
        '<span><b>' + v6Safe(result.title) + '</b><small>' + v6Safe(result.kind.toUpperCase() +
          ' · ' + result.detail) + '</small></span><em>↗</em></button>'
      ).join('');
  } catch (_) {
    if (seq === ceyrlSearchSequence) {
      dest.innerHTML = '<div class="v6-search-loading">Search is temporarily unavailable.</div>';
    }
  }
}

function initCeyrlV6() {
  const searchInput = $('#v6-search-input');
  const searchRoot = $('#v6-search-dialog');
  if (!searchInput || !searchRoot) return;
  $('#v6-search-trigger')?.addEventListener('click', openCeyrlSearch);
  $('#v6-search-close')?.addEventListener('click', closeCeyrlSearch);
  searchRoot.addEventListener('click', event => {
    if (event.target === searchRoot) closeCeyrlSearch();
    const result = event.target.closest('[data-v6-go]');
    if (!result) return;
    const page = result.dataset.v6Go;
    if (!SECTIONS.some(section => section.items.some(item => item[0] === page))) return;
    if (page === 'tickets' && result.dataset.v6Query) app.search = result.dataset.v6Query;
    closeCeyrlSearch();
    navigate(page);
  });
  searchInput.addEventListener('input', () => {
    clearTimeout(ceyrlSearchTimer);
    const q = searchInput.value;
    ceyrlSearchTimer = setTimeout(() => searchCeyrl(q), 220);
  });
  searchInput.addEventListener('keydown', event => {
    const results = [...searchRoot.querySelectorAll('.v6-result')];
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!results.length) return;
      const index = results.findIndex(x => x.classList.contains('v6-active'));
      const next = (index + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
      results.forEach((x, i) => x.classList.toggle('v6-active', i === next));
      results[next].scrollIntoView({block: 'nearest'});
    }
    if (event.key === 'Enter' && results.length) {
      event.preventDefault();
      (results.find(x => x.classList.contains('v6-active')) || results[0]).click();
    }
    if (event.key === 'Escape') closeCeyrlSearch();
  });
  $('#page-content')?.addEventListener('click', event => {
    const dayButton = event.target.closest('[data-v6-days]');
    if (dayButton) {
      ceyrlPeriod = Number(dayButton.dataset.v6Days) || 30;
      renderV6Actions().catch(notifyError);
      return;
    }
    const goButton = event.target.closest('[data-v6-go]');
    if (goButton) navigate(goButton.dataset.v6Go);
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (ceyrlSearchActive) closeCeyrlSearch();
      else openCeyrlSearch();
    }
    if (ceyrlSearchActive && event.key === 'Escape') closeCeyrlSearch();
  });
  $('#global-search')?.addEventListener('focus', openCeyrlSearch);
}

initCeyrlV6();
