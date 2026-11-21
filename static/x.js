/* Ceyrl X — functional AI Copilot, Shield, Event Radar and Delivery Center UI. */
'use strict';

let xChatHistory=[];
let xRadarEvents=[];
let xRadarQuery='';
let xRadarCountry='';

const xEsc=(v)=>escapeHtml(v==null?'':v);
const xTag=(text,type='neutral')=>'<span class="x-tag x-tag-'+type+'">'+xEsc(text)+'</span>';
const xHead=(kicker,title,desc)=>
  '<div class="x-page-title"><span class="x-eyebrow">'+xEsc(kicker)+'</span><h2>'+
  xEsc(title)+'</h2><p>'+xEsc(desc)+'</p></div>';
const xNote=(value)=>'<p class="x-muted-note">'+xEsc(value)+'</p>';
const xPane=(title,subtitle,body)=>
  '<section class="x-panel"><div class="x-panel-header"><div><h3>'+xEsc(title)+'</h3>'+
  '<small>'+xEsc(subtitle)+'</small></div></div><div class="x-panel-inner">'+body+'</div></section>';

async function renderXPage(page) {
  if(page==='copilot')return renderXCopilot();
  if(page==='shield')return renderXShield();
  if(page==='radar')return renderXRadar();
  if(page==='delivery')return renderXDelivery();
}

function renderXCopilot() {
  const content=$('#page-content');
  content.innerHTML=heading('Ceyrl AI Copilot',
    'Ask questions about your private ticket inventory, sales and delivery readiness.')+
    '<section class="x-hero x-ai-hero"><div><span class="x-eyebrow">CEYRL / INTELLIGENCE</span>'+
    '<h2>Ask your workspace.<br><em>Get clear answers.</em></h2>'+
    '<p>Start with the private local assistant. Online AI is optional and only receives your question and anonymized aggregate numbers when you explicitly enable it.</p></div>'+
    '<span class="x-hero-decoration" aria-hidden="true">✦</span></section>'+
    '<div class="x-chat-wrap">'+
    '<div class="x-chat-messages" id="x-chat-messages" aria-live="polite"></div>'+
    '<div class="x-chat-examples">'+
    ['How much revenue did I record?','Which ticket lots have no PDFs?','Are there double-sale risks?','How many events do I have?']
      .map(q=>'<button class="x-example" type="button" data-x-example="'+xEsc(q)+'">'+xEsc(q)+'</button>').join('')+
    '</div><form id="x-chat-form" class="x-chat-form">'+
    '<textarea id="x-chat-question" placeholder="Ask about your tickets, profits, risks or events…" rows="3" minlength="2" maxlength="500" required></textarea>'+
    '<div class="x-chat-controls"><label class="x-toggle-option"><input type="checkbox" id="x-use-online-ai">'+
    '<span>Use optional online AI</span></label><button type="submit" class="btn primary" id="x-chat-send">Ask Copilot ↗</button></div>'+
    '<small class="x-disclosure">Online AI is off by default. When enabled, your question and anonymized aggregate counts may be sent to the configured AI provider. No PDF files, stored emails or API keys are sent. Read-only: Copilot cannot modify or sell tickets.</small>'+
    '</form></div>';
  renderXChatMessages();
}

function renderXChatMessages(){
  const el=$('#x-chat-messages');if(!el)return;
  if(!xChatHistory.length){
    el.innerHTML='<div class="x-chat-start"><div class="x-chat-orb">✦</div><h3>Hello, I’m Ceyrl.</h3>'+
      '<p>Ask about your private inventory. I can explain sales, risks, missing PDFs and help you find the right screen.</p>'+
      xTag('Private by default','green')+'</div>';return;
  }
  el.innerHTML=xChatHistory.map(m=>
    '<div class="x-chat-bubble '+(m.role==='user'?'x-from-user':'x-from-assistant')+'"><span>'+
    (m.role==='user'?'YOU':'CEYRL '+(m.mode==='ai'?'AI':'LOCAL'))+'</span><p>'+
    xEsc(m.text)+'</p>'+
    (m.notice?'<small>'+xEsc(m.notice)+'</small>':'')+
    (m.pages?'<div class="x-chat-actions">'+m.pages.map(p=>
      '<button type="button" data-x-goto="'+xEsc(p)+'">'+xEsc(p.replaceAll('_',' '))+' ↗</button>').join('')+'</div>':'')+
    '</div>').join('');
  el.scrollTop=el.scrollHeight;
}

