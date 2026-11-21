/* Ceyrl — no CDN, independent authenticated workspace. */
'use strict';
const $=(selector)=>document.querySelector(selector);
const escapeHtml=(value)=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const money=(c,currency='EUR')=>{try{return new Intl.NumberFormat('en-IE',{style:'currency',currency}).format((Number(c)||0)/100)}catch{return (Number(c||0)/100).toFixed(2)+' '+currency}};
const num=(v)=>new Intl.NumberFormat('en-GB').format(v||0);
const niceDate=(v)=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(+d)?'—':new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(d)};
const inputDate=(offset=0)=>{const date=new Date(Date.now()+offset*864e5);return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)};
const isoLocal=(s)=>new Date(s).toISOString();
const statusTag=(text)=>{const s=String(text||'draft').toLowerCase();const cls=s==='listed'||s==='sold'?'green':s==='ready'||s==='available'?'blue':s==='paused'?'gold':s==='cancelled'?'red':'grey';return `<span class="tag ${cls}">● ${escapeHtml(text)}</span>`};
const app={user:null,csrf:'',authMode:'login',google:false,email:false,page:'overview',events:[],tickets:[],listings:[],sales:[],expenses:[],recaps:[],dashboard:null,search:''};
const SECTIONS=[
 {name:'WORKSPACE',items:[['overview','▦','Overview'],['actions','✦','Action Center'],['events','▤','My Events']]},
 {name:'INVENTORY',items:[['tickets','▧','Ticket Inventory'],['listings','◇','Listings']]},
 {name:'FINANCES',items:[['sales','↗','Sales Tracker'],['expenses','€','Expenses & Costs'],['analytics','◫','Analytics']]},
 {name:'PERSONAL',items:[['activity','≡','Activity Log'],['settings','♙','My Account']]}
];
async function api(path,opts={}){
 const options={credentials:'same-origin',...opts};
 if(options.body&&!(options.body instanceof FormData)&&typeof options.body!=='string'){
  options.body=JSON.stringify(options.body);
  options.headers={...(options.headers||{}),'Content-Type':'application/json'};
 }
 if(options.method&&options.method.toUpperCase()!=='GET'){
  options.headers={...(options.headers||{}),'x-csrf-token':app.csrf};
 }
 const response=await fetch('/api'+path,options);
 const raw=await response.text();let data;
 try{data=raw?JSON.parse(raw):{}}catch{data={detail:raw.slice(0,250)}}
 if(!response.ok){if(response.status===401&&app.user){app.user=null;showAuth('login')}
  throw Error(typeof data.detail==='string'?data.detail:'Request failed ('+response.status+').')}
 return data;
}
function notify(message,error=false){const el=document.createElement('div');el.className='toast'+(error?' error':'');el.textContent=message;$('#toast-stack').appendChild(el);setTimeout(()=>el.remove(),4800)}
function notifyError(error){notify(error?.message||String(error),true)}
function toggle(selector,show){$(selector).classList.toggle('hidden',!show)}
function heading(title,subtitle,actions=''){return `<div class="page-heading"><div><div class="eyebrow">CEYRL / PRIVATE WORKSPACE</div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div><div class="heading-actions">${actions}</div></div>`}
function button(label,action,style='primary'){return `<button type="button" class="btn ${style}" data-action="${escapeHtml(action)}">${label}</button>`}
function card(title,subtitle,body,action=''){return `<section class="panel"><div class="panel-head"><div><h2>${title}</h2><p>${subtitle}</p></div>${action}</div>${body}</section>`}
function table(columns,rows,emptyMsg='No records yet'){return rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr>${columns.map(s=>`<th>${s}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`:empty('◈',emptyMsg,'Create your first record to get started.');}
function empty(icon,title,desc,action=''){return `<div class="empty-state"><div class="empty-icon">${icon}</div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(desc)}</p>${action}</div>`}
function kpi(title,value,icon,subtitle,cls=''){return `<div class="kpi"><div class="kpi-top"><span>${title}</span><span class="kpi-symbol">${icon}</span></div><div class="kpi-value ${cls}">${value}</div><div class="kpi-sub">${subtitle}</div></div>`}
function hrefButton(text,action){return `<button class="panel-link" type="button" data-action="${escapeHtml(action)}">${text} ↗</button>`}
function isVisible(){return !!app.user}

function showAuth(mode){
 document.body.classList.add('auth-active');
 app.authMode=mode;toggle('#auth-view',true);toggle('#workspace',false);
 const meta={
  login:['Welcome back','Sign in to manage your personal ticket portfolio.','Sign in →'],
  register:['Create your account','Start your private ticket workspace. Your data belongs only to you.','Create my account →'],
  forgot:['Recover your account','Enter your email to request a password reset link.','Send recovery link →'],
  reset:['Set a new password','Choose a strong password to secure your personal workspace.','Update password →']
 }[mode]||['Welcome back','Sign in to continue.','Sign in →'];
 $('#auth-title').textContent=meta[0];$('#auth-description').textContent=meta[1];$('#auth-submit').innerHTML=meta[2];
 toggle('#auth-name-row',mode==='register');toggle('#auth-email-row',mode!=='reset');toggle('#auth-password-row',mode!=='forgot');
 $('#auth-email').required=mode!=='reset';$('#auth-name').required=mode==='register';$('#auth-password').required=mode!=='forgot';
 $('#forgot-link').classList.toggle('hidden',mode!=='login');
 toggle('#auth-google',app.google&&(mode==='login'||mode==='register'));
 $('#google-button').innerHTML=`<span class="google-symbol">G</span> ${mode==='register'?'Sign up with Google':'Continue with Google'} <span>↗</span>`;
 $('#auth-switch').innerHTML=mode==='login'?'New to Ceyrl? <button type="button" id="switch-auth">Create an account</button>':
  'Already have an account? <button type="button" id="switch-auth">Back to sign in</button>';
 $('#switch-auth').addEventListener('click',()=>showAuth(mode==='login'?'register':'login'));
 $('#auth-password').setAttribute('autocomplete',mode==='login'?'current-password':'new-password');
 toggle('#auth-errors',false);toggle('#auth-note',false);
}
function authError(message,good=false){const el=$(good?'#auth-note':'#auth-errors');el.textContent=message;el.classList.remove('hidden')}
async function authSubmit(e){
 e.preventDefault();toggle('#auth-errors',false);toggle('#auth-note',false);
 const email=$('#auth-email').value.trim(),password=$('#auth-password').value,name=$('#auth-name').value.trim();
 const button=$('#auth-submit');button.disabled=true;
 try{
  if(app.authMode==='login'){
   const response=await api('/auth/login',{method:'POST',body:{email,password}});
   app.csrf=response.csrf;await loadAuthState();notify('Welcome back. Your private workspace is ready.');
  }else if(app.authMode==='register'){
   const response=await api('/auth/register',{method:'POST',body:{name,email,password}});
   if(response.dev_verification_token){await api('/auth/verify',{method:'POST',body:{token:response.dev_verification_token}});showAuth('login');authError('Development account verified. Please sign in.',true)}
   else authError(response.message||'Check your inbox to verify your email.',true);
  }else if(app.authMode==='forgot'){
   const response=await api('/auth/forgot',{method:'POST',body:{email}});authError(response.message||'If eligible, a recovery email has been sent.',true);
  }else if(app.authMode==='reset'){
   const token=new URLSearchParams(location.search).get('reset')||'';
   await api('/auth/reset',{method:'POST',body:{token,password}});history.replaceState(null,'',location.pathname);showAuth('login');authError('Password reset. Sign in with your new password.',true);
  }
 }catch(err){authError(err.message)}finally{button.disabled=false}
}
async function loadAuthState(){
 const data=await api('/auth/state');app.google=!!data.google_enabled;app.email=!!data.email_enabled;
 if(data.authenticated){app.user=data.user;app.csrf=data.csrf;showWorkspace();return}
 app.user=null;app.csrf='';const q=new URLSearchParams(location.search);
 if(q.has('verify')){
  try{await api('/auth/verify',{method:'POST',body:{token:q.get('verify')}});history.replaceState(null,'',location.pathname);showAuth('login');authError('Email verified. Welcome! You can now sign in.',true)}
  catch(err){history.replaceState(null,'',location.pathname);showAuth('login');authError(err.message)}
 }else if(q.has('reset'))showAuth('reset');
 else if(q.has('google_error')){showAuth('login');authError('Google login could not finish ('+q.get('google_error')+'). Check your account and try again.');history.replaceState(null,'',location.pathname)}
 else showAuth('login');
 if(q.has('google')&&!q.has('google_error')){notify('Google account connected successfully.');history.replaceState(null,'',location.pathname+location.hash)}
}
function showWorkspace(){document.body.classList.remove('auth-active');toggle('#auth-view',false);toggle('#workspace',true);const name=app.user.display_name||app.user.email;
 $('#workspace-name').textContent='My Personal Space';$('#sidebar-username').textContent=name;$('#sidebar-email').textContent=app.user.email;
 const initial=name.charAt(0).toUpperCase();$('#sidebar-avatar').textContent=initial;$('#top-avatar').textContent=initial;$('#workspace-initial').textContent=initial;
 drawNav();navigate((location.hash||'#overview').slice(1));
}
function drawNav(){$('#sidebar-nav').innerHTML=SECTIONS.map(g=>`<div class="nav-group">${g.name}</div>${g.items.map(([id,icon,label])=>`<button type="button" data-page="${id}" class="nav-item ${id===app.page?'active':''}"><span class="nav-icon">${icon}</span>${label}</button>`).join('')}`).join('')}
function navigate(page){
 const entry=SECTIONS.flatMap(x=>x.items).find(x=>x[0]===page)||SECTIONS[0].items[0];app.page=entry[0];
 $('#crumb-current').textContent=entry[2];$('#sidebar').classList.remove('open');toggle('#mobile-scrim',false);
 $('#sidebar-nav').querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===app.page));
 history.replaceState(null,'','#'+app.page);window.scrollTo(0,0);renderPage().catch(notifyError);
}
async function loadAll(){const data=await Promise.all([api('/events'),api('/tickets'),api('/listings'),api('/sales'),api('/expenses'),api('/recaps')]);
 [app.events,app.tickets,app.listings,app.sales,app.expenses,app.recaps]=data;}
