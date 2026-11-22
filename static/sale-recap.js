/* Ceyrl • Sale Recap v1
 * Interactive details of one real account-owned sale. No synthetic payout,
 * customer, resale ranking or timeline records are created.
 */
'use strict';
(function installSaleRecap(){
  const root=document.getElementById('page-content');
  if(!root) return;
  const safe=x=>escapeHtml(x===null||x===undefined?'':x);
  const format=(c,unit)=>money(c,unit||'EUR');
  const qty=n=>num(Number(n)||0);
  const reduced=()=>document.body.classList.contains('motion-off') ||
    window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  const date=x=>{
    if(!x)return 'Neuvedené';
    const t=new Date(x);
    if(!Number.isFinite(t.getTime()))return 'Neuvedené';
    return new Intl.DateTimeFormat('sk-SK',{day:'numeric',month:'long',year:'numeric',
      hour:'2-digit',minute:'2-digit',timeZone:'Europe/Bratislava'}).format(t);
  };
  const shortDate=x=>x?niceDate(x):'Neuvedené';
  let overlay=null, opener=null, detail=null, currentId=null, mode='quick', tab='overview', serial=0;
  const stat=(label,value,note='',cls='')=>
    '<div class="sale-recap-stat '+cls+'"><small>'+safe(label)+'</small>'+
    '<strong>'+safe(value)+'</strong>'+(note?'<span>'+safe(note)+'</span>':'')+'</div>';
  const valueOr=(val,cur)=>Number.isFinite(val)?format(val,cur):'Nedostupné';
  const profitString=d=>d.sale_margin_cents===null?
    'Nedostupné':format(d.sale_margin_cents,d.currency);
  const roiString=d=>d.sale_roi_percent===null?'Nedostupné':
    (d.sale_roi_percent>0?'+':'')+Number(d.sale_roi_percent).toLocaleString('sk-SK',
      {maximumFractionDigits:2,minimumFractionDigits:0})+' %';
  const note=d=>d.currency_mismatch?
    'Nákup a predaj sú v rôznych menách. Maržu a ROI nemožno vypočítať bez overeného kurzu.':
    'Marža je tržba mínus poplatky a nákupná cena predaných vstupeniek. Neobsahuje spoločné náklady podujatia.';
  const saleTitle=d=>safe(d.event_title||'Zaznamenaný predaj');
  const tickets=d=>{
    const n=Math.max(0,Math.floor(Number(d.quantity)||0));
    const visible=Math.min(n,8);
    return '<div class="sale-recap-tickets" aria-label="Počet vstupeniek: '+n+'">'+
      Array.from({length:visible},(_,i)=>
      '<span class="sale-recap-ticket" aria-hidden="true"><span>CEYRL</span><b>♫</b></span>').join('')+
      (n>visible?'<span class="sale-recap-ticket-more">+'+qty(n-visible)+'</span>':'')+'</div>';
  };
  const breakdown=d=>
    '<div class="sale-recap-breakdown">'+
    '<div><span>Tržba predaja</span><b>'+safe(format(d.revenue_cents,d.currency))+'</b></div>'+
    '<div><span>Poplatky</span><b>− '+safe(format(d.fee_cents,d.currency))+'</b></div>'+
    '<div><span>Výnos po poplatkoch</span><b>'+safe(format(d.net_receipts_cents,d.currency))+'</b></div>'+
    '<div><span>Nákup predaných miest</span><b>'+
       (d.sold_purchase_cost_cents===null?'Iná mena':
       '− '+safe(format(d.sold_purchase_cost_cents,d.currency)))+'</b></div>'+
    '<div class="sale-recap-breakdown-final"><span>Marža tohto predaja</span><b>'+
    safe(profitString(d))+'</b></div></div>';
  const timeline=d=>{
    // There are only two source facts: when the sale was recorded and the
    // user-entered sale date. Neither proves actual platform settlement.
    const points=[
      {stamp:d.sold_at,title:'Dátum predaja',description:'Dátum zadaný pri evidencii transakcie'},
      {stamp:d.created_at,title:'Zápis do Ceyrlu',description:'Čas vytvorenia záznamu v súkromnom účte'}
    ].filter(x=>x.stamp).sort((a,b)=>Date.parse(a.stamp)-Date.parse(b.stamp));
    return '<ol class="sale-recap-timeline">'+points.map((x,i)=>
      '<li><span class="sale-recap-timeline-dot">'+(i+1)+'</span>'+
      '<div><strong>'+safe(x.title)+'</strong><time>'+safe(date(x.stamp))+'</time>'+
      '<p>'+safe(x.description)+'</p></div></li>').join('')+
      '<li class="sale-recap-unconfirmed"><span class="sale-recap-timeline-dot">?</span>'+
      '<div><strong>Vyplatenie platformou</strong><p>Stav výplaty sa v Ceyrle neeviduje; nie je potvrdený.</p></div></li></ol>';
  };
  const panels=d=>{
    switch(tab){
    case 'profit':return '<section class="sale-recap-tab-panel">'+
      '<div class="sale-recap-panel-head"><h3>Rozpis predaja</h3><p>Presné údaje z tvojho záznamu, bez odhadovaných výplat.</p></div>'+
      breakdown(d)+
      '<div class="sale-recap-note">'+safe(note(d))+'</div>'+
      '<div class="sale-recap-metric-grid">'+
      stat('Nákupná cena za vstupenku',format(d.purchase_cents,d.purchase_currency))+
      stat('Počet predaných kusov',qty(d.quantity))+
      stat('ROI len z tohto predaja',roiString(d),'Bez spoločných nákladov podujatia')+
      '</div></section>';
    case 'tickets':return '<section class="sale-recap-tab-panel">'+
      '<div class="sale-recap-panel-head"><h3>Predané vstupenky</h3><p>Vizuál je ilustračný, nejde o skutočné QR kódy ani čísla sedadiel.</p></div>'+
      tickets(d)+
      '<div class="sale-recap-meta-grid">'+
      stat('Predaných v tejto transakcii',qty(d.quantity))+
      stat('Sektor',d.section||'Neuvedený')+
      stat('Rad',d.row_label||'Neuvedený')+
      stat('Sedadlá',d.seats||'Neuvedené')+
      stat('Typ vstupenky',d.ticket_type||'Neuvedený')+
      stat('Pôvodný predajca',d.provider||'Neuvedený')+
      '</div><p class="sale-recap-muted">Údaje o sektore a sedadlách sú uložené pri celej dávke vstupeniek, nie jednotlivo pri tomto predaji.</p></section>';
    case 'timeline':return '<section class="sale-recap-tab-panel">'+
      '<div class="sale-recap-panel-head"><h3>Časová os predaja</h3><p>Iba udalosti, ktoré Ceyrl naozaj zaznamenal.</p></div>'+
      timeline(d)+'</section>';
    default:
      return '<section class="sale-recap-tab-panel">'+
      '<div class="sale-recap-metric-grid">'+
      stat('Tržba',format(d.revenue_cents,d.currency))+
      stat('Poplatky',format(d.fee_cents,d.currency))+
      stat('Nákup predaných kusov',valueOr(d.sold_purchase_cost_cents,d.currency))+
      stat('ROI predaja',roiString(d))+'</div>'+
      '<div class="sale-recap-overview-grid">'+
      '<div class="sale-recap-little-card"><span>Počet predaných vstupeniek</span>'+
      '<strong>'+qty(d.quantity)+'</strong>'+tickets(d)+'</div>'+
      '<div class="sale-recap-little-card"><span>Údaje transakcie</span>'+
      '<dl><dt>Kanál</dt><dd>'+safe(d.channel||'Neuvedený')+'</dd>'+
      '<dt>Referencia</dt><dd>'+safe(d.reference||'Neuvedená')+'</dd>'+
      '<dt>Miesto</dt><dd>'+safe([d.event_venue,d.event_city].filter(Boolean).join(' · ')||'Neuvedené')+'</dd>'+
      '<dt>Stav výplaty</dt><dd>Neevidovaný</dd></dl></div></div>'+
      '<p class="sale-recap-muted">'+safe(note(d))+'</p></section>';
    }
  };
  const tabs=()=>'<div class="sale-recap-tabs" role="tablist" aria-label="Detaily predaja">'+
    [['overview','Prehľad'],['profit','Výpočet marže'],['tickets','Vstupenky'],['timeline','Časová os']].map(([id,label])=>
      '<button type="button" role="tab" data-sale-tab="'+id+'" aria-selected="'+(tab===id)+'" tabindex="'+(tab===id?'0':'-1')+'">'+safe(label)+'</button>').join('')+'</div>';
  const backdrop=()=>'<div class="sale-recap-aurora" aria-hidden="true">'+
    '<span class="sale-orb sale-orb-one"></span><span class="sale-orb sale-orb-two"></span>'+
    '<span class="sale-orb sale-orb-three"></span><span class="sale-light-ray"></span>'+
    '<span class="sale-wave sale-wave-one"></span><span class="sale-wave sale-wave-two"></span>'+
    '<span class="sale-particles"></span></div>';
  function renderSheet(){
    if(!overlay||!detail)return;
    const d=detail;
    const eventName=String(d.event_title||'Zaznamenaný predaj');
    const initial=eventName.trim().slice(0,1).toLocaleUpperCase('sk')||'C';
    const location=[d.event_venue,d.event_city,d.event_country].filter(Boolean).join(' · ')||'Miesto neuvedené';
    const marginKnown=d.sale_margin_cents!==null;
    const marginState=!marginKnown?'Nevypočítaná marža':d.sale_margin_cents<0?'Záporná marža':'Kladná marža';
    const className=!marginKnown?'sale-unknown':d.sale_margin_cents<0?'sale-negative':'sale-positive';
    const label='Sale Recap · '+eventName+', predaj '+d.id;
    overlay.className='ceyrl-sale-overlay ceyrl-sale-mode-'+mode;
    overlay.innerHTML=backdrop()+
      '<div class="ceyrl-sale-shade" data-sale-close></div>'+
      '<section class="sale-recap-sheet" role="dialog" aria-modal="true" aria-label="'+safe(label)+'" tabindex="-1">'+
      '<header class="sale-recap-header"><div class="sale-recap-logo-line"><span class="sale-recap-symbol">C</span>'+
      '<span class="sale-recap-brand">Ceyrl</span><span class="sale-recap-header-divide">/</span>'+
      '<span class="sale-recap-header-context">'+(mode==='full'?'SALE RECAP STUDIO':'RÝCHLA REKAPITULÁCIA')+'</span></div>'+
      '<div class="sale-recap-header-actions"><span class="sale-recap-private-tag">✧ Súkromný prehľad</span>'+
      (mode==='full'?'<button type="button" data-sale-mode="quick" class="sale-recap-small">Zmenšiť</button>':'<button type="button" data-sale-mode="full" class="sale-recap-small">↗ Celá obrazovka</button>')+
      '<button type="button" data-sale-close class="sale-recap-close" aria-label="Zavrieť detail predaja">×</button>'+
      '</div></header>'+
      '<div class="sale-recap-scroll">'+
      '<div class="sale-recap-stage">'+
        '<section class="sale-recap-event" aria-label="Podujatie">'+
          '<div class="sale-recap-event-shimmer" aria-hidden="true"></div>'+
          '<div class="sale-recap-event-inner">'+
            '<div class="sale-recap-overline"><span>CEYRL / PERSONAL RECAP</span><span>NO. '+Number(d.id)+'</span></div>'+
            '<div class="sale-recap-event-heading">'+
              '<div class="sale-recap-artist-avatar" aria-hidden="true">'+safe(initial)+'</div>'+
              '<div><div class="sale-recap-eyebrow">EVENT · SALES SUMMARY</div>'+
                '<h2>'+saleTitle(d)+'</h2>'+
              '</div>'+
            '</div>'+
            '<div class="sale-recap-event-facts">'+
              '<div><span aria-hidden="true">⌖</span><span>'+safe(location)+'</span></div>'+
              '<div><span aria-hidden="true">▤</span><span>'+safe(shortDate(d.event_starts_at))+'</span></div>'+
              '<div><span aria-hidden="true">↗</span><span>Predaj '+safe(shortDate(d.sold_at))+'</span></div>'+
            '</div>'+
            '<div class="sale-recap-event-bottom"><span>ADMIT ONE · CEYRL</span>'+
             '<span>'+safe(qty(d.quantity))+' '+(Number(d.quantity)===1?'VSTUPENKA':'VSTUPENKY')+'</span></div>'+
          '</div>'+
        '</section>'+
        '<section class="sale-recap-profit" aria-label="Marža predaja">'+
          '<div class="sale-recap-profit-top"><span>FINANCIAL PERFORMANCE</span>'+
            '<span class="sale-recap-profit-indicator">'+safe(marginState)+'</span></div>'+
          '<div class="sale-recap-profit-main"><div class="sale-recap-profit-label">MARŽA KONKRÉTNEHO PREDAJA</div>'+
            '<strong class="'+className+'" '+
              (marginKnown?'data-sale-animate="'+Number(d.sale_margin_cents)+'" data-currency="'+safe(d.currency)+'"':'')+
            '>'+safe(profitString(d))+'</strong>'+
            '<span class="sale-recap-roi">'+(d.sale_roi_percent===null?'ROI nie je dostupné':
              'ROI '+safe(roiString(d)))+'</span>'+
            '<div class="sale-recap-profit-caption">Tržba − poplatky − nákup predaných vstupeniek</div>'+
          '</div>'+
          '<div class="sale-recap-profit-bottom"><span>Výpočet vychádza z evidovaných údajov</span>'+
             '<span>SALE #'+Number(d.id)+'</span></div>'+
        '</section>'+
      '</div>'+
      '<section class="sale-recap-summary-strip" aria-label="Základné údaje o predaji">'+
        '<div><span>TRŽBA</span><strong>'+safe(format(d.revenue_cents,d.currency))+'</strong></div>'+
        '<div><span>NAKÚPENÉ VSTUPENKY</span><strong>'+safe(valueOr(d.sold_purchase_cost_cents,d.currency))+'</strong></div>'+
        '<div><span>PREDANÝCH KUSOV</span><strong>'+safe(qty(d.quantity))+'</strong></div>'+
        '<div><span>ROI PREDAJA</span><strong class="'+className+'">'+safe(roiString(d))+'</strong></div>'+
      '</section>'+
      '<div class="sale-recap-section-heading"><div><span>DETAIL TRANSAKCIE</span><h3>Všetko o tomto predaji</h3></div>'+
        '<span class="sale-recap-section-code">CR–'+String(d.id).padStart(5,'0')+'</span></div>'+
      tabs()+
      '<div id="sale-recap-active-panel" role="tabpanel">'+panels(d)+'</div>'+
      '<div class="sale-recap-controls">'+
      (mode==='quick'?'<button type="button" class="btn primary" data-sale-mode="full">Otvoriť celý Sale Recap ↗</button>':
        '<button type="button" class="btn outline" data-sale-show-event>Zobraziť moje udalosti ↗</button>')+
      '<button type="button" class="btn outline" data-sale-copy>Kopírovať súhrn</button>'+
      (mode==='full'?'<button type="button" class="btn outline" data-sale-print>Tlačiť / Uložiť PDF</button>':'')+
      '</div>'+
      '<div class="sale-recap-perforation" aria-hidden="true"><span></span><span></span></div>'+
      '<footer class="sale-recap-footer"><span>✧ CEYRL · PRIVATE SALE ARCHIVE</span>'+
      '<span>Záznam predaja • '+safe(date(d.created_at))+'</span></footer>'+
      '</div></section>';
    overlay.querySelector('.sale-recap-close')?.focus({preventScroll:true});
    animateNumber();
  }
    function animateNumber(){
    if(!overlay||reduced())return;
    const el=overlay.querySelector('[data-sale-animate]');
    if(!el)return;
    const to=Number(el.dataset.saleAnimate),cur=el.dataset.currency;
    if(!Number.isFinite(to))return;
    const start=performance.now(),duration=850,round=x=>Math.round(x);
    function tick(t){
      if(!el.isConnected||reduced())return;
      const p=Math.min(1,Math.max(0,(t-start)/duration));
      const easing=1-Math.pow(1-p,3);
      el.textContent=format(round(to*easing),cur);
      if(p<1)requestAnimationFrame(tick);
    }
    el.textContent=format(0,cur);
    requestAnimationFrame(tick);
  }
  function ensureOverlay(){
    if(!overlay){overlay=document.createElement('div');overlay.id='ceyrl-sale-overlay';document.body.appendChild(overlay);}
    document.body.classList.add('ceyrl-sale-open');
  }
  function close(){
    serial++;
    if(overlay){overlay.remove();overlay=null;}
    document.body.classList.remove('ceyrl-sale-open');
    detail=null;currentId=null;
    if(opener?.isConnected)opener.focus({preventScroll:true});
    opener=null;
  }
  async function open(id,trigger){
    if(!Number.isInteger(id)||id<1)return;
    close();
    // close() invalidates pending requests; restart at a unique sequence.
    const token=++serial;
    opener=trigger||document.activeElement;
    ensureOverlay();mode='quick';tab='overview';currentId=id;
    overlay.className='ceyrl-sale-overlay ceyrl-sale-loading';
    overlay.innerHTML='<div class="ceyrl-sale-shade" data-sale-close></div>'+
      '<div class="sale-recap-loading" role="status">Načítavam súkromný predaj…</div>';
    try{
      const data=await api('/sales/'+id);
      if(serial!==token||!overlay)return;
      if(!app.user){close();return;}
      detail=data;renderSheet();
    }catch(error){
      if(serial!==token||!overlay)return;
      overlay.innerHTML='<div class="ceyrl-sale-shade" data-sale-close></div>'+
        '<div class="sale-recap-loading" role="alert"><h2>Detail sa nepodarilo načítať</h2>'+
        '<p>'+safe(error.message||'Skús to znova.')+'</p>'+
        '<button type="button" class="btn outline" data-sale-close>Zavrieť</button></div>';
    }
  }
  const oldRender=renderSales;
  renderSales=async function renderSalesWithRecaps(){
    close();
    await oldRender();
    if(app.page!=='sales')return;
    const rows=root.querySelectorAll('.data-table tbody tr');
    rows.forEach((tr,i)=>{
      const sale=app.sales?.[i];
      if(!sale||!Number.isInteger(Number(sale.id)))return;
      tr.dataset.ceyrlSaleId=String(sale.id);
      tr.classList.add('ceyrl-sale-row');
      tr.tabIndex=0;
      tr.title='Rozkliknúť detail predaja';
      const td=tr.lastElementChild;
      if(td)td.insertAdjacentHTML('beforeend',' <button type="button" class="ceyrl-sale-detail-button"'+
        ' data-ceyrl-sale-open="'+Number(sale.id)+'" aria-label="Zobraziť predaj '+Number(sale.id)+'">↗ Detail</button>');
    });
    const ledger=root.querySelector('.data-table')?.closest('.panel');
    if(ledger)ledger.classList.add('ceyrl-sale-ledger-panel');
    const hint=document.createElement('p');
    hint.className='ceyrl-sale-ledger-hint';
    hint.textContent='Klikni na predaj alebo na „Detail“ a otvorí sa osobná rekapitulácia.';
    ledger?.querySelector('.ceyrl-table-search')?.insertAdjacentElement('afterend',hint);
  };
  const prevNavigate=navigate;
  navigate=function navigateWithSaleRecap(page){close();return prevNavigate(page)};
  const previousShowAuth=showAuth;
  showAuth=function showAuthWithoutPrivateSaleData(mode){
    close();return previousShowAuth(mode);
  };
  root.addEventListener('click',e=>{
    if(app.page!=='sales')return;
    const btn=e.target.closest('[data-ceyrl-sale-open]');
    const row=btn?.closest('tr')||e.target.closest('tr[data-ceyrl-sale-id]');
    if(!row)return;
    const id=Number(btn?.dataset.ceyrlSaleOpen||row.dataset.ceyrlSaleId);
    if(id)open(id,btn||row);
  });
  root.addEventListener('keydown',e=>{
    if(app.page!=='sales'||!['Enter',' '].includes(e.key))return;
    if(e.target.matches('tr[data-ceyrl-sale-id]')){
      e.preventDefault();open(Number(e.target.dataset.ceyrlSaleId),e.target);
    }
  });
  document.addEventListener('click',e=>{
    if(!overlay)return;
    const target=e.target.closest('[data-sale-close],[data-sale-mode],[data-sale-tab],[data-sale-copy],[data-sale-print],[data-sale-show-event]');
    if(!target||!overlay.contains(target))return;
    if(target.hasAttribute('data-sale-close'))return close();
    if(target.dataset.saleMode){
      mode=target.dataset.saleMode;tab='overview';renderSheet();
      return;
    }
    if(target.dataset.saleTab){
      tab=target.dataset.saleTab;
      const panel=overlay.querySelector('#sale-recap-active-panel');
      if(panel)panel.innerHTML=panels(detail);
      overlay.querySelectorAll('[data-sale-tab]').forEach(b=>{
        const active=b.dataset.saleTab===tab;
        b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;
      });
      return;
    }
    if(target.hasAttribute('data-sale-show-event')){close();return navigate('events')}
    if(target.hasAttribute('data-sale-print'))return window.print();
    if(target.hasAttribute('data-sale-copy')){
      const d=detail;
      if(!d)return;
      const summary=[
        'Ceyrl · Rekapitulácia predaja #'+d.id,
        d.event_title||'',
        'Dátum predaja: '+date(d.sold_at),
        'Vstupenky: '+d.quantity,
        'Tržba: '+format(d.revenue_cents,d.currency),
        'Poplatky: '+format(d.fee_cents,d.currency),
        'Nákup predaných miest: '+(d.sold_purchase_cost_cents===null?'Iná mena':format(d.sold_purchase_cost_cents,d.currency)),
        'Marža (bez nákladov podujatia): '+profitString(d),
        'ROI: '+roiString(d),
        'Stav výplaty: neevidovaný'
      ].join('\n');
      navigator.clipboard.writeText(summary).then(()=>notify('Súhrn bol skopírovaný.')).catch(()=>notify('Kopírovanie nebolo povolené.',true));
    }
  });
  document.addEventListener('keydown',e=>{
    if(!overlay)return;
    if(e.key==='Escape'){e.preventDefault();close();return;}
    if(e.target?.matches?.('[data-sale-tab]') && ['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){
      const items=[...overlay.querySelectorAll('[data-sale-tab]')];
      const index=items.indexOf(e.target);
      if(index>=0){
        e.preventDefault();
        let next=e.key==='Home'?0:e.key==='End'?items.length-1:
          (index+(e.key==='ArrowRight'?1:-1)+items.length)%items.length;
        items[next].click();
        overlay.querySelectorAll('[data-sale-tab]')[next]?.focus();
        return;
      }
    }
    if(e.key!=='Tab')return;
    const focusable=[...overlay.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),[tabindex="0"]')]
      .filter(x=>x.getClientRects().length);
    if(!focusable.length)return;
    const first=focusable[0],last=focusable[focusable.length-1];
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  });
})();