async function xAskCopilot(){
  const field=$('#x-chat-question'),button=$('#x-chat-send');
  const question=field?.value.trim();
  if(!question || question.length<2)return;
  const useAI=$('#x-use-online-ai')?.checked||false;
  button.disabled=true;
  xChatHistory.push({role:'user',text:question});
  field.value='';
  renderXChatMessages();
  try{
    const response=await api('/x/copilot',{method:'POST',body:{question,use_ai:useAI}});
    xChatHistory.push({role:'assistant',mode:response.mode,text:response.answer,
      notice:response.notice,pages:response.pages});
    if(xChatHistory.length>30)xChatHistory=xChatHistory.slice(-30);
    renderXChatMessages();
  }catch(e){
    xChatHistory.push({role:'assistant',mode:'local',text:'I could not retrieve your private analytics. Try again or check your connection.'});
    renderXChatMessages();notifyError(e);
  }finally{button.disabled=false;field.focus()}
}

async function renderXShield(){
  const root=$('#page-content');
  root.innerHTML=heading('Double-Sale Shield',
    'Spot conflicting seats and stale local listings before they become costly mistakes.')+
    '<div class="x-loading">Checking your personal inventory…</div>';
  const data=await api('/x/shield');
  if(app.page!=='shield')return;
  root.innerHTML=heading('Double-Sale Shield',
    'A safety layer for overlapping seats, duplicate listings and sold-out stock.',
    button('Refresh checks','x-refresh-shield','outline'))+
    '<section class="x-hero x-shield-hero"><div><span class="x-eyebrow">CEYRL / INVENTORY SAFETY</span>'+
    '<h2>Protect every seat.<br><em>Prevent costly overlap.</em></h2>'+
    '<p>Exact seat conflicts are blocked when adding ticket lots. After you record a sale, local active listings for that lot are paused automatically.</p>'+
    '</div><span class="x-hero-decoration" aria-hidden="true">⬡</span></section>'+
    '<div class="x-stat-row"><div class="x-stat"><span>Shield status</span><strong>'+
    (data.status==='clear'?'Clear':'Review needed')+'</strong></div><div class="x-stat"><span>Detected conflicts</span>'+
    '<strong>'+data.conflicts.length+'</strong></div><div class="x-stat"><span>Coverage</span><strong>Local inventory</strong></div></div>'+
    xPane('Inventory risk report','Detected overlaps and actionable checks',
      data.conflicts.length?
        data.conflicts.map(c=>'<div class="x-risk-row"><span class="x-risk-symbol">!</span><div><b>'+
          xEsc(c.kind.replaceAll('_',' '))+'</b><small>'+xEsc(c.message)+'</small>'+
          (c.event_title?'<small>'+xEsc(c.event_title)+'</small>':'')+
          (c.seats?.length?'<small>Seats: '+xEsc(c.seats.join(', '))+'</small>':'')+
          '</div><button class="mini-btn" data-x-goto="tickets">Review</button></div>').join('')
        :'<div class="x-good-state"><span>✓</span><div><b>No known local conflicts</b>'+
          '<p>Your current records passed these checks. Always verify external listings separately.</p></div></div>')+
    xPane('Important limitations','What this protection does and does not do',
      '<p class="x-description">'+xEsc(data.warning)+'</p>'+
      '<div class="x-feature-grid"><div>✓ Blocks exact seat duplicates in known section/row</div>'+
      '<div>✓ Rejects duplicate sale references for the same channel</div>'+
      '<div>✓ Pauses active local listings after a sale</div>'+
      '<div>! Does not change live Viagogo or TicketSwap listings</div></div>');
}

