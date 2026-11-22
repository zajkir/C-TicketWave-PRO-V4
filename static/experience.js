/* Ceyrl Experience v5 — structural components for the reference design.
 * No new backend permissions, persistence, payment claims or fake event data.
 */
'use strict';
(function installCeyrlExperience() {
  const root=document.getElementById('page-content');
  const esc=x=>escapeHtml(x==null?'':x);
  const count=x=>num(Number(x)||0);
  const date=x=>niceDate(x);
  const now=()=>Date.now();
  const svgPaths={
    overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    radar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    events:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 11h18"/>',
    tickets:'<path d="M3 8V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3a4 4 0 0 0 0 8v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a4 4 0 0 0 0-8Z"/><path d="M13 3v3M13 10v4M13 18v3"/>',
    delivery:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 7h10M7 12h7M7 17h5"/><path d="m15 17 2 2 4-4"/>',
    shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m8 12 3 3 5-6"/>',
    listings:'<path d="m20 12-8 8-9-9V3h8Z"/><circle cx="7.5" cy="7.5" r="1"/>',
    sales:'<path d="M3 3v18h18"/><path d="m7 16 5-5 4 3 5-8"/>',
    expenses:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/>',
    analytics:'<path d="M3 3v18h18M7 16v-4M12 16V7M17 16V9"/>',
    actions:'<path d="M12 2 9 9l-7 3 7 3 3 7 3-7 7-3-7-3-3-7Z"/>',
    copilot:'<path d="M12 3 9 8l-6 3 6 3 3 6 3-6 6-3-6-3-3-5Z"/><path d="M3 19h5"/>',
    activity:'<path d="M4 3v6h6M4 9a9 9 0 1 1-1 7"/><path d="M12 7v5l4 2"/>',
    settings:'<path d="M12 2a3 3 0 0 0-3 3c-1 0-3-1-4 0L3 8c0 1 2 2 2 4s-2 3-2 4l2 3c1 1 3 0 4 0a3 3 0 0 0 6 0c1 0 3 1 4 0l2-3c0-1-2-2-2-4s2-3 2-4l-2-3c-1-1-3 0-4 0a3 3 0 0 0-3-3Z"/><circle cx="12" cy="12" r="3"/>'
  };
  const icon=id=>'<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(svgPaths[id]||svgPaths.overview)+'</svg>';
  const all=new Map(SECTIONS.flatMap(s=>s.items).map(x=>[x[0],x]));
  const group=(label,ids)=>({name:label,items:ids.map(id=>all.get(id)).filter(Boolean)});
  SECTIONS.splice(0,SECTIONS.length,
    group('OBJAVOVANIE',['overview','radar','events']),
    group('VSTUPENKY',['tickets','delivery','shield','listings']),
    group('FINANCIE',['sales','expenses','analytics']),
    group('NÁSTROJE',['actions','copilot','activity']),
    group('OSOBNÉ',['settings']));
  const labels={overview:'Dashboard',radar:'Event Radar',events:'Moje udalosti',
    tickets:'Moje vstupenky',delivery:'Pripravenosť dodania',shield:'Ochrana pred dvojpredajom',
    listings:'Inzeráty',sales:'Predaje',expenses:'Náklady',analytics:'Analytika',
    actions:'Centrum úloh',copilot:'AI asistent',activity:'História aktivít',settings:'Účet a nastavenia'};
  drawNav=function drawExperienceNav(){
    const nav=document.getElementById('sidebar-nav');if(!nav)return;
    nav.innerHTML=SECTIONS.map(g=>'<div class="nav-group">'+esc(g.name)+'</div>'+
      g.items.map(([id])=>'<button type="button" data-page="'+esc(id)+'" class="nav-item'+(app.page===id?' active':'')+'"'+
      (app.page===id?' aria-current="page"':'')+'><span class="nav-icon">'+icon(id)+'</span>'+
      '<span class="ceyrl-nav-label">'+esc(labels[id]||id)+'</span></button>').join('')).join('');
  };
  const originalNavigate=navigate;
  navigate=function navigateExperience(page){
    originalNavigate(page);
    document.body.dataset.ceyrlPage=app.page;
    document.querySelectorAll('#sidebar-nav [data-page]').forEach(b=>{
      if(b.dataset.page===app.page)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
    });
    document.getElementById('crumb-current').textContent=labels[app.page]||app.page;
  };
  const account=document.getElementById('top-avatar');
  if(account) {
    const nameBtn=document.createElement('button');
    nameBtn.type='button';nameBtn.className='ceyrl-top-account';nameBtn.title='Účet a nastavenia';
    nameBtn.textContent='Môj účet';nameBtn.addEventListener('click',()=>navigate('settings'));
    account.parentNode.insertBefore(nameBtn,account);
  }
  const oldShowWorkspace=showWorkspace;
  showWorkspace=function showExperienceWorkspace(){
    oldShowWorkspace();
    const name=(app.user?.display_name||app.user?.email||'Môj účet').trim();
    const title=document.querySelector('.ceyrl-top-account');if(title)title.textContent=name.length>22?name.slice(0,21)+'…':name;
    const el=document.getElementById('workspace-name');if(el)el.textContent='Môj Ceyrl';
    const scr=document.getElementById('sidebar-nav');if(scr&&scr.children.length===0)drawNav();
  };
  const header=(small,title,subtitle,extra='')=>
    '<header class="ceyrl-page-intro"><div class="ceyrl-page-heading"><span class="ceyrl-intro-eyebrow">'+esc(small)+'</span>'+
    '<h1>'+esc(title)+'</h1><p>'+esc(subtitle)+'</p></div>'+extra+'</header>';
  const updateRoot=html=>{if(root)root.innerHTML=html};
  const statusChip=(text,cls='')=>'<span class="ceyrl-status-chip '+cls+'">'+esc(text)+'</span>';
  const eventState={query:'',status:'all',view:'grid'};
  const originalEvents=renderEvents;
  renderEvents=async function renderExperienceEvents(){
    await originalEvents();
    if(app.page!=='events')return;
    const events=Array.isArray(app.events)?app.events:[];
    const upcoming=events.filter(e=>new Date(e.starts_at).getTime()>=now()).length;
    updateRoot(
      header('CEYRL · KALENDÁR','Moje udalosti','Všetky tvoje koncerty a podujatia na jednom mieste.',
        '<button class="btn primary" data-action="new-event">+ Pridať udalosť</button>')+
      '<section class="ceyrl-collection-hero"><div><span>MOJA ZBIERKA PODUJATÍ</span><h2>Miesta, na ktoré sa tešíš.</h2>'+
      '<p>Spravuj termíny, vstupenky a miesta — všetko zostáva vo tvojom súkromnom účte.</p></div>'+
      '<div class="ceyrl-collection-metrics"><strong>'+count(events.length)+'</strong><span>udalostí</span>'+
      '<strong>'+count(upcoming)+'</strong><span>nadchádzajúcich</span></div></section>'+
      '<div class="ceyrl-collection-toolbar"><label class="ceyrl-filter-search">'+icon('radar')+
      '<input id="ceyrl-event-filter" type="search" placeholder="Hľadať v mojich udalostiach…" value="'+esc(eventState.query)+'"></label>'+
      '<label for="ceyrl-event-state" class="ceyrl-filter-select">Zobraziť <select id="ceyrl-event-state">'+
      [['all','Všetky udalosti'],['upcoming','Nadchádzajúce'],['past','Minulé']].map(([v,l])=>
      '<option value="'+v+'"'+(v===eventState.status?' selected':'')+'>'+l+'</option>').join('')+'</select></label>'+
      '<div class="ceyrl-view-controls" aria-label="Zobrazenie udalostí"><button data-experience-event-view="grid" aria-pressed="'+(eventState.view==='grid')+'" title="Mriežka">▦</button>'+
      '<button data-experience-event-view="list" aria-pressed="'+(eventState.view==='list')+'" title="Zoznam">☷</button></div></div>'+
      '<div id="ceyrl-my-events-grid" aria-live="polite"></div>');
    renderMyEventGrid();
  };
  function renderMyEventGrid(){
    if(app.page!=='events')return;
    const region=document.getElementById('ceyrl-my-events-grid');if(!region)return;
    const q=eventState.query.trim().toLocaleLowerCase('sk');
    const rows=(app.events||[]).filter(e=>{
      const time=new Date(e.starts_at).getTime();
      const match=(String(e.title||'')+' '+String(e.city||'')+' '+String(e.venue||'')).toLocaleLowerCase('sk').includes(q);
      return match&&(eventState.status==='all'||(eventState.status==='upcoming'?time>=now():time<now()));
    }).sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at));
    region.innerHTML=rows.length?
      '<div class="ceyrl-private-event-grid '+(eventState.view==='list'?'ceyrl-private-list':'')+'">'+rows.map(e=>
        '<article class="ceyrl-private-event-card"><div class="ceyrl-private-art"><span class="ceyrl-private-category">'+
        esc(e.category||'Podujatie')+'</span><strong class="ceyrl-private-date">'+esc(date(e.starts_at))+'</strong></div>'+
        '<div class="ceyrl-private-event-content"><h3>'+esc(e.title)+'</h3><p>'+esc([e.venue,e.city].filter(Boolean).join(' · ')||'Miesto neuvedené')+'</p>'+
        '<div class="ceyrl-private-event-summary"><span>'+count(e.lots)+' položiek</span>'+
        statusChip(count(e.available)+' voľných','ceyrl-mint')+'</div>'+
        '<button class="btn outline" data-action="edit-event" data-id="'+Number(e.id)+'" type="button">Spravovať udalosť ↗</button></div></article>'
      ).join('')+'</div>':
      '<div class="ceyrl-collection-empty">'+icon('calendar')+'<h3>Žiadne zodpovedajúce udalosti</h3>'+
      '<p>Skús upraviť vyhľadávanie alebo pridať novú udalosť.</p>'+
      '<button type="button" class="btn primary" data-action="new-event">+ Pridať udalosť</button></div>';
  }
  const oldTickets=renderTickets;
  const oldTicketFilter=renderFilteredTickets;
  let ticketView='table';
  renderTickets=async function renderExperienceTickets(){
    await oldTickets();
    if(app.page!=='tickets')return;
    const rows=Array.isArray(app.tickets)?app.tickets:[];
    const total=rows.reduce((s,t)=>s+Number(t.quantity||0),0);
    const remaining=rows.reduce((s,t)=>s+Math.max(0,Number(t.quantity||0)-Number(t.sold_quantity||0)),0);
    const shell=root.querySelector('.page-heading');
    if(shell)shell.outerHTML=header('CEYRL · INVENTÁR','Moje vstupenky','Všetky miesta a PDF na jednom bezpečnom mieste.',
      '<button type="button" class="btn primary" data-action="new-ticket">+ Pridať vstupenky</button>');
    const stats=root.querySelector('.kpi-grid');
    if(stats){
      stats.insertAdjacentHTML('beforebegin',
        '<section class="ceyrl-inventory-banner"><div><span class="ceyrl-intro-eyebrow">SÚKROMNÝ INVENTÁR</span>'+
        '<h2>Každá vstupenka má svoje miesto.</h2><p>Vyhľadaj, skontroluj alebo spravuj svoje PDF vstupenky.</p></div>'+
        '<div class="ceyrl-inventory-counter"><strong>'+count(remaining)+'</strong><span>z '+count(total)+' dostupných miest</span></div></section>');
    }
    const filter=root.querySelector('.filters');
    if(filter){
      filter.insertAdjacentHTML('beforeend',
        '<div class="ceyrl-view-controls" aria-label="Zobrazenie inventára">'+
        '<button type="button" data-experience-ticket-view="table" aria-pressed="'+(ticketView==='table')+'" title="Tabuľka">☷</button>'+
        '<button type="button" data-experience-ticket-view="cards" aria-pressed="'+(ticketView==='cards')+'" title="Karty">▦</button></div>');
    }
    const tableRegion=root.querySelector('#ticket-table');
    if(tableRegion)tableRegion.insertAdjacentHTML('afterend','<div id="ceyrl-ticket-card-grid" class="ceyrl-ticket-card-grid" aria-live="polite"></div>');
    renderTicketCards();
  };
  renderFilteredTickets=function experienceTicketFilter(){oldTicketFilter();renderTicketCards()};
  function renderTicketCards(){
    if(app.page!=='tickets')return;
    const grid=document.getElementById('ceyrl-ticket-card-grid');
    const tableRegion=document.getElementById('ticket-table');
    if(!grid||!tableRegion)return;
    grid.hidden=ticketView!=='cards';tableRegion.hidden=ticketView==='cards';
    if(ticketView!=='cards')return;
    const q=(document.getElementById('ticket-filter')?.value||'').trim().toLowerCase();
    const status=document.getElementById('ticket-status')?.value||'all';
    const rows=(app.tickets||[]).filter(t=>{
      const match=[t.event_title,t.section,t.row_label,t.seats,t.provider].join(' ').toLowerCase().includes(q);
      const available=Number(t.quantity||0)>Number(t.sold_quantity||0);
      return match&&(status==='all'||(status==='available'?available:!available));
    });
    grid.innerHTML=rows.length?rows.map(t=>
      '<article class="ceyrl-ticket-card"><div class="ceyrl-ticket-card-top">'+icon('tickets')+
      statusChip(Number(t.quantity)>Number(t.sold_quantity)?'Dostupné':'Vypredané',
        Number(t.quantity)>Number(t.sold_quantity)?'ceyrl-mint':'')+'</div>'+
      '<h3>'+esc(t.event_title)+'</h3><p>'+esc(date(t.starts_at))+'</p>'+
      '<div class="ceyrl-ticket-card-info"><span>Sektor: '+esc(t.section||'Voľné státie')+'</span>'+
      '<span>Rad: '+esc(t.row_label||'—')+' · Sedadlá: '+esc(t.seats||'—')+'</span>'+
      '<span>'+count(Math.max(0,Number(t.quantity)-Number(t.sold_quantity)))+' / '+count(t.quantity)+' voľných</span>'+
      '<span>'+count(t.pdf_count)+' PDF</span></div>'+
      '<div class="ceyrl-ticket-card-actions"><button type="button" class="btn outline" data-action="manage-pdf" data-id="'+Number(t.id)+'">PDF trezor</button>'+
      '<button type="button" class="btn primary" data-action="sale-ticket" data-id="'+Number(t.id)+'">Predať ↗</button></div></article>'
    ).join(''):'<div class="ceyrl-collection-empty"><strong>Žiadne zodpovedajúce vstupenky</strong></div>';
  }
  const oldSales=renderSales;
  renderSales=async function renderExperienceSales(){
    await oldSales();
    if(app.page!=='sales')return;
    const pageHeader=root.querySelector('.page-heading');
    if(pageHeader)pageHeader.outerHTML=header('CEYRL · PREDAJE','Predaje','Aktuálny stav transakcií a výnosov zo skutočných záznamov.',
      '<button type="button" class="btn primary" data-action="new-sale">+ Zaznamenať predaj</button>');
    const table=root.querySelector('.data-table');
    if(table){
      const parent=table.closest('.panel') || table.parentElement;
      const controls=document.createElement('div');controls.className='ceyrl-table-search';
      controls.innerHTML='<label>'+icon('radar')+'<input type="search" id="ceyrl-sales-filter" placeholder="Hľadať podujatie, predajný kanál alebo referenciu…"></label>';
      parent.insertBefore(controls,parent.querySelector('.table-wrap')||table);
    }
  };
  const oldAnalytics=renderAnalytics;
  renderAnalytics=async function renderExperienceAnalytics(){
    await oldAnalytics();
    if(app.page!=='analytics')return;
    const hdr=root.querySelector('.page-heading');
    if(hdr)hdr.outerHTML=header('CEYRL · ANALYTIKA','Výsledky predajov',
      'Výpočty zo skutočne zaznamenaných predajov, poplatkov a nákladov.',
      '<button type="button" class="btn outline" data-action="export-sales">Export CSV ↗</button>');
    const list=(app.recaps||[]).filter(x=>Number.isFinite(Number(x.profit_cents))).slice(0,8);
    const max=Math.max(1,...list.map(x=>Math.abs(Number(x.profit_cents))));
    const chart='<section class="ceyrl-profit-visual"><div><span class="ceyrl-intro-eyebrow">VÝNOSNOSŤ PODUJATÍ</span>'+
      '<h2>Čistý zisk podľa podujatia</h2><p>Len zaznamenané transakcie v EUR.</p></div>'+
      (list.length?'<div class="ceyrl-profit-bars">'+list.map(x=>{
        const amount=Number(x.profit_cents);
        const level=Math.min(20,Math.max(0,Math.round(Math.abs(amount)/max*20)));
        return '<div class="ceyrl-profit-row"><strong title="'+esc(x.title)+'">'+esc(x.title)+'</strong>'+
          '<div class="ceyrl-profit-track"><div class="ceyrl-profit-level-'+level+' '+(amount<0?'ceyrl-profit-neg':'')+'"></div></div>'+
          '<span>'+esc(money(amount))+'</span></div>';
      }).join('')+'</div>':'<p class="ceyrl-panel-muted">Graf bude dostupný po zaznamenaní predaja.</p>')+
      '</section>';
    const existing=root.querySelector('.kpi-grid');
    if(existing)existing.insertAdjacentHTML('afterend',chart);
  };
  const oldSettings=renderSettings;
  renderSettings=async function renderExperienceSettings(){
    await oldSettings();
    if(app.page!=='settings')return;
    const hdr=root.querySelector('.page-heading');
    if(hdr)hdr.outerHTML=header('CEYRL · MÔJ ÚČET','Účet a nastavenia',
      'Profil, ochrana účtu, súkromné údaje a vzhľad aplikácie.');
    const grid=root.querySelector('.studio-account-grid');
    if(!grid||grid.closest('.ceyrl-settings-layout'))return;
    const panels=[...grid.querySelectorAll('.studio-settings-panel')];
    const names=['Profil','Bezpečnosť','Moje údaje','Vzhľad'];
    panels.forEach((p,i)=>{p.id='ceyrl-settings-section-'+i;p.tabIndex=-1});
    const wrap=document.createElement('div');wrap.className='ceyrl-settings-layout';
    const navEl=document.createElement('nav');
    navEl.className='ceyrl-settings-nav';navEl.setAttribute('aria-label','Sekcie nastavení');
    navEl.innerHTML='<span class="ceyrl-intro-eyebrow">NASTAVENIA</span>'+names.map((v,i)=>
      '<button type="button" data-experience-settings-tab="'+i+'">'+
      '<span>'+icon(['settings','shield','tickets','analytics'][i])+'</span>'+esc(v)+' ↗</button>').join('')+
      '<p>Všetky osobné údaje zostávajú súkromné. Neaktívne bezpečnostné funkcie nezobrazujeme ako zapnuté.</p>';
    grid.parentNode.insertBefore(wrap,grid);
    wrap.appendChild(navEl);wrap.appendChild(grid);
  };
  root?.addEventListener('click',event=>{
    const e=event.target.closest('[data-experience-event-view],[data-experience-ticket-view],[data-experience-settings-tab]');
    if(!e)return;
    if(e.hasAttribute('data-experience-event-view')&&app.page==='events'){
      eventState.view=e.dataset.experienceEventView;renderMyEventGrid();
      root.querySelectorAll('[data-experience-event-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.experienceEventView===eventState.view)));
    }else if(e.hasAttribute('data-experience-ticket-view')&&app.page==='tickets'){
      ticketView=e.dataset.experienceTicketView;renderTicketCards();
      root.querySelectorAll('[data-experience-ticket-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.experienceTicketView===ticketView)));
    }else if(e.hasAttribute('data-experience-settings-tab')&&app.page==='settings'){
      const panel=root.querySelector('#ceyrl-settings-section-'+e.dataset.experienceSettingsTab);
      if(panel){panel.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});panel.focus({preventScroll:true})}
    }
  });
  root?.addEventListener('input',event=>{
    if(app.page==='events'&&event.target.id==='ceyrl-event-filter'){
      eventState.query=event.target.value;renderMyEventGrid();
    }else if(app.page==='sales'&&event.target.id==='ceyrl-sales-filter'){
      const q=event.target.value.trim().toLowerCase();
      root.querySelectorAll('.data-table tbody tr').forEach(tr=>tr.hidden=!tr.textContent.toLowerCase().includes(q));
    }
  });
  root?.addEventListener('change',event=>{
    if(app.page==='events'&&event.target.id==='ceyrl-event-state'){
      eventState.status=event.target.value;renderMyEventGrid();
    }
  });
  // Event Radar side panel draws only data already belonging to the current account.
  const oldRadar=renderXRadar;
  let radarSequence=0;
  let radarHorizon='7';
  renderXRadar=async function renderExperienceRadar(){
    const seq=++radarSequence;
    await oldRadar();
    if(app.page!=='radar'||seq!==radarSequence)return;
    const aside=root.querySelector('.ceyrl-radar-aside');
    if(!aside)return;
    const pending=document.createElement('section');pending.className='ceyrl-aside-panel ceyrl-upcoming-panel';
    pending.innerHTML='<div class="ceyrl-panel-head"><h2>Nadchádzajúce podujatia</h2></div><p class="ceyrl-panel-muted">Načítavam tvoj kalendár…</p>';
    const before=aside.querySelectorAll('.ceyrl-aside-panel')[1];
    aside.insertBefore(pending,before||null);
    try{
      const events=await api('/events');
      if(app.page!=='radar'||seq!==radarSequence||!pending.isConnected)return;
      pending.dataset.events=String(Array.isArray(events)?events.length:0);
      const renderHorizon=()=>{
        const days=Number(radarHorizon)||7;
        const start=now(),end=start+days*86400000;
        const filtered=(Array.isArray(events)?events:[]).filter(e=>{
          const t=new Date(e.starts_at).getTime();return t>=start&&t<=end;
        }).sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at));
        const bars=[0,0,0,0,0,0,0];
        filtered.forEach(e=>{
          const n=new Date(e.starts_at).getTime();
          const index=Math.min(6,Math.max(0,Math.floor((n-start)/(days*86400000)*7)));
          bars[index]++;
        });
        const max=Math.max(1,...bars);
        pending.innerHTML='<div class="ceyrl-panel-head"><h2>Nadchádzajúce podujatia</h2><span>'+filtered.length+'</span></div>'+
          '<div class="ceyrl-panel-segments">'+[['7','7 dní'],['30','30 dní'],['90','90 dní']].map(([d,label])=>
            '<button type="button" data-ceyrl-horizon="'+d+'" aria-pressed="'+(radarHorizon===d)+'">'+label+'</button>').join('')+'</div>'+
          '<div class="ceyrl-calendar-bars" role="img" aria-label="'+filtered.length+' tvojich udalostí počas '+days+' dní">'+
          bars.map(n=>'<span class="ceyrl-calendar-level-'+(n?Math.min(20,Math.max(1,Math.round(n/max*20))):0)+'"></span>').join('')+'</div>'+
          '<div class="ceyrl-calendar-label"><span>Teraz</span><span>+'+days+' dní</span></div>'+
          (filtered.length?'<div class="ceyrl-upcoming-list">'+filtered.slice(0,3).map(e=>
            '<div><strong>'+esc(e.title)+'</strong><small>'+esc(date(e.starts_at))+'</small></div>').join('')+'</div>':
            '<p class="ceyrl-panel-muted">V tomto období nemáš v osobnom kalendári naplánované podujatia.</p>');
      };
      pending.addEventListener('click',e=>{
        const btn=e.target.closest('[data-ceyrl-horizon]');if(!btn)return;
        radarHorizon=btn.dataset.ceyrlHorizon;renderHorizon();
      });
      renderHorizon();
    }catch(error){
      if(pending.isConnected)pending.innerHTML='<div class="ceyrl-panel-head"><h2>Nadchádzajúce podujatia</h2></div>'+
        '<p class="ceyrl-panel-muted" role="alert">Kalendár momentálne nie je dostupný.</p>';
    }
  };
})();