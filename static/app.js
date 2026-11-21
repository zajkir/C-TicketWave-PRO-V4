/* C TicketWave PRO — vanilla JS frontend. No CDN, no cookies accessed from JS. */
'use strict';
const $=(s)=>document.querySelector(s);
const safe=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtMoney=(c,code='EUR')=>{try{return new Intl.NumberFormat('en-IE',{style:'currency',currency:code}).format(Number(c||0)/100)}catch(e){return (Number(c||0)/100).toFixed(2)+' '+code}};
const fmtDate=(d)=>d?new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(d)):'—';
const nfmt=(n)=>new Intl.NumberFormat('en-GB').format(n||0);
const escOpt=(v)=>safe(String(v??''));
const statusBadge=(s)=>{const v=String(s||'').trim().toLowerCase();const type=['available','active','sold','listed','enabled'].includes(v)?'green':['reserved','ready','draft','review','pending'].includes(v)?'yellow':['closed','cancelled','disabled','archived'].includes(v)?'red':'blue';return `<span class="tag tag-${type}">● ${safe(s||'—')}</span>`};
const state={user:null,csrf:'',page:'dashboard',dashboard:null,events:[],tickets:[],listings:[],sales:[],expenses:[],members:[],query:'',status:'',inviteToken:null,authMode:'login'};
const groups=[
 {title:'WORKSPACE',items:[['dashboard','overview','Overview'],['events','calendar','Events']]},
 {title:'INVENTORY',items:[['tickets','ticket','Ticket Inventory'],['listings','tag','Listings']]},
 {title:'FINANCIALS',items:[['sales','chart','Sales & Profit'],['expenses','wallet','Expenses']]},
 {title:'ADMINISTRATION',items:[['team','users','Team Members'],['audit','activity','Activity Log'],['account','shield','My Account']]}
];
const icons={
 overview:'<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="5" rx="2"/><rect x="13" y="10" width="8" height="11" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/>',
 calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
 ticket:'<path d="M2 9a3 3 0 0 0 0 6v3a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-3a3 3 0 0 1 0-6V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v3Z"/><path d="M13 5v2m0 3v2m0 3v2m0 3v1"/>',
 tag:'<path d="m20 13-7 7a2 2 0 0 1-3 0l-8-8V3h9l9 8a2 2 0 0 1 0 2Z"/><circle cx="7.5" cy="7.5" r="1"/>',
 chart:'<path d="M3 3v18h18M7 16l5-5 3 3 6-8"/>',
 wallet:'<rect x="2" y="5" width="20" height="16" rx="3"/><path d="M2 9h20M16 14h3"/>',
 users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
 activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
 search:'<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
 arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
 spark:'<path d="m12 3 1.9 6.1L20 11l-6.1 1.9L12 19l-1.9-6.1L4 11l6.1-1.9L12 3Z"/>',
 shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>'
};
function svg(name,size=18){return `<svg class="ui-icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.ticket}</svg>`}
const minRoles={team:2,audit:2};
const can=(role)=>({viewer:0,operator:1,manager:2,admin:3}[state.user?.role]||0)>=({viewer:0,operator:1,manager:2,admin:3}[role]||0);
async function api(path,options={}){
 const opts={credentials:'same-origin',...options};
 if(opts.body && !(opts.body instanceof FormData) && typeof opts.body!=='string')opts.body=JSON.stringify(opts.body);
 if(opts.body && !(opts.body instanceof FormData))opts.headers={'Content-Type':'application/json',...(opts.headers||{})};
 if(opts.method && !['GET','HEAD'].includes(opts.method.toUpperCase()))opts.headers={'X-CSRF-Token':state.csrf,...(opts.headers||{})};
 const r=await fetch('/api'+path,opts);const raw=await r.text();let payload;try{payload=raw?JSON.parse(raw):{}}catch(e){payload={detail:raw||r.statusText}};
 if(!r.ok){if(r.status===401){showAuth('login');state.user=null}throw Error(Array.isArray(payload.detail)?payload.detail.map(x=>x.msg).join('; '):(payload.detail||'Request failed'))}
 return payload;
}
function toast(msg,error=false){const el=document.createElement('div');el.className='toast'+(error?' error':'');el.textContent=msg;$('#toasts').append(el);setTimeout(()=>el.remove(),4800)}
function pageTitle(title,description,actions=''){return `<div class="page-top"><div><div class="eyebrow">C TICKETWAVE / WORKSPACE</div><h1>${title}</h1><p>${description}</p></div><div class="page-actions">${actions}</div></div>`}
function btn(label,act,style='primary'){return `<button class="btn btn-${style}" type="button" data-act="${act}">${label}</button>`}
function panel(title,subtitle,body='',extra='',cls=''){return `<section class="panel ${cls}"><div class="panel-head"><div><h2>${title}</h2><p>${subtitle}</p></div>${extra}</div>${body}</section>`}
function empty(icon,title,desc,button=''){return `<div class="empty"><div class="empty-symbol">${icon}</div><strong>${title}</strong><p>${desc}</p>${button}</div>`}
function table(headers,rows,emptyState){return rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map(s=>`<th>${s}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`:(emptyState||empty('◈','Nothing here yet','Your first records will appear here.'))}
function metric(label,val,icon,foot){return `<div class="metric"><div class="metric-head"><span>${label}</span><span class="metric-icon">${icon}</span></div><div class="metric-val">${val}</div><div class="metric-foot">${foot}</div></div>`}
function friendlyError(error){toast(error?.message||String(error),true)}
function setPage(name,searchQuery=''){window.scrollTo(0,0);if(!groups.flatMap(g=>g.items).some(x=>x[0]===name))name='dashboard';state.page=name;state.query=searchQuery;state.status='';$('#sidebar').classList.remove('open');$('#nav').querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.page===name));$('#crumb').textContent=groups.flatMap(g=>g.items).find(x=>x[0]===name)?.[2]||'Overview';history.replaceState(null,'','#'+name);renderPage().catch(friendlyError)}
function nav(){const groupsAllowed=groups.map(g=>({...g,items:g.items.filter(x=>minRoles[x[0]]===undefined || ({viewer:0,operator:1,manager:2,admin:3}[state.user?.role]||0)>=minRoles[x[0]])}));$('#nav').innerHTML=groupsAllowed.map(g=>`<div class="nav-group">${g.title}</div>${g.items.map(([key,icon,label])=>`<button class="nav-item ${state.page===key?'active':''}" data-page="${key}"><span class="nav-icon">${svg(icon,18)}</span><span>${label}</span>${state.page===key?'<span class="active-mark"></span>':''}</button>`).join('')}`).join('')}
function showAuth(mode){state.authMode=mode;$('#auth-page').classList.remove('hidden');$('#app-shell').classList.add('hidden');const setup=mode==='setup',invite=mode==='invite',reset=mode==='reset';$('#auth-title').textContent=setup?'Create your workspace':invite?'Accept your invitation':reset?'Reset your password':'Welcome back';$('#auth-subtitle').textContent=setup?'Set up the first administrator for your private workspace.':invite?'Create your secure team account and join the workspace.':reset?'Choose a new strong password using your one-time reset link.':'Sign in to your team’s secure ticket operations hub.';$('#auth-name-field').classList.toggle('hidden',!setup&&!invite);$('#setup-code-field').classList.toggle('hidden',!setup);$('#auth-submit').textContent=setup?'Create workspace →':invite?'Accept invite →':reset?'Reset password →':'Sign in →';$('#auth-password').setAttribute('autocomplete',setup||invite||reset?'new-password':'current-password');$('#auth-error').classList.add('hidden');if(setup||invite||reset){$('#auth-password').setAttribute('minlength','12');$('#auth-password').placeholder='12+ characters, letters and numbers'}else{$('#auth-password').removeAttribute('minlength');$('#auth-password').placeholder='Enter your password'}if(invite||reset){const p=new URLSearchParams(location.search);$('#auth-email').value=p.get('email')||'';}}
function showApp(){state.user&&($('#user-display').textContent=state.user.name,$('#user-role').textContent=state.user.role,$('#user-avatar').textContent=state.user.name[0]?.toUpperCase()||'C');$('#auth-page').classList.add('hidden');$('#app-shell').classList.remove('hidden');nav();let requested=(location.hash||'#dashboard').slice(1);if(minRoles[requested]&&!can('manager'))requested='dashboard';setPage(requested)}
async function boot(){try{const data=await api('/auth/state');if(data.authenticated){state.user=data.user;state.csrf=data.csrf;showApp()}else if(data.setup_required){showAuth('setup')}else if(new URLSearchParams(location.search).has('invite')){showAuth('invite')}else if(new URLSearchParams(location.search).has('reset')){showAuth('reset')}else{showAuth('login')}}catch(e){showAuth('login');friendlyError(e)}}
$('#auth-form').addEventListener('submit',async e=>{e.preventDefault();const form={email:$('#auth-email').value.trim(),password:$('#auth-password').value};if(state.authMode!=='login'){form.name=$('#auth-name').value.trim()||'';}if(state.authMode==='setup')form.setup_code=$('#auth-setup-code').value;if(state.authMode==='invite')form.token=new URLSearchParams(location.search).get('invite')||'';if(state.authMode==='reset'){form.new_password=form.password;delete form.password;form.token=new URLSearchParams(location.search).get('reset')||''}try{const r=await api('/auth/'+(state.authMode==='setup'?'bootstrap':state.authMode==='invite'?'invite':state.authMode==='reset'?'reset-password':'login'),{method:'POST',body:form});if(state.authMode==='reset'){history.replaceState(null,'',location.pathname);$('#auth-password').value='';showAuth('login');toast('Password changed. Sign in with your new password.');return}state.csrf=r.csrf;history.replaceState(null,'',location.pathname);const me=await api('/auth/state');state.user=me.user;state.csrf=me.csrf;showApp();toast('Signed in successfully')}catch(err){$('#auth-error').textContent=err.message;$('#auth-error').classList.remove('hidden')}});
$('#show-password').addEventListener('click',()=>{$('#auth-password').type=$('#auth-password').type==='password'?'text':'password'});
$('#nav').addEventListener('click',e=>{const target=e.target.closest('[data-page]');if(target)setPage(target.dataset.page)});
$('#menu-toggle').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
$('#quick-add').addEventListener('click',async()=>{try{if(!state.events.length)state.events=await api('/events');if(!state.events.length){newEvent();return;}await newTicket()}catch(error){friendlyError(error)}});
const globalSearch=$('#global-search');
if(globalSearch){
 globalSearch.addEventListener('keydown',e=>{
  if(e.key==='Enter'){
   const q=globalSearch.value.trim();
   if(!q)return;
   e.preventDefault();setPage('tickets',q);globalSearch.value='';
  }
 });
}
window.addEventListener('keydown',e=>{
 if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){
  e.preventDefault();globalSearch?.focus();globalSearch?.select();
 }
});