async function renderXDelivery(){
  const root=$('#page-content');
  root.innerHTML=heading('Delivery Readiness',
    'Prepare each ticket lot for fulfillment with an explicit checklist.')+
    '<div class="x-loading">Scoring your private ticket lots…</div>';
  const rows=await api('/x/delivery');
  if(app.page!=='delivery')return;
  const ready=rows.filter(x=>x.readiness.score>=85).length;
  root.innerHTML=heading('Delivery Readiness',
    'Know what is missing before attempting ticket delivery.',
    button('Add ticket lot','new-ticket'))+
    '<section class="x-hero x-delivery-hero"><div><span class="x-eyebrow">CEYRL / TICKET DELIVERY</span>'+
    '<h2>Delivery confidence.<br><em>No guesswork.</em></h2>'+
    '<p>Confirm transfer permissions, ticket availability, delivery format and document readiness. Score measures checklist completeness — not ticket validity.</p>'+
    '</div><span class="x-hero-decoration" aria-hidden="true">▧</span></section>'+
    '<div class="x-stat-row"><div class="x-stat"><span>Tracked lots</span><strong>'+
    rows.length+'</strong></div><div class="x-stat"><span>Checklist score ≥85</span><strong>'+
    ready+'</strong></div><div class="x-stat"><span>Needs review</span><strong>'+
    (rows.length-ready)+'</strong></div></div>'+
    (rows.length?'<div class="x-delivery-grid">'+rows.map(t=>
      '<article class="x-delivery-card"><div class="x-card-top"><span class="x-eyebrow">LOT #'+t.id+
      '</span>'+xTag(t.method.replaceAll('_',' '),t.readiness.score>=85?'green':'neutral')+'</div>'+
      '<h3>'+xEsc(t.event_title)+'</h3><small>'+xEsc(t.section||'General')+
      ' · Row '+xEsc(t.row_label||'—')+' · Seats '+xEsc(t.seats||'—')+'</small>'+
      '<div class="x-readiness-title"><span>Readiness checklist</span><b>'+t.readiness.score+'/100</b></div>'+
      '<div class="x-meter"><div style="width:'+t.readiness.score+'%"></div></div>'+
      '<div class="x-delivery-issues">'+
      (t.readiness.tasks.length?t.readiness.tasks.slice(0,3).map(x=>
        '<span>• '+xEsc(x)+'</span>').join(''):'<span>✓ No checklist items remaining</span>')+
      '</div><button class="btn primary" type="button" data-x-delivery="'+t.id+
      '">Review delivery →</button></article>').join('')+'</div>':
      '<div class="x-empty">No ticket lots yet. Add a ticket to begin delivery checks.</div>')+
    xNote('Checklist scores do not establish ticket authenticity or guarantee that a provider will allow transfer.');
  window.xDeliveryRows=rows;
}
function xEditDelivery(id){
  const t=(window.xDeliveryRows||[]).find(x=>x.id===Number(id));
  if(!t){notify('Ticket lot not found.');return}
  openModal('Delivery checklist · '+t.event_title,[
    {name:'method',label:'Actual delivery method',type:'select',wide:true,value:t.method,
      options:[{value:'unknown',label:'Not confirmed'},{value:'pdf',label:'PDF'},
       {value:'mobile_transfer',label:'Mobile transfer'},{value:'mobile_app',label:'Mobile app / wallet'},
       {value:'physical',label:'Physical ticket'},{value:'will_call',label:'Venue collection'}]},
    {name:'transfer_confirmed',label:'Transfer permitted by provider',type:'select',
      value:String(Number(t.transfer_confirmed)),options:[{value:'0',label:'Not yet confirmed'},{value:'1',label:'Confirmed'}]},
    {name:'possession_confirmed',label:'Physical possession or pickup confirmed',type:'select',
      value:String(Number(t.possession_confirmed)),options:[{value:'0',label:'No'},{value:'1',label:'Yes'}]},
    {name:'restrictions_checked',label:'Provider resale and transfer rules reviewed',type:'select',
      value:String(Number(t.restrictions_checked)),options:[{value:'0',label:'Not checked'},{value:'1',label:'Checked'}]},
    {name:'availability_confirmed',label:'Availability for delivery confirmed',type:'select',
      value:String(Number(t.availability_confirmed)),options:[{value:'0',label:'Not confirmed'},{value:'1',label:'Confirmed'}]},
    {name:'notes',label:'Private delivery notes',type:'textarea',wide:true,
      value:t.delivery_notes||'',help:'Do not enter passwords, verification codes or buyer card details.'}
  ],async v=>{
    const payload={...v,transfer_confirmed:v.transfer_confirmed==='1',
      possession_confirmed:v.possession_confirmed==='1',
      restrictions_checked:v.restrictions_checked==='1',
      availability_confirmed:v.availability_confirmed==='1'};
    await api('/x/delivery/'+id,{method:'PUT',body:payload});
    notify('Delivery checklist updated.');
  },'Save checklist');
}