async function renderPage(){
 if(!app.user)return;$('#page-content').innerHTML='<div class="loading">Loading your private workspace…</div>';
 switch(app.page){
  case'overview':return renderOverview();
  case'actions':return renderV6Actions();
  case'events':return renderEvents();
  case'tickets':return renderTickets();
  case'listings':return renderListings();
  case'sales':return renderSales();
  case'expenses':return renderExpenses();
  case'analytics':return renderAnalytics();
  case'activity':return renderActivity();
  case'settings':return renderSettings();
 }
}
function chart(series){
 if(!series?.length)return '<div class="chart-message">Your revenue timeline will appear once you record a sale.</div>';
 const max=Math.max(1,...series.map(x=>x.revenue_cents));const w=690,h=200,base=183;
 const pts=series.map((e,i)=>({x:20+i*(w-38)/Math.max(1,series.length-1),y:base-e.revenue_cents/max*145,label:e.day,value:e.revenue_cents}));
 const path=pts.map((p,i)=>(i?'L':'M')+p.x.toFixed(1)+' '+p.y.toFixed(1)).join(' ');
 const fill=path+' L '+pts.at(-1).x.toFixed(1)+' '+base+' L '+pts[0].x.toFixed(1)+' '+base+' Z';
 return `<div class="chart-box"><svg viewBox="0 0 700 230" role="img" aria-label="Revenue trend chart" preserveAspectRatio="none"><defs><linearGradient id="chartShade" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#8e86fb" stop-opacity=".38"/><stop offset="100%" stop-color="#8e86fb" stop-opacity="0"/></linearGradient></defs>${[45,90,135,180].map(y=>`<line class="chart-gridline" x1="18" y1="${y}" x2="684" y2="${y}"/>`).join('')}<path class="chart-fill" d="${fill}"/><path class="chart-line" d="${path}"/>${pts.map(p=>`<circle class="chart-point" cx="${p.x}" cy="${p.y}" r="4"><title>${escapeHtml(p.label)}: ${money(p.value)}</title></circle>`).join('')}<text class="chart-lbl" x="20" y="218">${escapeHtml(series[0].day)}</text><text class="chart-lbl" x="590" y="218">${escapeHtml(series.at(-1).day)}</text></svg></div>`;
}
async function renderOverview(){
 const [d,events]=await Promise.all([api('/dashboard'),api('/events')]);app.dashboard=d;app.events=events;
 const e=events.filter(x=>new Date(x.starts_at)>new Date()).slice(0,5);
 $('#page-content').innerHTML=heading('Workspace Overview','A real-time snapshot of your tickets, events and sales — visible only to you.',button('+ Add tickets','new-ticket')+button('New event ↗','new-event','outline'))+
 `<section class="hero-panel"><div><span class="hero-kicker">✦ YOUR TICKET OPERATIONS, SIMPLIFIED</span><h2>Good to see you, ${escapeHtml(app.user.display_name.split(' ')[0])}.</h2><p>Every ticket, every sale and every PDF belongs to your account. Track your inventory and results with complete clarity.</p></div><div class="hero-actions">${button('Add a ticket','new-ticket','white')}${button('View analytics ↗','go-analytics','outline')}</div></section>`+
 `<div class="kpi-grid">${kpi('Net profit',money(d.profit_cents),'↗','Realized profit in EUR',d.profit_cents>=0?'positive':'negative')}${kpi('Sales revenue',money(d.revenue_cents),'€','Recorded EUR sales')}${kpi('Available tickets',num(d.available),'◈','Remaining individual seats')}${kpi('Tickets sold',num(d.sold),'▣','Across all your events')}</div>`+
 `<div class="two-cols">${card('Revenue performance','EUR revenue recorded over the most recent sale dates',chart(d.revenue_trend),hrefButton('Sales details','go-sales'))}${card('Portfolio at a glance','Your personal event and ticket inventory',`<div class="panel-body">${[['My events',num(d.events)],['Ticket lots',num(d.tickets)],['Encrypted PDF files',num(d.attachments)],['Local listings',num(d.listings)],['Individual sales',num(d.sales)]].map(([l,v])=>`<div class="summary-row"><span>${l}</span><strong>${v}</strong></div>`).join('')}</div>`)}</div>`+
 `<div class="two-cols">${card('Your upcoming events','Next scheduled events in your private calendar',e.length?`<div class="table-wrap">${table(['Event','Date','Tickets'],e.map(v=>`<tr><td><span class="table-strong">${escapeHtml(v.title)}</span><span class="table-sub">${escapeHtml(v.venue||v.city||'Location not specified')}</span></td><td>${niceDate(v.starts_at)}</td><td>${num(v.available)} available</td></tr>`))}</div>`:empty('▤','No upcoming events','Create an event to organize your first batch of tickets.',button('Create event','new-event')) ,hrefButton('All events','go-events'))}${card('Recent sales','Your latest completed sale records',d.recent_sales.length?table(['Event','Tickets','Revenue'],d.recent_sales.map(s=>`<tr><td><span class="table-strong">${escapeHtml(s.event_title)}</span><span class="table-sub">${niceDate(s.sold_at)}</span></td><td>${s.quantity}</td><td><strong class="positive">${money(s.revenue_cents,s.currency)}</strong></td></tr>`)):empty('↗','No sales recorded','Record a sale to see your actual profits.',button('Record sale','new-sale')),hrefButton('Sales tracker','go-sales'))}</div>`;
 await decorateV6Overview();
}
function formOptions(data,placeholder='Choose an option'){return [{value:'',label:placeholder},...data]}
function eventOptions(){return formOptions(app.events.map(e=>({value:e.id,label:e.title+' · '+niceDate(e.starts_at)})),'Select an event')}
function ticketOptions(){return formOptions(app.tickets.filter(t=>t.quantity>t.sold_quantity).map(t=>({value:t.id,label:'#'+t.id+' '+t.event_title+' · '+(t.section||'General')+' ('+(t.quantity-t.sold_quantity)+' left)'})),'Select a ticket lot')}
async function renderEvents(){app.events=await api('/events');const rows=app.events;
 $('#page-content').innerHTML=heading('My Events','Your upcoming concerts, sports and live events in one private calendar.',button('+ Create Event','new-event'))+
 `<div class="stats-strip"><span class="stat-chip"><strong>${num(rows.length)}</strong> events</span><span class="stat-chip"><strong>${num(rows.reduce((s,e)=>s+e.available,0))}</strong> available tickets</span><span class="stat-chip">Your private collection</span></div>`+
 (rows.length?`<div class="event-cards" style="margin-top:20px">${rows.map(e=>`<article class="event-card"><div class="event-type">◆ ${escapeHtml(e.category||'EVENT')}</div><h3>${escapeHtml(e.title)}</h3><p>▤ ${niceDate(e.starts_at)}</p><p>⌾ ${escapeHtml([e.venue,e.city].filter(Boolean).join(' · ')||'Venue not specified')}</p><div class="event-bottom"><span>${num(e.lots)} ticket lots · ${num(e.available)} remaining</span><button class="mini-btn" data-action="edit-event" data-id="${e.id}">Edit ↗</button></div></article>`).join('')}</div>`:empty('▤','Your event calendar is empty','Create your first event to start organizing tickets.',button('Create first event','new-event')));
}
async function renderTickets(){await Promise.all([api('/tickets').then(x=>app.tickets=x),api('/events').then(x=>app.events=x)]);app.search=app.search||'';
 $('#page-content').innerHTML=heading('Ticket Inventory','All of your ticket lots, seats and PDFs — private and fully accounted for.',button('+ Add Tickets','new-ticket'))+
 `<div class="kpi-grid">${kpi('Ticket lots',num(app.tickets.length),'▧','Stored in your account')}${kpi('Available seats',num(app.tickets.reduce((n,t)=>n+t.quantity-t.sold_quantity,0)),'◈','Ready for your next sale')}${kpi('Sold tickets',num(app.tickets.reduce((n,t)=>n+t.sold_quantity,0)),'↗','Units marked as sold')}${kpi('PDF attachments',num(app.tickets.reduce((n,t)=>n+t.pdf_count,0)),'▤','Encrypted in your vault')}</div>`+
 `<div class="filters"><input class="filter-input" id="ticket-filter" type="search" placeholder="Search event, sector, seat, source…" value="${escapeHtml(app.search)}"><select class="filter-select" id="ticket-status"><option value="all">All inventory</option><option value="available">Available</option><option value="sold">Sold out</option></select></div>`+
 card('My ticket lots','Every lot is visible to your account only',`<div id="ticket-table">${ticketTable(app.tickets)}</div>`);
 $('#ticket-filter').addEventListener('input',renderFilteredTickets);$('#ticket-status').addEventListener('change',renderFilteredTickets);
}
function renderFilteredTickets(){app.search=$('#ticket-filter').value;let rows=app.tickets;
 const q=app.search.trim().toLowerCase();const filter=$('#ticket-status').value;
 if(q)rows=rows.filter(t=>[t.event_title,t.section,t.row_label,t.seats,t.provider].join(' ').toLowerCase().includes(q));
 if(filter==='available')rows=rows.filter(t=>t.sold_quantity<t.quantity);
 if(filter==='sold')rows=rows.filter(t=>t.sold_quantity===t.quantity);
 $('#ticket-table').innerHTML=ticketTable(rows);
}
function ticketTable(rows){return table(['Event / Lot','Section / Seat','Inventory','Cost / ticket','PDF vault','Actions'],rows.map(t=>`<tr><td><div class="row-title"><span class="circle-icon">▣</span><div><span class="table-strong">${escapeHtml(t.event_title)}</span><span class="table-sub">#${t.id} · ${niceDate(t.starts_at)} · ${escapeHtml(t.provider||'Direct')}</span></div></div></td><td><span class="table-strong">${escapeHtml(t.section||'General admission')}</span><span class="table-sub">Row ${escapeHtml(t.row_label||'—')} · Seat ${escapeHtml(t.seats||'—')}</span></td><td>${statusTag(t.quantity>t.sold_quantity?'Available':'Sold out')}<span class="table-sub">${t.quantity-t.sold_quantity} / ${t.quantity} left</span></td><td>${money(t.purchase_cents,t.currency)}</td><td>${t.pdf_count?'🔒 '+t.pdf_count+' PDF(s)':'No PDF'}</td><td><button class="mini-btn" data-action="manage-pdf" data-id="${t.id}">PDF Vault</button><button class="mini-btn" data-action="sale-ticket" data-id="${t.id}">Sell ↗</button></td></tr>`),'No matching tickets found')}
async function renderListings(){await Promise.all([api('/listings').then(x=>app.listings=x),api('/tickets').then(x=>app.tickets=x)]);
 $('#page-content').innerHTML=heading('My Listings','Create and track marketplace listings without losing control of your inventory.',button('+ New listing','new-listing'))+
 `<div class="section-note"><strong>Marketplace status:</strong> Listings are stored locally in your personal account. Viagogo publication is not active until an authorized seller integration is approved.</div>`+
 card('Listing manager',`${app.listings.length} listings in your private database`,table(['Event / Ticket','Marketplace','Asking price','Status','ID','Actions'],app.listings.map(l=>`<tr><td><span class="table-strong">${escapeHtml(l.event_title)}</span><span class="table-sub">${escapeHtml(l.section||'General')} · Lot #${l.ticket_id}</span></td><td>${escapeHtml(l.marketplace)}</td><td>${money(l.price_cents,l.currency)}</td><td>${statusTag(l.status)}</td><td>${escapeHtml(l.external_id||'—')}</td><td><button class="mini-btn" data-action="edit-listing" data-id="${l.id}">Manage</button></td></tr>`),'No listings in your account'));
}
async function renderSales(){await Promise.all([api('/sales').then(x=>app.sales=x),api('/tickets').then(x=>app.tickets=x)]);
 const rev=app.sales.filter(x=>x.currency==='EUR').reduce((s,x)=>s+x.revenue_cents,0);
 $('#page-content').innerHTML=heading('Sales Tracker','Track actual sales, marketplace fees and delivery references.',button('+ Record Sale','new-sale'))+
 `<div class="kpi-grid">${kpi('Recorded sales',num(app.sales.length),'↗','Transactions in your account')}${kpi('Tickets sold',num(app.sales.reduce((s,x)=>s+x.quantity,0)),'▣','Individual ticket units')}${kpi('EUR revenue',money(rev),'€','Excludes other currencies')}${kpi('EUR fees',money(app.sales.filter(x=>x.currency==='EUR').reduce((s,x)=>s+x.fee_cents,0)),'◈','Recorded marketplace fees')}</div>`+
 card('Sales ledger','All sales are private and update your available ticket quantities',table(['Event','Sale date','Units','Revenue','Fees','Channel','Reference'],app.sales.map(s=>`<tr><td><span class="table-strong">${escapeHtml(s.event_title)}</span><span class="table-sub">${escapeHtml(s.section||'General')}</span></td><td>${niceDate(s.sold_at)}</td><td>${num(s.quantity)}</td><td><strong class="positive">${money(s.revenue_cents,s.currency)}</strong></td><td>${money(s.fee_cents,s.currency)}</td><td>${escapeHtml(s.channel)}</td><td>${escapeHtml(s.reference||'—')}</td></tr>`),'No sales yet'));
}
async function renderExpenses(){await Promise.all([api('/expenses').then(x=>app.expenses=x),api('/events').then(x=>app.events=x)]);
 $('#page-content').innerHTML=heading('Expenses & Costs','Understand the operating costs behind your ticket portfolio.',button('+ Add Expense','new-expense'))+
 `<div class="stats-strip"><span class="stat-chip"><strong>${num(app.expenses.length)}</strong> entries</span><span class="stat-chip"><strong>${money(app.expenses.filter(x=>x.currency==='EUR').reduce((s,x)=>s+x.amount_cents,0))}</strong> EUR expenses</span></div><div style="height:18px"></div>`+
 card('Expense ledger','Costs can be connected to a specific event or recorded as general expenses',table(['Description','Event','Amount','Date'],app.expenses.map(x=>`<tr><td><span class="table-strong">${escapeHtml(x.title)}</span></td><td>${escapeHtml(x.event_title||'General / no event')}</td><td>${money(x.amount_cents,x.currency)}</td><td>${niceDate(x.created_at)}</td></tr>`),'No expenses recorded'));
}
async function renderAnalytics(){app.recaps=await api('/recaps');const totals=app.recaps.reduce((r,x)=>({profit:r.profit+x.profit_cents,revenue:r.revenue+x.revenue_cents,sold:r.sold+x.sold}),{profit:0,revenue:0,sold:0});
 $('#page-content').innerHTML=heading('Portfolio Analytics','Accurate event-by-event performance from your recorded transactions.',button('Export sales CSV','export-sales','outline'))+
 `<div class="kpi-grid">${kpi('Net profit',money(totals.profit),'↗','EUR after recorded costs',totals.profit>=0?'positive':'negative')}${kpi('Gross revenue',money(totals.revenue),'€','EUR only')}${kpi('Tickets sold',num(totals.sold),'▣','Across all events')}${kpi('Analyzed events',num(app.recaps.length),'▤','Private event histories')}</div>`+
 `<div class="section-note"><strong>Financial transparency:</strong> Net profit = EUR sales revenue − marketplace fees − cost of sold tickets − related EUR expenses. Other currencies are excluded until converted explicitly; ROI is based on cost of sold tickets and event expenses.</div>`+
 card('Event profitability','A readable report with a clear calculation for every event',table(['Event','Sold / Available','Revenue','Ticket cost','Fees + expenses','Net profit','ROI'],app.recaps.map(r=>`<tr><td><span class="table-strong">${escapeHtml(r.title)}</span><span class="table-sub">${escapeHtml(r.city)} · ${niceDate(r.starts_at)}${r.has_non_eur?' · other currencies excluded':''}</span></td><td>${num(r.sold)} / ${num(r.available)}</td><td>${money(r.revenue_cents)}</td><td>${money(r.sold_cost_cents)}</td><td>${money(r.fee_cents+r.expenses_cents)}</td><td><strong class="${r.profit_cents>=0?'positive':'negative'}">${money(r.profit_cents)}</strong></td><td>${r.roi_percent===null?'—':(r.roi_percent>0?'+':'')+r.roi_percent.toFixed(1)+'%'}</td></tr>`),'No sale analytics yet'));
}
async function renderActivity(){const rows=await api('/audit');$('#page-content').innerHTML=heading('Activity Log','A private history of updates and changes to your own records.')+
 card('My recent activity','Action history stays inside your personal database',table(['Date','Action','Record type','ID'],rows.map(r=>`<tr><td>${niceDate(r.created_at)}</td><td>${statusTag(r.action)}</td><td>${escapeHtml(r.resource)}</td><td>#${r.resource_id}</td></tr>`),'No activity yet'));
}
async function renderSettings(){const me=await api('/me');const google=app.google;
 $('#page-content').innerHTML=heading('My Account','Manage your personal login, identity and data exports.')+
 `<div class="two-cols">${card('Your identity','This workspace belongs only to your own login',`<div class="profile-card"><div class="profile-avatar">${escapeHtml(me.name[0]?.toUpperCase()||'C')}</div><div><h3>${escapeHtml(me.name)}</h3><p>${escapeHtml(me.email)}</p><span class="tag green">● Private account</span></div></div><div class="panel-body"><div class="secure-row"><div><strong>Personal database</strong><small>Separate inventory and event records</small></div><span class="tag green">Isolated</span></div><div class="secure-row"><div><strong>PDF encryption</strong><small>Private encrypted vault stored per account</small></div><span class="tag green">Active</span></div><div class="secure-row"><div><strong>Google sign-in</strong><small>${me.has_google?'Connected to this account':'Not connected'}</small></div>${me.has_google?'<span class="tag green">Connected</span>':google?button('Connect Google','connect-google','outline'):'<span class="tag grey">Not set up</span>'}</div></div>`)}${card('Account controls','Protect your sign-in and export your records',`<div class="panel-body"><div class="summary-row"><span>My events</span><strong>${num(me.counts.events)}</strong></div><div class="summary-row"><span>Ticket lots</span><strong>${num(me.counts.tickets)}</strong></div><div class="summary-row"><span>Encrypted PDF files</span><strong>${num(me.counts.attachments)}</strong></div><div class="summary-row"><span>Sales</span><strong>${num(me.counts.sales)}</strong></div><div style="margin-top:19px;display:flex;flex-wrap:wrap;gap:10px">${button('Change password','change-password','subtle')}${button('Log out','sign-out','outline')}</div></div>`)}</div>`+
 card('Your private data','Download a CSV copy of your own records',`<div class="panel-body"><div class="section-note">PDF files are encrypted and cannot be accessed by other accounts. Back up the entire server data directory, including per-user encryption keys, through your hosting provider.</div><div class="heading-actions">${['events','tickets','listings','sales','expenses'].map(x=>button('Export '+x,'export-'+x,'outline')).join('')}</div></div>`);
}
/* Input forms */
function control({name,label,type='text',required=false,value='',placeholder='',options=[],wide=false,help='',min,max,step}){
 const id='input-'+name,attrs=(required?' required':'')+(min!==undefined?` min="${min}"`:'')+(max!==undefined?` max="${max}"`:'')+(step!==undefined?` step="${step}"`:'');
 let element;
 if(type==='select')element=`<select name="${name}" id="${id}" ${attrs}>${options.map(o=>`<option value="${escapeHtml(o.value)}" ${String(o.value)===String(value)?'selected':''}>${escapeHtml(o.label)}</option>`).join('')}</select>`;
 else if(type==='textarea')element=`<textarea id="${id}" name="${name}" ${attrs} placeholder="${escapeHtml(placeholder)}">${escapeHtml(value)}</textarea>`;
 else element=`<input id="${id}" type="${type}" name="${name}" value="${escapeHtml(value)}" placeholder="${escapeHtml(placeholder)}" ${attrs}>`;
 return `<div class="field ${wide?'full':''}"><label for="${id}">${escapeHtml(label)}</label>${element}${help?`<small>${escapeHtml(help)}</small>`:''}</div>`;
}
function openModal(title,fields,callback,buttonLabel='Save changes'){
 $('#modal-title').textContent=title;$('#modal-fields').innerHTML=fields.map(control).join('');$('#modal-save').textContent=buttonLabel;
 toggle('#modal-backdrop',true);
 $('#modal-form').onsubmit=async e=>{
  e.preventDefault();const submit=$('#modal-save');submit.disabled=true;
  const values=Object.fromEntries(new FormData(e.target).entries());
  try{await callback(values);closeModal();await renderPage()}catch(err){notifyError(err)}finally{submit.disabled=false}
 };
 $('#modal-fields').querySelector('input,select,textarea')?.focus();
}
function closeModal(){toggle('#modal-backdrop',false);$('#modal-form').onsubmit=null}
const COMMON_CURRENCIES=['EUR','CZK','USD','GBP','PLN','CHF'].map(x=>({value:x,label:x}));
async function newEvent(existing=null){
 openModal(existing?'Edit event':'Create a new event',[
  {name:'title',label:'Event / artist name',value:existing?.title||'',required:true,wide:true,placeholder:'Example: Coldplay — Music of the Spheres'},
  {name:'starts_at',label:'Event date & time',type:'datetime-local',value:existing?inputDateFromUTC(existing.starts_at):inputDate(30),required:true},
  {name:'category',label:'Event category',type:'select',value:existing?.category||'Concert',options:['Concert','Sports','Festival','Theatre','Other'].map(v=>({value:v,label:v}))},
  {name:'venue',label:'Venue',value:existing?.venue||'',placeholder:'Example: O2 Arena'},
  {name:'city',label:'City',value:existing?.city||'',placeholder:'Example: Prague'},
  {name:'country',label:'Country',value:existing?.country||'',placeholder:'Example: Czechia'},
  {name:'notes',label:'Internal notes',type:'textarea',value:existing?.notes||'',wide:true}
 ],async v=>{
  v.starts_at=isoLocal(v.starts_at);
  await api(existing?'/events/'+existing.id:'/events',{method:existing?'PATCH':'POST',body:v});notify(existing?'Event updated':'Event created in your private account');
 },existing?'Update event':'Create event');
}
function inputDateFromUTC(v){const d=new Date(v);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
async function newTicket(){app.events=await api('/events');if(!app.events.length){notify('Create an event before adding tickets.');navigate('events');return newEvent()}
 openModal('Add tickets to inventory',[
  {name:'event_id',label:'Event',type:'select',options:eventOptions(),required:true,wide:true},
  {name:'provider',label:'Ticket provider',placeholder:'Ticketmaster, AXS, Eventim…'},
  {name:'ticket_type',label:'Ticket format',type:'select',options:['E-Ticket','Mobile Transfer','PDF','Physical'].map(x=>({label:x,value:x}))},
  {name:'section',label:'Section',placeholder:'Example: 421'},
  {name:'row_label',label:'Row',placeholder:'Example: 15'},
  {name:'seats',label:'Seats',placeholder:'Example: 3–6'},
  {name:'quantity',label:'Quantity of tickets',type:'number',min:1,max:1000,required:true,value:1},
  {name:'purchase_price',label:'Purchase price per ticket',type:'number',step:'.01',min:0,required:true,value:0},
  {name:'currency',label:'Purchase currency',type:'select',options:COMMON_CURRENCIES},
  {name:'notes',label:'Private notes',type:'textarea',wide:true,placeholder:'Transfer instructions or ticket conditions (no passwords or OTPs)'}
 ],async v=>{
  if(!v.event_id)throw Error('Please select an event.');v.event_id=Number(v.event_id);v.quantity=Number(v.quantity);
  const result=await api('/tickets',{method:'POST',body:v});notify('Ticket lot saved. You can now attach PDFs.');navigate('tickets');return result;
 },'Save ticket lot');
}
async function newListing(existing=null){app.tickets=await api('/tickets');const options=ticketOptions();if(!existing&&options.length<=1){notify('Add available tickets before creating a listing.');return}
 openModal(existing?'Edit your listing':'Create a local listing',[
  {name:'ticket_id',label:'Ticket lot',type:'select',options:existing?[{value:existing.ticket_id,label:existing.event_title+' · Lot #'+existing.ticket_id}]:options,required:true,wide:true},
  {name:'marketplace',label:'Marketplace',value:existing?.marketplace||'viagogo',placeholder:'viagogo, TicketSwap, StubHub…'},
  {name:'external_id',label:'External listing ID',value:existing?.external_id||'',placeholder:'Optional'},
  {name:'price',label:'Asking price per ticket',type:'number',min:0,step:'.01',value:existing?(existing.price_cents/100).toFixed(2):'0',required:true},
  {name:'currency',label:'Currency',type:'select',value:existing?.currency||'EUR',options:COMMON_CURRENCIES},
  {name:'status',label:'Status',type:'select',value:existing?.status||'draft',options:['draft','ready','listed','paused','sold','cancelled'].map(x=>({value:x,label:x}))},
  {name:'notes',label:'Private notes',type:'textarea',value:existing?.notes||'',wide:true}
 ],async v=>{if(!v.ticket_id)throw Error('Choose a ticket lot.');v.ticket_id=Number(v.ticket_id);
 await api(existing?'/listings/'+existing.id:'/listings',{method:existing?'PATCH':'POST',body:v});notify('Listing saved privately (not published to a marketplace).');
 },existing?'Update listing':'Save local listing');
}
async function newSale(prefill=null){app.tickets=await api('/tickets');const opts=ticketOptions();if(opts.length<=1){notify('No available tickets to sell.');return}
 openModal('Record a completed sale',[
  {name:'ticket_id',label:'Ticket lot',type:'select',value:prefill||'',options:opts,wide:true,required:true},
  {name:'quantity',label:'Tickets sold',type:'number',min:1,max:1000,value:1,required:true},
  {name:'sold_at',label:'Sale date',type:'datetime-local',value:inputDate(),required:true},
  {name:'revenue',label:'Total sale revenue',type:'number',min:0,step:'.01',value:'0',required:true},
  {name:'fees',label:'Total marketplace fees',type:'number',min:0,step:'.01',value:'0'},
  {name:'currency',label:'Currency',type:'select',options:COMMON_CURRENCIES},
  {name:'channel',label:'Sales channel',placeholder:'viagogo, TicketSwap…',value:'Direct'},
  {name:'reference',label:'Order reference',placeholder:'Optional order ID'}
 ],async v=>{
  if(!v.ticket_id)throw Error('Choose a ticket lot.');v.ticket_id=Number(v.ticket_id);v.quantity=Number(v.quantity);v.sold_at=isoLocal(v.sold_at);
  await api('/sales',{method:'POST',body:v});notify('Sale recorded. Available ticket quantity updated.');
 },'Record sale');
}
async function newExpense(){app.events=await api('/events');
 openModal('Record a new expense',[
  {name:'title',label:'Expense description',placeholder:'Hosting, delivery, service fee…',required:true,wide:true},
  {name:'event_id',label:'Associated event',type:'select',options:[{value:'',label:'General expense / no specific event'},...eventOptions().slice(1)]},
  {name:'amount',label:'Total expense',type:'number',step:'.01',min:0,value:0,required:true},
  {name:'currency',label:'Currency',type:'select',options:COMMON_CURRENCIES}
 ],async v=>{v.event_id=v.event_id?Number(v.event_id):null;await api('/expenses',{method:'POST',body:v});notify('Expense recorded.');},'Save expense');
}
async function managePdf(ticketId){
 const list=await api('/tickets/'+ticketId+'/pdfs');
 $('#modal-title').textContent='Encrypted PDF Vault · Ticket #'+ticketId;
 $('#modal-fields').innerHTML=`<div class="field full"><div class="file-drop">♧ &nbsp; Upload a ticket PDF (max 20 MB)<input id="upload-pdf-input" accept="application/pdf,.pdf" type="file"><small>Files are encrypted and available only to your own account.</small></div></div><div class="field full"><strong>Saved attachments</strong>${list.length?list.map(a=>`<div class="secure-row"><div><strong>${escapeHtml(a.filename)}</strong><small>${Math.round(a.size/1024)} KB · ${niceDate(a.created_at)}</small></div><button class="mini-btn" type="button" data-pdf-download="${a.id}">Download ↗</button></div>`).join(''):'<p style="color:#92a2be">No documents attached yet.</p>'}</div>`;
 $('#modal-save').textContent='Upload PDF';toggle('#modal-backdrop',true);
 $('#modal-fields').querySelectorAll('[data-pdf-download]').forEach(el=>el.addEventListener('click',()=>window.open('/api/tickets/'+ticketId+'/pdfs/'+el.dataset.pdfDownload,'_blank','noopener,noreferrer')));
 $('#modal-form').onsubmit=async e=>{
  e.preventDefault();const file=$('#upload-pdf-input').files?.[0];if(!file){notify('Choose a PDF first.');return}
  const form=new FormData();form.append('file',file);const save=$('#modal-save');save.disabled=true;
  try{await api('/tickets/'+ticketId+'/pdf',{method:'POST',body:form});notify('PDF encrypted and saved.');closeModal();navigate('tickets')}
  catch(err){notifyError(err)}finally{save.disabled=false}
 };
}
async function changePassword(){openModal('Change account password',[
 {name:'current_password',label:'Current password',type:'password',wide:true,placeholder:'Leave blank if you registered using Google'},
 {name:'new_password',label:'New password (12+ characters including letters & numbers)',type:'password',wide:true,required:true}
 ],async v=>{await api('/me/password',{method:'POST',body:v});notify('Password updated. Other sessions were revoked.');},'Update password')}
async function changeName(){const me=await api('/me');openModal('Update your profile',[
 {name:'name',label:'Display name',required:true,wide:true,value:me.name}
 ],async v=>{await api('/me',{method:'PATCH',body:v});await loadAuthState();notify('Profile updated.');},'Save profile')}
function dispatchAction(action,id){
 if(action==='new-event')return newEvent();
 if(action==='edit-event')return api('/events/'+id).then(newEvent);
 if(action==='new-ticket')return newTicket();
 if(action==='new-listing')return newListing();
 if(action==='edit-listing')return newListing(app.listings.find(x=>x.id===Number(id)));
 if(action==='new-sale')return newSale();
 if(action==='sale-ticket')return newSale(Number(id));
 if(action==='new-expense')return newExpense();
 if(action==='manage-pdf')return managePdf(Number(id));
 if(action==='go-analytics')return navigate('analytics');
 if(action==='go-sales')return navigate('sales');
 if(action==='go-events')return navigate('events');
 if(action==='change-password')return changePassword();
 if(action==='edit-profile')return changeName();
 if(action==='connect-google')return window.location.assign('/api/auth/google/start?mode=link');
 if(action==='sign-out')return signOut();
 if(action.startsWith('export-'))return window.open('/api/export/'+action.slice(7)+'.csv','_blank','noopener,noreferrer');
}
async function signOut(){try{await api('/auth/logout',{method:'POST'});app.user=null;app.csrf='';showAuth('login');notify('Signed out safely.')}catch(err){notifyError(err)}}
function toggleSidebar(){const open=$('#sidebar').classList.toggle('open');toggle('#mobile-scrim',open)}
$('#menu-toggle').addEventListener('click',toggleSidebar);$('#mobile-scrim').addEventListener('click',toggleSidebar);
$('#sidebar-nav').addEventListener('click',e=>{const btn=e.target.closest('[data-page]');if(btn)navigate(btn.dataset.page)});
$('#page-content').addEventListener('click',async e=>{const btn=e.target.closest('[data-action]');if(!btn)return;try{await dispatchAction(btn.dataset.action,btn.dataset.id)}catch(err){notifyError(err)}});
$('#sidebar-account').addEventListener('click',()=>navigate('settings'));$('#top-avatar').addEventListener('click',()=>navigate('settings'));
$('#auth-form').addEventListener('submit',authSubmit);$('#password-toggle').addEventListener('click',()=>{$('#auth-password').type=$('#auth-password').type==='password'?'text':'password'});
$('#forgot-link').addEventListener('click',()=>showAuth('forgot'));
$('#google-button').addEventListener('click',()=>window.location.assign('/api/auth/google/start'));
$('#modal-close').addEventListener('click',closeModal);$('#modal-cancel').addEventListener('click',closeModal);
$('#modal-backdrop').addEventListener('click',e=>{if(e.target===e.currentTarget)closeModal()});
$('#global-search').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();openCeyrlSearch()}});
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#modal-backdrop').classList.contains('hidden'))closeModal()});
// Motion is purely visual: no effect on account data or any backend request.
(function initializeCeyrlMotion(){
  const control=$('#motion-toggle');
  if(!control)return;
  const systemPrefersStill=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches||false;
  let saved=null;
  try { saved=localStorage.getItem('ceyrl-ambient-motion'); } catch(_error) {}
  const setMotion=(isOn)=>{
    const enabled=Boolean(isOn)&&!systemPrefersStill;
    document.body.classList.toggle('motion-off',!enabled);
    control.setAttribute('aria-pressed',String(enabled));
    control.querySelector('span').textContent=enabled?'Motion on':'Motion off';
    control.title=systemPrefersStill?'Motion is disabled by your device accessibility settings.':(enabled?'Pause animated background':'Resume animated background');
    control.disabled=systemPrefersStill;
  };
  setMotion(saved===null?!systemPrefersStill:saved==='on');
  control.addEventListener('click',()=>{
    const on=control.getAttribute('aria-pressed')!=='true';
    setMotion(on);
    try { localStorage.setItem('ceyrl-ambient-motion',on?'on':'off'); } catch(_error) {}
  });
})();
loadAuthState().catch(notifyError);
