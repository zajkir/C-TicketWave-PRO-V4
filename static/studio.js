/* Ceyrl Studio — real interface enhancements, preserving existing APIs and records. */
'use strict';
(function initCeyrlStudio() {
  const page = document.getElementById('page-content');
  const branchSafe = (v) => escapeHtml(v == null ? '' : v);
  const savedPreference = (key, fallback) => {
    try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
  };
  const storePreference = (key, value) => {
    try { localStorage.setItem(key, value); } catch (_) { /* preferences are optional */ }
  };
  document.body.classList.toggle('studio-density-compact', savedPreference('ceyrl-studio-density', 'comfortable') === 'compact');

  function studioLinks(q) {
    const encoded = encodeURIComponent(q || '');
    if (!encoded) return '';
    return '<section class="studio-radar-links" aria-label="Official external searches">' +
      '<a href="https://www.ticketmaster.com/search?q=' + encoded + '" rel="noopener noreferrer" target="_blank">Ticketmaster search ↗</a>' +
      '<a href="https://www.songkick.com/search?query=' + encoded + '" rel="noopener noreferrer" target="_blank">Songkick search ↗</a>' +
      '<a href="https://www.bandsintown.com/search?q=' + encoded + '" rel="noopener noreferrer" target="_blank">Bandsintown search ↗</a></section>';
  }

  // Display only actual provider data. Never generate placeholder tour dates,
  // availability or ticket prices that a provider did not confirm.
  xRadarResultsHtml = function studioEventCards(rows) {
    const safeRows = Array.isArray(rows) ? rows : [];
    return '<section class="x-panel x-radar-results studio-radar-results">' +
      '<div class="studio-radar-ribbon"><strong>Verified source listings</strong><small>' +
      safeRows.length + ' result' + (safeRows.length === 1 ? '' : 's') + ' returned</small></div>' +
      '<div class="x-radar-grid">' + safeRows.map(e => {
        const isSport = /sport|football|soccer|basketball|hockey/i.test(e.category || '');
        const icon = isSport ? '◈' : '♫';
        const location = [e.venue,e.city,e.country].filter(Boolean).join(' · ') || 'Venue not listed';
        return '<article class="x-event-result">' +
          '<div class="studio-event-cover" aria-hidden="true"><span>' + icon + '</span><div><strong>' +
          branchSafe(e.category || 'Live event') + '</strong><small>Official provider listing</small></div></div>' +
          '<div class="x-card-top"><span class="x-eyebrow">' + branchSafe(e.provider || xRadarSource) + '</span>' +
          xTag(e.category || 'Event') + '</div><h3>' + branchSafe(e.name) + '</h3>' +
          '<p>▤ ' + branchSafe(e.local_date || e.starts_at || 'Date not confirmed') + '</p>' +
          '<p>⌖ ' + branchSafe(location) + '</p>' +
          '<div class="x-result-actions">' +
          '<button class="btn primary" type="button" data-x-import="' + branchSafe(e.id) + '"' +
          (!e.starts_at ? ' disabled title="Provider has not confirmed an exact event time"' : '') +
          '>Add to my events</button>' +
          (e.url ? '<a href="' + branchSafe(e.url) + '" rel="noopener noreferrer" target="_blank">Official listing ↗</a>' : '') +
          '</div></article>';
      }).join('') + '</div></section>';
  };

  renderXRadar = async function studioRadarPage() {
    if (!page) return;
    page.innerHTML = heading('Event Radar', 'Discover concerts, sports and live events from connected sources.') +
      '<div class="studio-radar-empty" role="status">Loading Event Radar…</div>';
    const settled = await Promise.allSettled([api('/x/radar/status'), api('/x/radar/watches')]);
    if (app.page !== 'radar') return;
    const status = settled[0].status === 'fulfilled' ? settled[0].value : {global_concerts_enabled:false,provider:'Source status unavailable',coverage_note:'Source status is currently unavailable.'};
    const watchState = settled[1].status === 'fulfilled' ? settled[1].value : {watches:[],hits:[]};
    const watches = Array.isArray(watchState.watches) ? watchState.watches : [];
    const hits = Array.isArray(watchState.hits) ? watchState.hits : [];
    const configured = !!status.global_concerts_enabled;
    const countries = [['','All countries'],['SK','Slovakia'],['CZ','Czechia'],['DE','Germany'],['AT','Austria'],['PL','Poland'],
      ['GB','United Kingdom'],['US','United States'],['FR','France'],['IT','Italy'],['ES','Spain'],['NL','Netherlands']];
    page.innerHTML = heading('Event Radar', 'Search real event listings, save your searches and add confirmed dates to your calendar.') +
      '<section class="studio-radar-intro"><div><span class="x-eyebrow">CEYRL · EVENT DISCOVERY</span>' +
      '<h2>Find the events worth going to.</h2>' +
      '<p>Artists, festivals, sports and venues in one focused workspace. Search is free to use; no personal API key needed.</p></div>' +
      '<span class="studio-radar-state"><i class="studio-status-dot ' + (configured ? 'ready' : '') + '"></i>' +
      (configured ? 'Global concert source configured' : 'Limited public coverage') + '</span></section>' +
      '<section class="studio-radar-search"><p class="studio-radar-searchlabel">What are you looking for?</p>' +
      '<form class="x-radar-form" id="x-radar-form">' +
      '<input id="x-radar-query" name="query" type="search" minlength="2" maxlength="80" required autocomplete="off"' +
      ' placeholder="Search artist, team, festival or venue…" value="' + branchSafe(xRadarQuery) + '">' +
      '<select id="x-radar-kind" name="kind" aria-label="Category">' +
      [['all','All categories'],['music','Music & festivals'],['sports','Sports']].map(item =>
        '<option value="' + item[0] + '"' + (item[0] === xRadarKind ? ' selected' : '') + '>' + item[1] + '</option>').join('') +
      '</select><select id="x-radar-country" name="country" aria-label="Country">' +
      countries.map(item => '<option value="' + item[0] + '"' + (item[0] === xRadarCountry ? ' selected' : '') +
        '>' + item[1] + '</option>').join('') +
      '</select><button class="btn primary" type="submit" id="studio-radar-submit">Search events ↗</button></form>' +
      '<div class="studio-search-footnote">' +
      branchSafe(status.coverage_note || 'Provider coverage may be incomplete.') +
      ' Results come from connected sources, not from fabricated event listings.</div></section>' +
      '<section class="x-radar-artists"><div class="x-radar-artists-header"><strong>Popular artist shortcuts</strong>' +
      '<small>Tap an artist to search real listings</small></div>' +
      '<div class="x-radar-artist-chips">' + xRadarPopularArtists.map(a =>
        '<button type="button" class="x-radar-artist-chip" data-x-artist="' + branchSafe(a) + '">' +
        branchSafe(a) + '</button>').join('') + '</div></section>' +
      '<div class="studio-radar-columns"><div>' +
      '<div class="x-search-actions"><button type="button" class="btn outline" data-x-action="radar-follow">+ Save this search</button>' +
      '<button type="button" class="btn outline" data-x-action="radar-refresh">Refresh saved searches</button></div>' +
      '<div id="x-radar-results" aria-live="polite">' +
      (xRadarEvents.length ? xRadarResultsHtml(xRadarEvents) :
        '<div class="studio-radar-empty"><strong>Start discovering events</strong>' +
        '<p>Search above or choose a popular artist. Dates and ticket offers are shown only when a source returns them.</p></div>') +
      '</div></div><aside class="studio-radar-side" aria-label="My radar activity">' +
      xPane('Saved searches', 'Private to your account · up to 15', watches.length ?
        watches.map(w => '<div class="x-watch-row"><div><b>' + branchSafe(w.query) + '</b><small>' +
          branchSafe(w.country || 'Worldwide') + ' · Last checked: ' +
          branchSafe(w.last_checked ? niceDate(w.last_checked) : 'Not yet') + '</small></div>' +
          '<button type="button" class="mini-btn" data-x-remove-watch="' + Number(w.id) + '">Remove</button></div>').join('') :
        '<p class="x-description">No saved searches yet. Search for an artist or event, then save it.</p>') +
      xPane('Latest updates', 'Changes detected when you refresh', hits.length ?
        hits.slice(0,10).map(h => '<div class="x-watch-row"><div><b>' + branchSafe(h.name) +
          '</b><small>' + branchSafe(h.city || 'Location unknown') + ' · ' +
          branchSafe(h.starts_at || 'Date unconfirmed') + '</small></div></div>').join('') :
        '<p class="x-description">No changes detected yet.</p>') +
      xPane('Source availability', 'Operator-managed integrations', '<p class="x-description">' +
        branchSafe(status.provider || 'Provider status unavailable') + '</p>' +
        '<p class="x-description">Live source availability is checked during searches. The operator enables the shared Ticketmaster key; users never enter credentials.</p>') +
      '</aside></div>';
  };

  let radarRequestSerial = 0;
  xRadarSearch = async function studioRadarSearch() {
    const query = document.getElementById('x-radar-query')?.value.trim() || '';
    const country = document.getElementById('x-radar-country')?.value || '';
    const kind = document.getElementById('x-radar-kind')?.value || 'all';
    if (query.length < 2) return notify('Enter at least two characters to search.', true);
    xRadarQuery = query; xRadarCountry = country; xRadarKind = kind;
    const serial = ++radarRequestSerial;
    const resultPanel = document.getElementById('x-radar-results');
    const submit = document.getElementById('studio-radar-submit');
    if (!resultPanel) return;
    if (submit) { submit.disabled = true; submit.textContent = 'Searching…'; }
    resultPanel.innerHTML = '<div class="studio-radar-empty" role="status"><strong>Checking event sources…</strong><p>Results will appear here when a provider responds.</p></div>';
    try {
      const data = await api('/x/radar/search?q=' + encodeURIComponent(query) + '&country=' + encodeURIComponent(country) + '&kind=' + encodeURIComponent(kind));
      if (serial !== radarRequestSerial || app.page !== 'radar') return;
      xRadarEvents = Array.isArray(data.events) ? data.events : [];
      xRadarSource = data.source || 'Connected sources';
      xRadarCoverage = data.coverage_note || '';
      const checked = Array.isArray(data.sources_checked) ? data.sources_checked : [];
      const warnings = Array.isArray(data.provider_warnings) ? data.provider_warnings : [];
      const status = '<div class="studio-radar-ribbon"><strong>' + xRadarEvents.length +
        ' matching event' + (xRadarEvents.length === 1 ? '' : 's') + '</strong><small>Sources checked: ' +
        branchSafe(checked.join(', ') || xRadarSource) + '</small></div>';
      const warning = warnings.length ? '<p class="x-radar-provider-note" role="status">' +
        branchSafe(warnings.join(' ')) + '</p>' : '';
      const empty = '<div class="studio-radar-empty"><strong>No verified events returned</strong>' +
        '<p>Coverage may be limited, or the event has not been published by a connected source. ' +
        'Try another country or browse the official provider searches below.</p></div>';
      const panel = document.getElementById('x-radar-results');
      if (panel) panel.innerHTML = status + warning + (xRadarEvents.length ?
        xRadarResultsHtml(xRadarEvents) : empty) + studioLinks(query);
    } catch (err) {
      if (serial !== radarRequestSerial || app.page !== 'radar') return;
      const panel = document.getElementById('x-radar-results');
      if (panel) panel.innerHTML = '<div class="x-api-error" role="alert"><strong>Search source temporarily unavailable.</strong><p>' +
        branchSafe(err.message || 'Please try again shortly.') +
        '</p><p>Use official searches below, or try a different search later.</p></div>' +
        studioLinks(query);
    } finally {
      if (serial === radarRequestSerial && app.page === 'radar' && submit) {
        submit.disabled = false; submit.textContent = 'Search events ↗';
      }
    }
  };

  async function renderStudioSettings() {
    const root = document.getElementById('page-content');
    root.innerHTML = heading('My Account', 'Your identity, security and preferences in one place.') +
      '<div class="studio-radar-empty" role="status">Loading your account settings…</div>';
    const [profileResult, sessionResult] = await Promise.allSettled([api('/me'),api('/me/sessions')]);
    if (app.page !== 'settings') return;
    if (profileResult.status !== 'fulfilled') {
      root.innerHTML = heading('My Account', 'Account settings could not be loaded.') +
        '<div class="x-api-error" role="alert">' + branchSafe(profileResult.reason.message) +
        '</div><button type="button" class="btn outline" data-studio-action="reload-settings">Try again</button>';
      return;
    }
    const me = profileResult.value;
    const sessions = sessionResult.status === 'fulfilled' ? sessionResult.value : null;
    const initial = (me.name || me.email || 'C').trim()[0].toUpperCase();
    const compact = document.body.classList.contains('studio-density-compact');
    const motion = document.getElementById('motion-toggle');
    const motionOn = motion && motion.getAttribute('aria-pressed') === 'true';
    const count = me.counts || {};
    root.innerHTML = heading('My Account', 'Manage your profile, sign-in security, connected services and workspace.') +
      '<section class="studio-account-header"><div class="studio-account-ident">' +
      '<div class="studio-avatar" aria-hidden="true">' + branchSafe(initial) + '</div><div>' +
      '<span class="studio-account-label">PERSONAL CEYRL ACCOUNT</span><h2>' + branchSafe(me.name) + '</h2>' +
      '<p>' + branchSafe(me.email) + '</p></div></div>' +
      '<button type="button" class="btn primary" data-action="edit-profile">Edit profile ↗</button></section>' +
      '<div class="studio-account-grid">' +
      '<section class="studio-settings-panel"><h3>Profile & account</h3>' +
      '<p>Your workspace is independent from other Ceyrl users.</p>' +
      '<div class="secure-row"><div><strong>Display name</strong><small>' + branchSafe(me.name) + '</small></div>' +
      '<button type="button" class="mini-btn" data-action="edit-profile">Change</button></div>' +
      '<div class="secure-row"><div><strong>Email address</strong><small>' + branchSafe(me.email) + '</small></div>' +
      '<span class="studio-setting-status">Verified account</span></div>' +
      '<div class="secure-row"><div><strong>Google sign-in</strong><small>' +
      (me.has_google ? 'Connected to this account' : 'Not connected') + '</small></div>' +
      (me.has_google ? '<span class="studio-setting-status">Linked</span>' :
        app.google ? '<button class="mini-btn" type="button" data-action="connect-google">Connect</button>' :
          '<span class="studio-setting-status neutral">Not configured</span>') + '</div>' +
      '<div class="studio-setting-actions"><button class="btn outline" type="button" data-action="sign-out">Sign out</button></div></section>' +
      '<section class="studio-settings-panel"><h3>Security & sessions</h3>' +
      '<p>Review real account security controls; no simulated two-factor toggles.</p>' +
      '<div class="secure-row"><div><strong>Password</strong><small>' +
      (me.has_password ? 'Password sign-in is enabled' : 'Signed in via connected account') +
      '</small></div><button type="button" class="mini-btn" data-action="change-password">' +
      (me.has_password ? 'Change password' : 'Set password') + '</button></div>' +
      '<div class="secure-row"><div><strong>Signed-in sessions</strong><small>' +
      (sessions ? (Number(sessions.active || 0) + ' active session(s); current session expires ' +
        branchSafe(sessions.current_expires_at ? niceDate(sessions.current_expires_at) : 'soon')) :
        'Session details unavailable right now') + '</small></div>' +
      (sessions ? '<span class="studio-setting-status neutral">' + Number(sessions.active || 0) + ' active</span>' : '') +
      '</div><div class="studio-setting-actions"><button type="button" class="btn outline" data-studio-action="revoke-sessions"' +
      (!sessions || !sessions.other ? ' disabled' : '') + '>Sign out other sessions</button></div></section>' +
      '<section class="studio-settings-panel"><h3>My private inventory</h3>' +
      '<p>All figures below come from your account database.</p>' +
      [['Events',count.events],['Ticket lots',count.tickets],['Encrypted PDF documents',count.attachments],['Sales records',count.sales]].map(item =>
        '<div class="secure-row"><div><strong>' + item[0] + '</strong></div><b>' +
          Number(item[1] || 0).toLocaleString('en-GB') + '</b></div>').join('') +
      '<div class="studio-setting-actions">' +
      '<button type="button" class="btn outline" data-action="export-events">Export events</button>' +
      '<button type="button" class="btn outline" data-action="export-tickets">Export tickets</button>' +
      '<button type="button" class="btn outline" data-action="export-sales">Export sales</button></div></section>' +
      '<section class="studio-settings-panel"><h3>Appearance & accessibility</h3>' +
      '<p>Customize Ceyrl on this device. Preferences do not change your account data.</p>' +
      '<div class="studio-preference-row"><div><strong>Compact layout</strong><small>Show denser tables and panels.</small></div>' +
      '<button type="button" class="studio-toggle" data-studio-action="density" aria-pressed="' +
      compact + '">' + (compact ? 'On' : 'Off') + '</button></div>' +
      '<div class="studio-preference-row"><div><strong>Ambient motion</strong>' +
      '<small>Keep decorative movement on or off. System accessibility settings take priority.</small></div>' +
      '<button type="button" class="studio-toggle" data-studio-action="motion" aria-pressed="' +
      !!motionOn + '"' + (motion?.disabled ? ' disabled' : '') + '>' +
      (motionOn ? 'On' : 'Off') + '</button></div>' +
      '<div class="studio-preference-row"><div><strong>Theme</strong><small>Ceyrl Studio dark theme</small></div>' +
      '<span class="studio-setting-status neutral">Active</span></div></section></div>' +
      '<div class="section-note" style="margin-top:22px">Ceyrl keeps user records in separate databases and encrypted PDF vaults. ' +
      'Always protect account recovery email and use a unique password. A two-factor feature is not enabled in this version.</div>';
  }
  renderSettings = renderStudioSettings;

  page?.addEventListener('click', async function onStudioClick(event) {
    const button = event.target.closest('[data-studio-action]');
    if (!button) return;
    const action = button.dataset.studioAction;
    if (action === 'reload-settings') return renderStudioSettings();
    if (action === 'density') {
      const next = !document.body.classList.contains('studio-density-compact');
      document.body.classList.toggle('studio-density-compact', next);
      storePreference('ceyrl-studio-density', next ? 'compact' : 'comfortable');
      button.setAttribute('aria-pressed', String(next));
      button.textContent = next ? 'On' : 'Off';
      return;
    }
    if (action === 'motion') {
      document.getElementById('motion-toggle')?.click();
      const next = document.getElementById('motion-toggle')?.getAttribute('aria-pressed') === 'true';
      button.setAttribute('aria-pressed', String(next));
      button.textContent = next ? 'On' : 'Off';
      return;
    }
    if (action === 'revoke-sessions') {
      if (!confirm('Sign out all other sessions? This device will stay signed in.')) return;
      button.disabled = true;
      try {
        const result = await api('/me/sessions/revoke-others', {method:'POST'});
        notify(String(result.revoked || 0) + ' other session(s) signed out.');
        await renderStudioSettings();
      } catch (error) {
        notifyError(error);
        button.disabled = false;
      }
    }
  });
})();
