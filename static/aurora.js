/* Ceyrl Aurora — reference-led Event Radar without invented availability. */
'use strict';
(function applyCeyrlAurora(){
  const root = document.getElementById('page-content');
  const esc = value => escapeHtml(value == null ? '' : value);
  const eventKinds = [['all','Všetky kategórie'],['music','Koncerty a festivaly'],['sports','Šport']];
  const countries = [['','Všetky krajiny'],['SK','Slovensko'],['CZ','Česko'],['DE','Nemecko'],['AT','Rakúsko'],
    ['PL','Poľsko'],['GB','Veľká Británia'],['US','USA'],['IE','Írsko'],['FR','Francúzsko'],
    ['IT','Taliansko'],['ES','Španielsko'],['NL','Holandsko'],['BE','Belgicko'],['CH','Švajčiarsko'],['HU','Maďarsko'],['CA','Kanada'],['AU','Austrália']];
  const tips = ['Noah Kahan','BTS','Nickelback','Coldplay','Post Malone','Calin','KATSEYE','Tame Impala','RAYE','Sam Fender'];
  const dateValue = value => {
    const date = Date.parse(String(value||''));
    return Number.isFinite(date) ? date : null;
  };
  const state = {from:'',to:'',sort:'date',view:'grid'};
  const trustedImage = value => typeof value==='string' &&
    /^https:\/\/(?:s1\.ticketm\.net|images1\.ticketmaster\.com|images\.ticketmaster\.com)\//i.test(value) ? value : '';
  const trustedListing = value => {
    if (typeof value !== 'string') return '';
    try {
      const u = new URL(value);
      if (u.protocol !== 'https:' || u.username || u.password) return '';
      if (/^(?:www\.)?ticketfairy\.com$/i.test(u.hostname)) return value;
      if (/^(?:www\.)?ticketmaster\.(?:com|co\.uk|de|fr|es|it|nl|be|ch|ca|ie|cz|pl|at|hu|com\.au)$/i.test(u.hostname)) return value;
      if (u.hostname==='www.espn.com' || u.hostname==='www.thesportsdb.com') return value;
    } catch (_) {}
    return '';
  };
  const options = (values,current) => values.map(([id,label]) =>
    '<option value="'+esc(id)+'"'+(id===current?' selected':'')+'>'+esc(label)+'</option>').join('');
  const dateText = item => {
    const d = item.local_date || item.starts_at || '';
    if (!d) return 'Dátum nepotvrdený';
    const ms = dateValue(d);
    if (ms == null) return 'Dátum nepotvrdený';
    return new Intl.DateTimeFormat('sk-SK',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(ms);
  };
  const card = item => {
    const sport = /sport|football|soccer|hockey|basketball|baseball/i.test(item.category||'');
    const icon = sport ? '◈' : '♫';
    const cover = trustedImage(item.image_url);
    const category = String(item.category||'Podujatie');
    const location = [item.venue,item.city,item.country].filter(Boolean).join(' · ') || 'Miesto neuvedené';
    const illustration = cover
      ? '<img loading="lazy" decoding="async" referrerpolicy="no-referrer" src="'+esc(cover)+'" alt="">'
      : '<div class="ceyrl-event-art" aria-hidden="true"><span>'+icon+'</span></div>';
    const link = trustedListing(item.url);
    return '<article class="ceyrl-event-card">'+
      '<div class="ceyrl-event-image">'+illustration+
      '<span class="ceyrl-event-category">'+esc(category)+'</span></div>'+
      '<div class="ceyrl-event-body">'+
      '<span class="ceyrl-event-source">'+esc(item.provider||'Externý zdroj')+'</span>'+
      '<h3>'+esc(item.name||'Podujatie')+'</h3>'+
      '<p><span aria-hidden="true">⌖</span> '+esc(location)+'</p>'+
      '<p><span aria-hidden="true">▤</span> '+esc(dateText(item))+'</p>'+
      '<div class="ceyrl-event-card-actions">'+
      (link?'<a target="_blank" rel="noopener noreferrer" href="'+esc(link)+'" class="ceyrl-event-link">Zobraziť zdroj ↗</a>':'<span class="ceyrl-source-missing">Odkaz nie je dostupný</span>')+
      '<button type="button" class="btn primary" data-x-import="'+esc(item.id||'')+'"'+
      (!item.starts_at?' disabled title="Zdroj nepotvrdil presný čas"':'')+
      '>+ Moje podujatia</button></div></div></article>';
  };
  const filteredRows = rows => {
    let filtered = (Array.isArray(rows)?rows:[]).filter(e=>{
      const ts=dateValue(e.starts_at || e.local_date);
      if (state.from && (ts===null || ts < Date.parse(state.from+'T00:00:00Z'))) return false;
      if (state.to && (ts===null || ts > Date.parse(state.to+'T23:59:59Z'))) return false;
      return true;
    });
    if(state.sort==='name') filtered.sort((a,b)=>String(a.name||'').localeCompare(String(b.name||''),'sk'));
    else filtered.sort((a,b)=>{
      const da=dateValue(a.starts_at || a.local_date),db=dateValue(b.starts_at || b.local_date);
      return (da===null?Infinity:da)-(db===null?Infinity:db);
    });
    return filtered;
  };
  const cardsHtml = rows => {
    const filtered=filteredRows(rows);
    const view = state.view==='list'?'ceyrl-list-view':'';
    return '<section class="ceyrl-radar-results">'+
      '<div class="ceyrl-results-summary"><div><h2>Nájdené podujatia <span>('+filtered.length+')</span></h2>'+
      '<small>Podujatia načítané zo skutočných katalógov. Ceny a dostupnosť overuj u organizátora.</small></div>'+
      '<div class="ceyrl-results-controls"><label for="ceyrl-results-sort">Zoradiť</label>'+
      '<select id="ceyrl-results-sort"><option value="date"'+(state.sort==='date'?' selected':'')+'>Najbližšie</option>'+
      '<option value="name"'+(state.sort==='name'?' selected':'')+'>Podľa názvu</option></select>'+
      '<button type="button" aria-label="Mriežka" title="Mriežka" data-aurora-view="grid" aria-pressed="'+(state.view==='grid')+'">▦</button>'+
      '<button type="button" aria-label="Zoznam" title="Zoznam" data-aurora-view="list" aria-pressed="'+(state.view==='list')+'">☷</button></div></div>'+
      (filtered.length?'<div class="ceyrl-event-grid '+view+'">'+filtered.map(card).join('')+'</div>':
        '<div class="ceyrl-radar-empty"><span>⌕</span><strong>Žiadne výsledky pre tieto filtre</strong><p>Skús iný dátum alebo vyhľadávací výraz. Neznamená to, že interpret nemá koncerty.</p></div>')+
      '</section>';
  };
  xRadarResultsHtml = cardsHtml;

  const sourceState=(status,failed)=> {
    const tm = status.global_concerts_enabled===true;
    return '<div class="ceyrl-source-list">'+
      '<div><span class="ceyrl-source-mark">T</span><span><strong>Ticketmaster</strong><small>'+
      (failed?'Stav neznámy':tm?'Kľúč na serveri nastavený':'Rozšírené vyhľadávanie nenastavené')+
      '</small></span><i class="'+(!failed&&tm?'ceyrl-ready':'')+'"></i></div>'+
      '<div><span class="ceyrl-source-mark ceyrl-tf">♫</span><span><strong>Ticket Fairy</strong><small>Verejný katalóg; overuje sa pri hľadaní</small></span><i></i></div>'+
      '<div><span class="ceyrl-source-mark ceyrl-sp">◈</span><span><strong>Športové zdroje</strong><small>Pokrytie podľa športu a súťaže</small></span><i></i></div></div>';
  };
  const watched=(watches,failed)=>failed?
    '<p class="ceyrl-panel-muted" role="alert">Uložené vyhľadávania sa nepodarilo načítať.</p>':
    watches.length?watches.slice(0,10).map(w=>
      '<div class="ceyrl-watch-row"><div><strong>'+esc(w.query)+'</strong><small>'+esc(w.country||'Celý svet')+'</small></div>'+
      '<button type="button" data-x-remove-watch="'+Number(w.id)+'" aria-label="Odstrániť sledovanie '+esc(w.query)+'">×</button></div>').join(''):
    '<p class="ceyrl-panel-muted">Zatiaľ nemáš uložené žiadne sledovania. Vyhľadaj interpreta a ulož hľadanie.</p>';
  const changes=(hits,failed)=>failed?'<p class="ceyrl-panel-muted">Aktualizácie momentálne nie sú dostupné.</p>':
    hits.length?hits.slice(0,6).map(h=>
      '<div class="ceyrl-watch-row"><div><strong>'+esc(h.name)+'</strong><small>'+
      esc(h.city||'Miesto nepotvrdené')+'</small></div></div>').join(''):
    '<p class="ceyrl-panel-muted">Žiadne nové zmeny. Aktualizujú sa po kontrole sledovaní.</p>';

  renderXRadar = async function renderAuroraRadar() {
    if (!root) return;
    root.innerHTML='<div class="studio-radar-empty" role="status">Načítavam Event Radar…</div>';
    const [sr,wr] = await Promise.allSettled([api('/x/radar/status'),api('/x/radar/watches')]);
    if (app.page!=='radar') return;
    const failed=sr.status!=='fulfilled';
    const status=failed?{global_concerts_enabled:false,coverage_note:'Stav zdrojov sa momentálne nedá overiť.'}:sr.value;
    const watchError=wr.status!=='fulfilled';
    const watch=watchError?{watches:[],hits:[]}:wr.value;
    const ws=Array.isArray(watch.watches)?watch.watches:[];
    const hits=Array.isArray(watch.hits)?watch.hits:[];
    const configured=!!status.global_concerts_enabled;
    root.innerHTML=
      '<main class="ceyrl-radar">'+
      '<div class="ceyrl-radar-primary">'+
      '<section class="ceyrl-radar-hero">'+
      '<div class="ceyrl-radar-hero-copy"><span class="ceyrl-hero-tag">⌾ Event Radar</span>'+
      '<h1>Objavuj koncerty, festivaly a live udalosti <em>po celom svete.</em></h1>'+
      '<p>Hľadaj interpretov, mestá, festivaly a športové podujatia. Výsledky pochádzajú z napojených zdrojov.</p></div></section>'+
      '<section class="ceyrl-radar-search"><form id="x-radar-form" class="ceyrl-search-form">'+
      '<label class="ceyrl-search-input" for="x-radar-query"><span aria-hidden="true">⌕</span>'+
      '<input id="x-radar-query" type="search" name="query" autocomplete="off" required minlength="2" maxlength="80" '+
      'placeholder="Vyhľadaj interpreta, festival alebo mesto…" value="'+esc(xRadarQuery)+'"></label>'+
      '<button type="submit" id="studio-radar-submit" class="btn primary">Vyhľadať ↗</button></form>'+
      '<div class="ceyrl-radar-shortcuts"><strong>Rýchle vyhľadávanie</strong>'+
      tips.map(t=>'<button type="button" data-x-artist="'+esc(t)+'">'+esc(t)+'</button>').join('')+'</div></section>'+
      '<section class="ceyrl-radar-filters" aria-label="Filtre vyhľadávania">'+
      '<label>Krajina<select id="x-radar-country">'+options(countries,xRadarCountry)+'</select></label>'+
      '<label>Kategória<select id="x-radar-kind">'+options(eventKinds,xRadarKind)+'</select></label>'+
      '<label>Dátum od<input id="ceyrl-date-from" type="date" value="'+esc(state.from)+'"></label>'+
      '<label>Dátum do<input id="ceyrl-date-to" type="date" value="'+esc(state.to)+'"></label>'+
      '<button type="button" class="ceyrl-reset-filters" data-aurora-reset>Vymazať filtre ×</button></section>'+
      '<div class="ceyrl-radar-actions"><button class="btn outline" type="button" data-x-action="radar-follow">♡ Uložiť hľadanie</button>'+
      '<button class="btn outline" type="button" data-x-action="radar-refresh">↻ Aktualizovať sledovania</button></div>'+
      '<div class="ceyrl-live-results" id="x-radar-results" aria-live="polite">'+
      (xRadarEvents.length?cardsHtml(xRadarEvents):
        '<div class="ceyrl-radar-empty"><span>♫</span><strong>Vyhľadaj svoje obľúbené podujatie</strong>'+
        '<p>Začni menom interpreta alebo klikni na rýchle vyhľadávanie. Nezobrazujeme vymyslené koncerty ani ceny.</p></div>')+
      '</div></div>'+
      '<aside class="ceyrl-radar-aside" aria-label="Prehľad Event Radaru">'+
      '<section class="ceyrl-aside-panel"><div class="ceyrl-panel-head"><h2>Stav zdrojov</h2>'+
      '<span class="ceyrl-source-indicator '+(configured&&!failed?'ceyrl-connected':'')+'">'+
      (failed?'Neoverený':configured?'Nastavené':'Obmedzené pokrytie')+'</span></div>'+
      sourceState(status,failed)+'<p class="ceyrl-source-explainer">'+esc(status.coverage_note||'Pokrytie zdrojov sa môže líšiť.')+'</p></section>'+
      '<section class="ceyrl-aside-panel"><div class="ceyrl-panel-head"><h2>Uložené sledovania</h2><span>'+ws.length+'/15</span></div>'+
      watched(ws,watchError)+'</section>'+
      '<section class="ceyrl-aside-panel"><div class="ceyrl-panel-head"><h2>Nové zmeny</h2></div>'+
      changes(hits,watchError)+'</section></aside></main>';
  };
  root?.addEventListener('click',event=>{
    const button=event.target.closest('[data-aurora-view],[data-aurora-reset]');
    if(!button||app.page!=='radar') return;
    if(button.dataset.auroraView) state.view=button.dataset.auroraView;
    else {
      state.from='';state.to='';
      const from=root.querySelector('#ceyrl-date-from'),to=root.querySelector('#ceyrl-date-to');
      if(from) from.value='';
      if(to) to.value='';
      const cc=root.querySelector('#x-radar-country'),kind=root.querySelector('#x-radar-kind');
      if(cc) cc.value='';
      if(kind) kind.value='all';
      xRadarCountry='';xRadarKind='all';
    }
    updateVisible();
  });
  root?.addEventListener('change',event=>{
    if(app.page!=='radar') return;
    const {id,value}=event.target;
    if(id==='ceyrl-date-from')state.from=value;
    else if(id==='ceyrl-date-to')state.to=value;
    else if(id==='ceyrl-results-sort')state.sort=value;
    else return;
    updateVisible();
  });
  function updateVisible(){
    const node=root.querySelector('.ceyrl-radar-results');
    if(node) node.outerHTML=cardsHtml(xRadarEvents);
  }
})();