async function renderXRadar(){
  const root=$('#page-content');
  root.innerHTML=heading('Event Radar','Discover official event dates and follow selected searches.')+
    '<div class="x-loading">Connecting your radar…</div>';
  const [status,saved]=await Promise.all([api('/x/radar/status'),api('/x/radar/watches')]);
  if(app.page!=='radar')return;
  root.innerHTML=heading('Event Radar',
    'Ticketmaster Discovery API event lookup and your own watchlist.',
    button('Connect API key','x-radar-key','outline'))+
    '<section class="x-hero x-radar-hero"><div><span class="x-eyebrow">CEYRL / EVENT DISCOVERY</span>'+
    '<h2>Find what’s next.<br><em>Stay one step ahead.</em></h2>'+
    '<p>Search upcoming events and follow artists or event keywords. Import verified listings into your personal calendar with one click.</p>'+
    '</div><span class="x-hero-decoration" aria-hidden="true">⌾</span></section>'+
    '<div class="x-radar-status">'+xTag(status.connected?'API connected':'API key required',status.connected?'green':'warning')+
    '<span>'+xEsc(status.provider)+'</span><button class="x-link" type="button" data-x-action="radar-key">'+
    (status.personal_key?'Replace personal key':'Set up my key')+'</button></div>'+
    '<form class="x-radar-form" id="x-radar-form"><input name="query" id="x-radar-query" minlength="2" maxlength="80" required '+
    'placeholder="Artist or event name…" value="'+xEsc(xRadarQuery)+'">'+
    '<select name="country" id="x-radar-country">'+
    [['','All countries'],['SK','Slovakia'],['CZ','Czechia'],['DE','Germany'],['AT','Austria'],['PL','Poland'],
     ['GB','United Kingdom'],['US','USA'],['FR','France'],['IT','Italy'],['ES','Spain'],['NL','Netherlands']]
       .map(([c,n])=>'<option value="'+c+'" '+(xRadarCountry===c?'selected':'')+'>'+n+'</option>').join('')+
    '</select><button class="btn primary" type="submit">Search events ↗</button></form>'+
    '<div class="x-search-actions"><button class="btn outline" type="button" data-x-action="radar-follow">+ Follow this search</button>'+
    '<button class="btn outline" type="button" data-x-action="radar-refresh">Refresh watched events</button></div>'+
    '<div id="x-radar-results">'+(xRadarEvents.length?xRadarResultsHtml(xRadarEvents):xNote('Search for an artist or event to see verified Ticketmaster results.'))+'</div>'+
    xPane('Your watched searches','Updates are checked when you click refresh; no scheduled background monitoring',
      saved.watches.length?saved.watches.map(w=>
        '<div class="x-watch-row"><div><b>'+xEsc(w.query)+'</b><small>'+xEsc(w.country||'Worldwide')+
        ' · Last checked: '+xEsc(w.last_checked?niceDate(w.last_checked):'Never')+'</small></div>'+
        '<button type="button" class="mini-btn" data-x-remove-watch="'+w.id+'">Remove</button></div>').join(''):
        '<p class="x-description">No watches yet. Enter an artist name above and choose Follow this search.</p>')+
    xPane('Discovered changes','Newly observed events and dates changed since the prior refresh',
      saved.hits.length?saved.hits.slice(0,16).map(h=>
        '<div class="x-watch-row"><div><b>'+xEsc(h.name)+'</b><small>'+
        xEsc(h.city)+' · '+xEsc(h.starts_at||'Date not confirmed')+'</small></div>'+
        xTag(h.status,h.status==='updated'?'warning':'green')+'</div>').join(''):
        '<p class="x-description">New events and changes will appear here after refreshing a watch.</p>')+
    xNote('Discovery listings are third-party source data. Verify all dates, admission terms and availability on Ticketmaster.');
}
function xRadarResultsHtml(rows){
  return '<section class="x-panel x-radar-results"><div class="x-panel-header"><div><h3>Ticketmaster results</h3><small>'+
    rows.length+' events</small></div></div><div class="x-radar-grid">'+rows.map(e=>
    '<article class="x-event-result"><div class="x-card-top"><span class="x-eyebrow">TICKETMASTER</span>'+
    xTag(e.category||'Event')+'</div><h3>'+xEsc(e.name)+'</h3>'+
    '<p>▤ '+xEsc(e.local_date||e.starts_at||'Date not confirmed')+'</p>'+
    '<p>⌾ '+xEsc([e.venue,e.city,e.country].filter(Boolean).join(' · ')||'Location unavailable')+'</p>'+
    '<div class="x-result-actions"><button class="btn primary" type="button" data-x-import="'+xEsc(e.id)+'" '+
    (!e.starts_at?'disabled title="UTC event time missing"':'')+'>Add to my calendar</button>'+
    (e.url?'<a href="'+xEsc(e.url)+'" target="_blank" rel="noopener noreferrer">Official event ↗</a>':'')+
    '</div></article>').join('')+'</div></section>';
}