$('#user-chip').addEventListener('click',async()=>{if(!confirm('Sign out of C TicketWave PRO?'))return;try{await api('/auth/logout',{method:'POST'});state.user=null;state.csrf='';showAuth('login');toast('Signed out')}catch(e){friendlyError(e)}});
function parseForm(form){const result={};new FormData(form).forEach((val,key)=>{result[key]=typeof val==='string'?val.trim():val});return result}
function field({name,label,type='text',value='',placeholder='',required=false,options=[],wide=false,help='',min,max,step}){const id='f-'+name;const extra=(required?' required':'')+(min!==undefined?` min="${safe(min)}"`:'')+(max!==undefined?` max="${safe(max)}"`:'')+(step!==undefined?` step="${safe(step)}"`:'');let control=type==='select'?`<select id="${id}" name="${name}"${extra}>${options.map(o=>`<option value="${safe(o.value)}" ${String(value)===String(o.value)?'selected':''}>${safe(o.label)}</option>`).join('')}</select>`:type==='textarea'?`<textarea id="${id}" name="${name}" placeholder="${safe(placeholder)}" ${required?'required':''}>${safe(value)}</textarea>`:`<input id="${id}" name="${name}" type="${type}" value="${safe(value)}" placeholder="${safe(placeholder)}" ${extra}>`;return `<div class="field ${wide?'field-wide':''}"><label for="${id}">${safe(label)}</label>${control}${help?`<small>${safe(help)}</small>`:''}</div>`}
function openModal(title,fields,submit,{note='',label='Save changes'}={}){$('#modal-title').textContent=title;$('#modal-form').innerHTML=`${note?`<div class="info-box field-wide" style="margin-bottom:18px">${note}</div>`:''}<div class="fields">${fields.map(field).join('')}</div><div class="modal-footer"><button type="button" class="btn btn-ghost" data-modal-close>Cancel</button><button type="submit" class="btn btn-primary">${label}</button></div>`;$('#modal-overlay').classList.remove('hidden');$('#modal-form').onsubmit=async e=>{e.preventDefault();const b=$('#modal-form button[type=submit]');b.disabled=true;b.textContent='Saving…';try{await submit(parseForm(e.target));closeModal();await renderPage()}catch(error){friendlyError(error);b.disabled=false;b.textContent=label}};$('#modal-form').querySelector('input,select,textarea')?.focus()}
function closeModal(){$('#modal-overlay').classList.add('hidden');$('#modal-form').onsubmit=null}
$('#modal-overlay').addEventListener('click',e=>{if(e.target.id==='modal-overlay'||e.target.closest('[data-modal-close]'))closeModal()});$('#modal-close').addEventListener('click',closeModal);
function eventOptions(){return state.events.filter(e=>!e.archived).map(e=>({value:e.id,label:`${e.title} — ${e.city} · ${new Date(e.starts_at).toLocaleDateString('en-GB')}`}))}
function ticketOptions(){return state.tickets.filter(t=>t.status==='available'&&t.quantity>t.sold_quantity).map(t=>({value:t.id,label:`#${t.id} ${t.event_title} · ${t.section||'General'} · ${t.quantity-t.sold_quantity} left`}))}
function pageAction(action,handler){window.actions[action]=handler}
window.actions={};
$('#page').addEventListener('click',async e=>{const route=e.target.closest('[data-page]');if(route){setPage(route.dataset.page);return;}const el=e.target.closest('[data-act]');if(!el)return;const key=el.dataset.act;const handler=window.actions[key];if(handler)try{await handler(el)}catch(err){friendlyError(err)}});
async function renderPage(){const p=state.page;$('#page').innerHTML=`<div class="inline-empty">Loading your workspace…</div>`;switch(p){case'dashboard':return renderDashboard();case'events':return renderEvents();case'tickets':return renderTickets();case'listings':return renderListings();case'sales':return renderSales();case'expenses':return renderExpenses();case'team':return renderTeam();case'audit':return renderAudit();case'account':return renderAccount();default:setPage('dashboard')}}
async function renderDashboard(){
 const [d,insights]=await Promise.all([api('/dashboard'),api('/insights')]);state.dashboard=d;state.insights=insights;
 const sales=insights.monthly_sales||[];const maxRevenue=Math.max(1,...sales.map(x=>x.revenue_cents||0));
 const trend=sales.length?`<div class="sales-trend">${sales.map(x=>`<div class="trend-col" title="${safe(x.month)} · ${fmtMoney(x.revenue_cents)}"><span class="trend-value">${fmtMoney(x.revenue_cents)}</span><div class="trend-bar" style="height:${Math.max(9,Math.round(x.revenue_cents/maxRevenue*100))}%"></div><small>${safe(x.month.slice(5))}/${safe(x.month.slice(2,4))}</small></div>`).join('')}</div>`:empty('↗','Your sales chart starts here','Record your first sale to see the revenue trend.');
 const best=insights.top_events||[];
 $('#page').innerHTML=`
 <section class="hero-v3"><div class="hero-copy"><div class="eyebrow">C TICKETWAVE / OVERVIEW · LIVE DATA</div><h1>Everything about your tickets.<br><span>In one beautiful workspace.</span></h1><p>Your inventory, event calendar, profits and team activity — organized around the work that matters.</p><div class="hero-actions">${can('operator')?(d.events?btn('＋ Add tickets','new-ticket'):btn('＋ Create first event','new-event')):''}${btn('Explore sales ↗','go-sales','ghost')}</div></div><div class="hero-art"><div class="hero-orb"><img src="/static/logo.png" alt="C TicketWave" /></div><div class="hero-small-card"><span>● LIVE WORKSPACE</span><b>${nfmt(d.events)} events</b><small>${nfmt(d.tickets_available)} tickets available</small></div></div></section>
 <div class="section-title-row"><div><div class="eyebrow">AT A GLANCE</div><h2>Business overview</h2></div><span class="timestamp-label">Financial amounts in EUR · Data from your database</span></div>
 <div class="metric-grid v3-kpis">${metric('Net profit',fmtMoney(d.gross_profit_cents),'↗','Revenue − sold costs − fees − expenses')}${metric('Sales revenue',fmtMoney(d.sales_revenue_cents),'€','Confirmed EUR transactions')}${metric('Available tickets',nfmt(d.tickets_available),'◈',`${nfmt(d.tickets_total)} units in inventory`)}${metric('Live listings',nfmt(d.listing_status?.listed||0),'▤','Manually marked / linked listings')}</div>
 <div class="dashboard-grid v3-dash-grid">${panel('Revenue trend','Revenue by month · real recorded EUR sales',`<div class="panel-body"><div class="trend-total"><span>Recorded gross revenue</span><strong>${fmtMoney(d.sales_revenue_cents)}</strong></div>${trend}</div>`,`<button class="table-action" data-page="sales">View sales ↗</button>`)}${panel('Top performing events','Based on net profit from EUR transactions',`<div class="panel-body top-events">${best.length?best.slice(0,4).map((e,i)=>`<button class="performance-row" data-page="sales"><span class="rank-no">0${i+1}</span><span class="perf-event"><strong>${safe(e.title)}</strong><small>${nfmt(e.sold)} tickets sold · ${safe(e.city)}</small></span><span class="perf-money ${e.net_profit_cents>=0?'positive':'negative'}">${fmtMoney(e.net_profit_cents)}<small>ROI ${e.roi_pct===null?'—':e.roi_pct+'%'}</small></span><span class="perf-arrow">↗</span></button>`).join(''):empty('▤','No sales yet','Record your first sale to start tracking your profitability.')}</div>`)}</div>
 <div class="dashboard-grid v3-dash-grid bottom-panels">${panel('Upcoming events','Your next dates and remaining inventory',d.upcoming.length?table(['Event','Date','Available',''],d.upcoming.map(e=>`<tr><td><strong class="table-name">${safe(e.title)}</strong><div class="table-sub">${safe(e.city)} · ${safe(e.venue)}</div></td><td>${fmtDate(e.starts_at)}</td><td>${nfmt(e.remaining)}</td><td><button class="table-action" data-page="sales">View sales ↗</button></td></tr>`)):empty('▦','No upcoming events','Create an event to start tracking your tickets.'))}${panel('Recent team activity','Recorded changes across your workspace',`<div class="panel-body">${d.activity.length?d.activity.slice(0,6).map(a=>`<div class="activity-line"><span class="activity-ico">↗</span><div class="activity-details"><b>${safe(a.action.replaceAll('.',' · '))}</b><small>${safe(a.actor||'System')} · ${fmtDate(a.created_at)}</small></div></div>`).join(''):empty('◷','Activity starts here','Your actions are securely recorded.')}</div>`)}</div>`;

}
async function renderEvents(){state.events=await api('/events');const list=state.events;$('#page').innerHTML=pageTitle('Events','Manage venues, event dates and inventory across upcoming and past shows.',can('operator')?btn('＋ Add event','new-event'):'')+`<div class="grid grid-3">${list.slice(0,9).map(e=>`<article class="event-card"><div class="event-date">${fmtDate(e.starts_at).toUpperCase()}</div><h3>${safe(e.title)}</h3><p>⌖ ${safe(e.venue)} · ${safe(e.city)}, ${safe(e.country)}</p><div class="event-footer"><span>◈ ${nfmt(e.remaining)} unsold tickets</span><span>${safe(e.category)}</span></div></article>`).join('')||empty('▦','No events yet','Create your first event to organize tickets and sales.')}</div><div style="margin-top:22px">${panel('All events',`${list.length} events in this workspace`,table(['Event','Location','Date','Ticket lots','Remaining','Source'],list.map(e=>`<tr><td><div class="table-name">${safe(e.title)}</div><div class="table-sub">${safe(e.category)}</div></td><td>${safe(e.city)} · ${safe(e.country)}</td><td>${fmtDate(e.starts_at)}</td><td>${e.lots}</td><td>${e.remaining}</td><td><span class="source-badge">${safe(e.external_source||'Manual')}</span></td></tr>`),empty('▦','No events available','Use Add event to create your first record.')))}</div>`}
function newEvent(){if(!can('operator'))return toast('You need Operator access.',true);openModal('Create a new event',[{name:'title',label:'Event / performer name',required:true,placeholder:'e.g. The Weeknd – European Tour',wide:true},{name:'starts_at',label:'Event date and time',type:'datetime-local',required:true,help:'Uses your local timezone'},{name:'category',label:'Event category',type:'select',options:['Concert','Sports','Festival','Theatre','Other'].map(x=>({value:x,label:x}))},{name:'venue',label:'Venue name',required:true,placeholder:'O2 Arena'},{name:'city',label:'City',required:true,placeholder:'Prague'},{name:'country',label:'Country',required:true,placeholder:'Czechia'}],async d=>{d.starts_at=new Date(d.starts_at).toISOString();await api('/events',{method:'POST',body:d});toast('Event added successfully')},{label:'Create event'})}
async function newTicket(){if(!can('operator'))return toast('You need Operator access.',true);if(!state.events.length)state.events=await api('/events');if(!state.events.length)return toast('Create an event before adding tickets.',true);openModal('Add tickets to inventory',[
{name:'event_id',label:'Event',type:'select',options:eventOptions(),required:true,wide:true},
{name:'quantity',label:'Quantity',type:'number',value:1,min:1,max:100,required:true},
{name:'type',label:'Delivery type',type:'select',options:['E-Ticket','Mobile Transfer','Digital','Paper'].map(x=>({value:x,label:x}))},
{name:'section',label:'Section',placeholder:'e.g. 421'},
{name:'row_label',label:'Row',placeholder:'e.g. 15'},
{name:'seats',label:'Seats',placeholder:'e.g. 12,13,14,15'},
{name:'source',label:'Original platform',placeholder:'e.g. Ticketmaster'},
{name:'cost',label:'Purchase cost (per ticket)',type:'number',step:'.01',min:0,value:'0'},
{name:'face',label:'Face value (per ticket)',type:'number',step:'.01',min:0,value:'0'},
{name:'currency_code',label:'Currency',type:'select',options:['EUR','CZK','USD','GBP','PLN','CHF'].map(x=>({value:x,label:x}))},
{name:'file',label:'Upload ticket PDF (optional, max 20 MB)',type:'file',wide:true,help:'Stored encrypted on the server. Do not publish QR or barcode images.'},
{name:'notes',label:'Internal notes',type:'textarea',wide:true}],async d=>{const form=new FormData();Object.entries(d).forEach(([k,v])=>{if(k==='file'&&(!v||!v.name))return;form.append(k,v)});await api('/tickets',{method:'POST',body:form});toast('Ticket lot saved securely')},{note:'Your PDFs are encrypted at rest. All members of your trusted workspace can access the inventory; access is controlled by account roles.',label:'Save ticket lot'})}
function ticketRow(t){
 return `<tr>
   <td><div class="table-name">#${t.id} · ${safe(t.event_title)}</div><div class="table-sub">${fmtDate(t.starts_at)}</div></td>
   <td>${safe(t.section||'General')} · ${safe(t.row_label||'—')}<div class="table-sub">${safe(t.seats||'Unassigned')}</div></td>
   <td><strong>${nfmt(Math.max(0,t.quantity-t.sold_quantity))}</strong> / ${nfmt(t.quantity)}</td>
   <td>${fmtMoney(t.cost_cents,t.currency)}</td>
   <td>${statusBadge(t.status)}</td>
   <td>${statusBadge(t.listing_status||'Not listed')}</td>
   <td>${t.stored_filename?`<button class="table-action" data-act="pdf-${t.id}">↓ PDF</button>`:'—'}</td>
   <td><div class="inline-actions">${can('operator')&&t.status==='available'&&t.quantity>t.sold_quantity?`<button class="table-action" data-act="ticket-list-${t.id}">List</button><button class="table-action" data-act="ticket-sell-${t.id}">Sell</button><button class="table-action" data-act="ticket-reserve-${t.id}">Reserve</button>`:''}${can('operator')&&t.status==='reserved'?`<button class="table-action" data-act="ticket-release-${t.id}">Release</button>`:''}</div></td>
 </tr>`;
}
function filterInventory(){
 const q=state.query.trim().toLowerCase();
 const matched=state.tickets.filter(t=>(!state.status||state.status===t.status)&&[
   t.event_title,t.section,t.row_label,t.source,t.seats,t.id,t.currency
 ].join(' ').toLowerCase().includes(q));
 const wrap=$('#inventory-table-holder');
 if(wrap)wrap.innerHTML=table(
   ['Ticket / Event','Section & Seats','Available','Cost / unit','Status','Listing','PDF','Actions'],
   matched.map(ticketRow),
   empty('◈',state.query||state.status?'No matching tickets':'No tickets yet',
     state.query||state.status?'Try a different search term or status filter.':'Create a ticket lot to start tracking your inventory.')
 );
 if($('#inventory-result-count'))$('#inventory-result-count').textContent=nfmt(matched.length)+' matching lots';
}
async function renderTickets(){
 state.tickets=await api('/tickets');
 const all=state.tickets;
 const available=all.filter(t=>t.status==='available').reduce((n,t)=>n+Math.max(0,t.quantity-t.sold_quantity),0);
 const sold=all.reduce((n,t)=>n+Number(t.sold_quantity||0),0);
 const pdfs=all.filter(t=>!!t.stored_filename).length;
 $('#page').innerHTML=pageTitle('Ticket Inventory',
   'Track every seat, PDF and ticket lot with a searchable inventory.',
   can('operator')?btn('＋ Upload / Add tickets','new-ticket'):'')+
 `<div class="metric-grid inventory-kpis">
   ${metric('Available tickets',nfmt(available),'◈','Ready to list or reserve')}
   ${metric('Tickets sold',nfmt(sold),'↗','Recorded sales across all lots')}
   ${metric('Ticket lots',nfmt(all.length),'▤','Unique inventory groups')}
   ${metric('PDF documents',nfmt(pdfs),'↓','Encrypted attachments')}
 </div>`+
 panel('Inventory explorer','Filter instantly by event, section, seats or status.',
   `<div class="toolbar"><input id="ticket-search" type="search" placeholder="⌕ Search event, section, platform…" value="${safe(state.query)}" aria-label="Search ticket inventory"><select id="ticket-status" aria-label="Filter ticket status"><option value="">All statuses</option>${['available','reserved','sold','cancelled'].map(x=>`<option value="${x}" ${state.status===x?'selected':''}>${x[0].toUpperCase()+x.slice(1)}</option>`).join('')}</select><div class="toolbar-spacer"></div><span class="rows-count" id="inventory-result-count"></span></div><div id="inventory-table-holder"></div>`);
 filterInventory();
 $('#ticket-search')?.addEventListener('input',e=>{state.query=e.target.value;filterInventory()});
 $('#ticket-status')?.addEventListener('change',e=>{state.status=e.target.value;filterInventory()});
 for(const t of all){
   pageAction('pdf-'+t.id,()=>window.open('/api/tickets/'+t.id+'/pdf','_blank','noopener,noreferrer'));
   pageAction('ticket-list-'+t.id,()=>newListing(t.id));
   pageAction('ticket-sell-'+t.id,()=>newSale(t.id));
   pageAction('ticket-reserve-'+t.id,async()=>{await api('/tickets/'+t.id+'/status',{method:'PATCH',body:{status:'reserved'}});toast('Ticket lot reserved');await renderTickets()});
   pageAction('ticket-release-'+t.id,async()=>{await api('/tickets/'+t.id+'/status',{method:'PATCH',body:{status:'available'}});toast('Ticket lot available again');await renderTickets()});
 }
}
async function newListing(selectedId){if(!can('operator'))return toast('Operator access needed',true);if(!state.tickets.length)state.tickets=await api('/tickets');const options=ticketOptions();if(!options.length)return toast('Add available ticket inventory first.',true);openModal('Create marketplace listing draft',[
{name:'ticket_id',label:'Ticket lot',type:'select',options,value:selectedId||options[0].value,wide:true,required:true},
{name:'marketplace',label:'Marketplace',type:'select',options:['viagogo','StubHub','TicketSwap','Other'].map(x=>({value:x,label:x}))},
{name:'price',label:'Listing price / ticket',type:'number',min:.01,step:'.01',placeholder:'150.00',required:true},
{name:'fee_pct',label:'Estimated commission (%)',type:'number',min:0,max:50,step:'.1',value:10},
{name:'notes',label:'Internal listing notes',type:'textarea',wide:true,placeholder:'Delivery deadlines, restrictions or notes'}],async d=>{await api('/listings',{method:'POST',body:d});toast('Listing draft created')},{note:'This creates a <b>local draft only</b>. It is not automatically published to Viagogo. The official API requires approved OAuth access and verified integration.',label:'Create listing draft'})}
async function renderListings(){state.listings=await api('/listings');$('#page').innerHTML=pageTitle('Market Listings','Prepare offers, track marketplace IDs and avoid accidental duplicate listings.',can('operator')?btn('＋ Create draft','new-listing'):'')+`<div class="notice-blue">▣ <b>Publishing control:</b> Listings are local drafts until you publish them on a marketplace. Mark a listing "Listed" only after entering the real external listing ID. Direct Viagogo API publishing is not activated.</div>`+panel('Listing management',`${state.listings.length} listings`,table(['Event','Marketplace','Price / ticket','Commission','Status','External ID','Action'],state.listings.map(l=>`<tr><td><div class="table-name">#${l.ticket_id} ${safe(l.event_title)}</div><div class="table-sub">${safe(l.section||'General')} · ${l.quantity-l.sold_quantity} unsold</div></td><td>${safe(l.marketplace)}</td><td>${fmtMoney(l.price_cents,l.currency)}</td><td>${(l.commission_bp/100).toFixed(1)}%</td><td>${statusBadge(l.status)}</td><td>${safe(l.external_id||'—')}</td><td>${can('operator')?`<button class="table-action" data-act="edit-listing-${l.id}">Update</button>`:'—'}</td></tr>`),empty('▧','No marketplace listings yet','Create your first draft from a ticket lot.')));for(const l of state.listings)pageAction(`edit-listing-${l.id}`,()=>editListing(l))}
function editListing(l){openModal('Update listing #'+l.id,[{name:'status',label:'Listing status',type:'select',value:l.status,options:['draft','ready','listed','review','closed'].map(x=>({value:x,label:x}))},{name:'external_id',label:'Real marketplace listing ID',value:l.external_id||'',placeholder:'Required if status = Listed',wide:true}],async d=>{await api('/listings/'+l.id,{method:'PATCH',body:d});toast('Listing updated')},{note:'“Listed” is a manual confirmation. Enter only an actual marketplace listing ID. Closing a listing does not cancel it automatically on Viagogo.'})}
async function newSale(selected){if(!can('operator'))return toast('Operator access needed',true);if(!state.tickets.length)state.tickets=await api('/tickets');const options=ticketOptions();if(!options.length)return toast('No available ticket inventory.',true);openModal('Record a sale',[
{name:'ticket_id',label:'Ticket lot',type:'select',options,value:selected||options[0].value,wide:true},
{name:'quantity',label:'Tickets sold',type:'number',min:1,max:100,value:1,required:true},
{name:'amount',label:'Total sale amount',type:'number',min:0,step:'.01',required:true,placeholder:'250.00'},
{name:'fees',label:'Total marketplace fees',type:'number',min:0,step:'.01',value:0},
{name:'channel',label:'Sales channel',type:'select',options:['viagogo','StubHub','TicketSwap','Direct','Other'].map(x=>({value:x,label:x}))},
{name:'reference',label:'Order / payout reference',placeholder:'Optional order reference',wide:true}],async d=>{await api('/sales',{method:'POST',body:d});toast('Sale recorded and ticket inventory updated')},{note:'Important: <b>sale amount and fees are totals for all tickets in this sale</b>. The app will prevent overselling the same ticket lot.',label:'Record sale'})}
async function renderSales(){
 const [sales,insights,summary]=await Promise.all([api('/sales'),api('/insights'),api('/dashboard')]);
 state.sales=sales;state.insights=insights;
 const euro=sales.filter(s=>s.currency==='EUR');
 const revenue=euro.reduce((n,s)=>n+s.amount_cents,0);
 const fees=euro.reduce((n,s)=>n+s.fee_cents,0);
 const sold=sales.reduce((n,s)=>n+s.quantity,0);
 const stats=insights.event_performance||[];
 const netProfit=summary.gross_profit_cents;
 const renderEventRow=(e)=>{
   const total=Math.max(1,Number(e.quantity||0));
   const share=Math.max(0,Math.min(100,Math.round(100*e.sold/total)));
   return `<tr>
     <td><div class="table-name">${safe(e.title)}</div><div class="table-sub">${safe(e.city)} · ${fmtDate(e.starts_at)}</div></td>
     <td><strong>${nfmt(e.sold)} / ${nfmt(e.quantity)}</strong><div class="sold-track"><span style="width:${share}%"></span></div></td>
     <td><strong>${fmtMoney(e.revenue_cents)}</strong></td>
     <td class="${e.net_profit_cents>=0?'positive':'negative'}"><strong>${fmtMoney(e.net_profit_cents)}</strong></td>
     <td>${e.roi_pct===null?'<span class="muted">—</span>':`<span class="roi-pill ${e.roi_pct>=0?'up':'down'}">${e.roi_pct>0?'+':''}${e.roi_pct}%</span>`}</td>
     <td><button class="table-action" data-act="event-breakdown-${e.id}">Details ↗</button></td>
   </tr>`;
 };
 $('#page').innerHTML=pageTitle('Sales & Profit','Every sale, every cost and your true performance — in one place.',can('operator')?btn('＋ Record a sale','new-sale'):'')+
 `<div class="metric-grid v4-finance-grid">
   ${metric('Net profit',fmtMoney(netProfit),'↗','Based on recorded EUR sales and costs')}
   ${metric('Gross revenue',fmtMoney(revenue),'€','Confirmed EUR transactions')}
   ${metric('Tickets sold',nfmt(sold),'◈','Across recorded sales')}
   ${metric('Marketplace fees',fmtMoney(fees),'◎','Recorded EUR sales fees')}
 </div>
 <div class="insights-explainer"><span class="info-dot">i</span><div><strong>Transparent financial reporting</strong><p>EUR results are calculated from the database. Net profit deducts ticket purchase costs, sales fees and recorded event expenses; other currencies are not silently converted.</p></div></div>
 <section class="section-heading"><div><span class="eyebrow">PERFORMANCE BY EVENT</span><h2>Where your profit comes from</h2><p>Compare sales, remaining inventory and your return on investment.</p></div><span class="section-count">${stats.length} event${stats.length===1?'':'s'}</span></section>
 ${panel('Event performance','Click Details to see exact costs and fees.',table(['Event','Sold','Revenue','Net profit','ROI',''],stats.map(renderEventRow),empty('↗','Nothing sold yet','Add tickets and record a sale to unlock financial reporting.')))}
 <div id="event-breakdown" class="hidden"></div>
 <section class="section-heading"><div><span class="eyebrow">TRANSACTION HISTORY</span><h2>All recorded sales</h2><p>Clear audit trail of quantities, marketplaces and fees.</p></div><span class="section-count">${sales.length} transactions</span></section>
 ${panel('Sales ledger','Complete transaction records',table(['Event & section','Quantity','Sale amount','Fees','After fees','Marketplace','Date','Reference'],sales.map(s=>`<tr><td><div class="table-name">${safe(s.event_title)}</div><div class="table-sub">${safe(s.section||'General')} · ${safe(s.seats||'—')}</div></td><td>${s.quantity}</td><td><strong>${fmtMoney(s.amount_cents,s.currency)}</strong></td><td>${fmtMoney(s.fee_cents,s.currency)}</td><td class="positive">${fmtMoney(s.amount_cents-s.fee_cents,s.currency)}</td><td>${safe(s.channel)}</td><td>${fmtDate(s.sold_at)}</td><td>${safe(s.reference||'—')}</td></tr>`),empty('↗','No sales recorded','Record a sale to start tracking revenue and profit.')))}
 `;
 for(const e of stats)pageAction('event-breakdown-'+e.id,()=>renderEventBreakdown(e.id));
}
async function renderEventBreakdown(id){
 const response=await api('/events/'+id+'/recap');
 const e=response.summary;
 const total=Math.max(1,Number(e.quantity||0));
 const share=Math.min(100,Math.max(0,Math.round((e.sold||0)/total*100)));
 const target=$('#event-breakdown');
 if(!target)return;
 target.classList.remove('hidden');
 target.innerHTML=`<article class="profit-detail">
   <div class="profit-detail-header"><div><div class="eyebrow">DETAILED FINANCIAL BREAKDOWN</div><h2>${safe(e.title)}</h2><p>${safe(e.venue||'')} · ${safe(e.city||'')} · ${fmtDate(e.starts_at)}</p></div><button type="button" class="icon-btn" data-act="close-event-detail" aria-label="Close event breakdown">✕</button></div>
   <div class="profit-primary"><div><small>NET PROFIT</small><strong class="${e.net_profit_cents>=0?'positive':'negative'}">${fmtMoney(e.net_profit_cents)}</strong></div><div><small>RETURN ON INVESTMENT</small><strong>${e.roi_pct===null?'—':e.roi_pct+'%'}</strong></div><div><small>INVENTORY SOLD</small><strong>${nfmt(e.sold)} / ${nfmt(e.quantity)}</strong></div></div>
   <div class="progress-large"><span style="width:${share}%"></span></div>
   <div class="profit-lines"><div><span>Sales revenue</span><strong>${fmtMoney(e.revenue_cents)}</strong></div><div><span>Cost of sold tickets</span><strong>−${fmtMoney(e.sold_cost_cents)}</strong></div><div><span>Marketplace fees</span><strong>−${fmtMoney(e.fees_cents)}</strong></div><div><span>Event expenses</span><strong>−${fmtMoney(e.expenses_cents)}</strong></div></div>
   <p class="profit-footnote">EUR only • Figures come from recorded sales, costs and fees. Unsold ticket costs are not included in realized profit.</p>
 </article>`;
 pageAction('close-event-detail',()=>{target.classList.add('hidden');target.innerHTML=''})
 target.scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function renderExpenses(){state.expenses=await api('/expenses');const total=state.expenses.filter(e=>e.currency==='EUR').reduce((n,x)=>n+x.amount_cents,0);$('#page').innerHTML=pageTitle('Expenses','Track delivery expenses, subscriptions, proxy costs and operational fees.',can('operator')?btn('＋ Add expense','new-expense'):'')+`<div class="metric-grid">${metric('Expense entries',state.expenses.length,'◎','Across all currencies')}${metric('Total expenses · EUR',fmtMoney(total),'€','Tracked operational costs')}${metric('Active events',state.dashboard?.events||'—','▦','Event-linked costs')}${metric('Inventory',state.dashboard?.lots||'—','◈','Ticket lots')}</div>`+panel('Expense ledger','Every expense can optionally be linked to a specific event',table(['Description','Event','Amount','Date','Notes'],state.expenses.map(e=>`<tr><td><div class="table-name">${safe(e.label)}</div></td><td>${safe(e.event_title||'General operating cost')}</td><td>${fmtMoney(e.amount_cents,e.currency)}</td><td>${fmtDate(e.incurred_at)}</td><td>${safe(e.notes||'—')}</td></tr>`),empty('◎','No expenses yet','Keep costs organized to understand your real margin.')))}
async function newExpense(){if(!can('operator'))return toast('Operator access needed',true);if(!state.events.length)state.events=await api('/events');const evopts=[{value:'',label:'General / not linked'},...eventOptions()];openModal('Add an expense',[
{name:'label',label:'Expense description',placeholder:'Hosting, delivery fees, software, travel…',required:true,wide:true},
{name:'event_id',label:'Related event (optional)',type:'select',options:evopts},
{name:'amount',label:'Amount',type:'number',min:0,step:'.01',required:true},
{name:'currency',label:'Currency',type:'select',options:['EUR','CZK','USD','GBP','PLN','CHF'].map(x=>({value:x,label:x}))},
{name:'notes',label:'Internal notes',type:'textarea',wide:true}],async d=>{if(!d.event_id)delete d.event_id;else d.event_id=Number(d.event_id);await api('/expenses',{method:'POST',body:d});toast('Expense recorded')})}
async function renderTeam(){if(!can('manager'))return setPage('dashboard');state.members=await api('/team');let invites=[];if(can('admin'))invites=await api('/team/invites');$('#page').innerHTML=pageTitle('Team Members','Professional access control for your staff, managers and read-only viewers.',can('admin')?btn('＋ Invite user','invite-user'):'')+`<div class="notice-blue">☷ Every teammate signs in with their own email and password. Roles control who can create tickets, manage sales, invite colleagues and view the audit trail.</div>`+panel('Workspace access',`${state.members.length} members`,table(['Name','Email','Role','Status','Last login','Action'],state.members.map(u=>`<tr><td><div class="table-name">${safe(u.name)}</div></td><td>${safe(u.email)}</td><td>${statusBadge(u.role)}</td><td>${statusBadge(u.enabled?'active':'disabled')}</td><td>${fmtDate(u.last_login)}</td><td>${can('admin')&&u.id!==state.user.id?`<button class="table-action" data-act="member-edit-${u.id}">Manage</button><button class="table-action" data-act="member-reset-${u.id}">Reset login</button>`:'—'}</td></tr>`),empty('♙','No team members','Invite users to work with you.')))+`<div style="margin-top:20px">${panel('Roles & access','Principle of least privilege',`<div class="panel-body"><div class="grid grid-2">${[['Administrator','Manage users, inventory and all workspace records.'],['Manager','Manage inventory and team reporting; cannot change user access.'],['Operator','Create tickets, listings, sales, expenses and events.'],['Viewer','Read-only access to workspace records.']].map(([a,b])=>`<div class="kpi-pill"><strong style="font-size:13px;margin:0 0 8px">${a}</strong><small>${b}</small></div>`).join('')}</div></div>`)}</div>`;state.members.forEach(u=>{pageAction(`member-edit-${u.id}`,()=>manageMember(u));pageAction(`member-reset-${u.id}`,()=>issueReset(u))})}
function inviteUser(){if(!can('admin'))return toast('Admin access needed',true);openModal('Invite a team member',[{name:'email',label:'Work email',type:'email',required:true,wide:true,placeholder:'colleague@company.com'},{name:'role',label:'Initial role',type:'select',options:['viewer','operator','manager','admin'].map(x=>({value:x,label:x}))}],async d=>{const res=await api('/team/invites',{method:'POST',body:d});state.inviteToken=res;toast('Invitation created – copy the link from the next dialog');setTimeout(showInviteLink,100)},{note:'The app will create a one-time invitation link valid for 48 hours. No email is automatically sent; share it securely with the intended person.'})}
function showInviteLink(){const invite=state.inviteToken;if(!invite)return;const url=location.origin+'/?invite='+encodeURIComponent(invite.token)+'&email='+encodeURIComponent(invite.email);openModal('Invitation ready',[{name:'invite_url',label:'Secure one-time link',value:url,wide:true},{name:'note',label:'Next step',value:'Send the invite link privately to '+invite.email,wide:true}],async()=>{try{await navigator.clipboard.writeText(url);toast('Invite link copied to clipboard')}catch(e){toast('Select and copy the link above')};},{note:'The link allows one registration for the chosen email, expires after 48 hours and contains a secret. Do not share it publicly.',label:'Copy invitation link'})}
async function issueReset(u){
 if(!confirm('Issue a one-time password reset link for '+u.email+'?'))return;
 const result=await api('/team/'+u.id+'/password-reset',{method:'POST'});
 const url=location.origin+'/?reset='+encodeURIComponent(result.token)+'&email='+encodeURIComponent(result.email);
 openModal('One-time password reset',[{name:'reset_url',label:'Private reset link (30 min)',value:url,wide:true}],async()=>{
   try{await navigator.clipboard.writeText(url);toast('Reset link copied')}catch(e){toast('Copy the link manually')}
 },{note:'Share only with '+safe(u.email)+' through a trusted channel. The link expires after 30 minutes and can be used once.',label:'Copy reset link'});
}
function manageMember(u){openModal('Manage '+u.name,[{name:'role',label:'Role',type:'select',value:u.role,options:['viewer','operator','manager','admin'].map(x=>({value:x,label:x}))},{name:'enabled',label:'Account status',type:'select',value:String(u.enabled),options:[{value:'1',label:'Enabled'},{value:'0',label:'Disabled — revoke sessions'}]}],async d=>{await api('/team/'+u.id,{method:'PATCH',body:{role:d.role,enabled:d.enabled==='1'}});toast('Team member updated')},{note:'Disabling a member immediately revokes their active sessions. Use separate accounts for every person.'})}
async function renderAudit(){if(!can('manager'))return setPage('dashboard');const logs=await api('/audit');$('#page').innerHTML=pageTitle('Activity Log','A transparent audit trail of your team’s operational changes.')+panel('Recent changes',`${logs.length} recent actions`,table(['Timestamp','Team member','Action','Type','Record','Details'],logs.map(l=>`<tr><td>${fmtDate(l.created_at)}</td><td>${safe(l.actor||'System')}</td><td>${statusBadge(l.action)}</td><td>${safe(l.entity)}</td><td>#${l.entity_id||'—'}</td><td>${safe(l.detail||'—')}</td></tr>`),empty('☷','No activity yet','Activity appears when team members use the workspace.')))}
async function renderAccount(){
 const m=state.user||{};
 $('#page').innerHTML=pageTitle('My Account','Manage your sign-in security and export workspace records.')+
 `<div class="grid grid-2 account-grid">
   ${panel('Account & security','Your personal workspace identity',`<div class="panel-body account-profile"><div class="profile-avatar">${safe((m.name||'C')[0].toUpperCase())}</div><div><h3>${safe(m.name||'Workspace member')}</h3><p>${safe(m.email||'')}</p><span class="role-chip">${safe(m.role||'viewer')}</span></div></div><div class="panel-body account-actions">${btn('Change my password','change-password','ghost')}</div>`)}
   ${panel('Backups & exports','Keep copies of your important records',`<div class="panel-body"><p class="muted">Export ticket inventory and sales history as CSV. Administrators should regularly back up the entire private data directory, including its encryption key.</p><div class="account-actions">${can('manager')?`${btn('Export inventory CSV','export-tickets','ghost')} ${btn('Export sales CSV','export-sales','ghost')}`:'Ask a Manager or Admin to export records.'}</div></div>`)}
 </div>`;
}
function changePassword(){openModal('Change your password',[{name:'current_password',label:'Current password',type:'password',required:true,wide:true},{name:'new_password',label:'New password (12+ characters, letters + numbers)',type:'password',required:true,wide:true,minlength:12}],async d=>{await api('/auth/password',{method:'POST',body:d});toast('Password changed. Other sessions were signed out.')})}
pageAction('new-event',newEvent);pageAction('new-ticket',newTicket);pageAction('new-listing',()=>newListing());pageAction('new-sale',()=>newSale());pageAction('new-expense',newExpense);pageAction('invite-user',inviteUser);pageAction('change-password',changePassword);
pageAction('export-tickets',()=>window.open('/api/export/tickets.csv','_blank','noopener,noreferrer'));pageAction('export-sales',()=>window.open('/api/export/sales.csv','_blank','noopener,noreferrer'));
pageAction('go-sales',()=>setPage('sales'));
window.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
boot();