async function xRadarSearch(){
  const query=$('#x-radar-query')?.value.trim()||'';
  const country=$('#x-radar-country')?.value||'';
  if(query.length<2)return;
  xRadarQuery=query;xRadarCountry=country;
  $('#x-radar-results').innerHTML='<div class="x-loading">Searching Ticketmaster Discovery API…</div>';
  try{
    const data=await api('/x/radar/search?q='+encodeURIComponent(query)+'&country='+encodeURIComponent(country));
    xRadarEvents=data.events||[];
    if(app.page==='radar')$('#x-radar-results').innerHTML=xRadarEvents.length?
      xRadarResultsHtml(xRadarEvents):'<div class="x-empty">No matching events found.</div>';
  }catch(error){
    $('#x-radar-results').innerHTML='<div class="x-api-error">'+xEsc(error.message)+'</div>';
  }
}
function xRadarSetKey(){
  openModal('Connect Ticketmaster Discovery API',[
    {name:'api_key',label:'Your Ticketmaster Discovery API key',type:'password',wide:true,required:true,
      placeholder:'Paste your private API key',help:'Stored encrypted in your own account. Never paste this key in chats or GitHub.'}
  ],async v=>{await api('/x/radar/key',{method:'PUT',body:v});notify('Ticketmaster API key encrypted and connected.');},'Save integration');
}

function initXPages(){
  $('#page-content').addEventListener('click',async event=>{
    const btn=event.target.closest('[data-x-action], [data-x-example], [data-x-import], [data-x-delivery], [data-x-goto], [data-x-remove-watch]');
    if(!btn)return;
    try{
      if(btn.dataset.xExample){$('#x-chat-question').value=btn.dataset.xExample;return xAskCopilot()}
      if(btn.dataset.xGoto)return navigate(btn.dataset.xGoto);
      if(btn.dataset.xDelivery)return xEditDelivery(Number(btn.dataset.xDelivery));
      if(btn.dataset.xImport){
        if(!confirm('Import this Ticketmaster event into your personal Ceyrl calendar?'))return;
        const done=await api('/x/radar/import/'+encodeURIComponent(btn.dataset.xImport),{method:'POST'});
        notify(done.already_exists?'Event already in your calendar.':'Event imported into your private calendar.');
        return navigate('events');
      }
      if(btn.dataset.xRemoveWatch){
        if(!confirm('Stop watching this event search?'))return;
        await api('/x/radar/watches/'+btn.dataset.xRemoveWatch,{method:'DELETE'});
        return renderXRadar();
      }
      const action=btn.dataset.xAction;
      if(action==='radar-key'||action==='x-radar-key')return xRadarSetKey();
      if(action==='x-refresh-shield')return renderXShield();
      if(action==='radar-follow'){
        const query=$('#x-radar-query').value.trim(),country=$('#x-radar-country').value;
        if(query.length<2)return notify('Enter an event or artist first.');
        await api('/x/radar/watches',{method:'POST',body:{query,country}});
        notify('Added to your private watchlist.');return renderXRadar();
      }
      if(action==='radar-refresh'){
        btn.disabled=true;
        const result=await api('/x/radar/refresh',{method:'POST'});
        notify('Radar refreshed: '+result.new+' new events, '+result.updated+' changed.');
        return renderXRadar();
      }
    }catch(error){notifyError(error)}
  });
  $('#page-content').addEventListener('submit',async event=>{
    if(event.target.id==='x-chat-form'){event.preventDefault();return xAskCopilot()}
    if(event.target.id==='x-radar-form'){event.preventDefault();return xRadarSearch()}
  });
}
initXPages();
