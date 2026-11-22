/* Ceyrl X — functional AI Copilot, Shield, Event Radar and Delivery Center UI. */
'use strict';

let xChatHistory=[];
let xRadarEvents=[];
let xRadarSource='Ticket Fairy public events';
let xRadarCoverage='';
let xRadarQuery='';
let xRadarCountry='';
let xRadarKind='all';
const xRadarPopularArtists=[
  'Noah Kahan','Nickelback','BTS','Coldplay','Post Malone','The Weeknd',
  'Morgan Wallen','Billie Eilish','Taylor Swift','Ed Sheeran','Dua Lipa',
  'Olivia Rodrigo','Imagine Dragons','Metallica','Harry Styles','Sabrina Carpenter',
  'Bad Bunny','KATSEYE','RAYE','Tame Impala','Sam Fender','Calin','BLACKPINK','Stray Kids'
];

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

async function renderXCopilot() {
  const content=$('#page-content');
  content.innerHTML=heading('Ceyrl AI Copilot',
    'Real GPT-5.4 mini conversations, with optional live web search and scoped inventory context.')+
    '<div class="x-loading">Checking your private AI connection…</div>';
  let status={configured:false,model:'gpt-5.4-mini',web_available:false};
  let history=[];
  try {
    [status,history]=await Promise.all([
      api('/x/copilot/status'),
      api('/x/copilot/history').then(r=>r.messages||[])
    ]);
  } catch(error) {
    console.warn('Ceyrl AI connection check failed',error);
  }
  if(app.page!=='copilot')return;
  xChatHistory=history.map(m=>({role:m.role,text:m.text,mode:m.mode||'ai'}));
  const enabled=Boolean(status.configured);
  content.innerHTML=heading('Ceyrl AI Copilot',
    'An intelligent assistant powered by GPT-5.4 mini. Ask questions in Slovak or English.')+
    '<section class="x-hero x-ai-hero"><div><span class="x-eyebrow">CEYRL / GPT-5.4 MINI</span>'+
    '<h2>Ask anything.<br><em>Get real answers.</em></h2>'+
    '<p>Talk naturally, ask follow-up questions and search the web for current information. '+
    'Your chat history is encrypted inside your private workspace.</p></div>'+
    '<span class="x-hero-decoration" aria-hidden="true">✦</span></section>'+
    '<div class="x-ai-status '+(enabled?'is-configured':'needs-key')+'">'+
      '<span class="x-ai-status-icon">'+(enabled?'✓':'!')+'</span><div><strong>'+
      (enabled?'GPT-5.4 mini API key configured':'GPT-5.4 mini is not configured yet')+'</strong><small>'+
      (enabled?'Online AI is ready to test. Live web search is '+
          (status.web_available?'available.':'disabled by the administrator.')+
          ' Actual connectivity is confirmed when the first answer succeeds.':
          'In Bot-Hosting.net → Environment, add CTW_OPENAI_API_KEY and restart your server. Offline rules cannot answer general knowledge or current-event questions.')+
      '</small></div></div>'+
    '<div class="x-chat-wrap">'+
    '<div class="x-chat-toolbar"><div><strong>Private conversation</strong>'+
    '<small>Model: '+xEsc(status.model||'gpt-5.4-mini')+
    ' · estimated usage this month: $'+Number(status.estimated_account_usage_usd||0).toFixed(4)+
    '</small></div><button type="button" class="btn outline" data-x-action="clear-chat">Clear conversation</button></div>'+
    '<div class="x-chat-messages" id="x-chat-messages" aria-live="polite"></div>'+
    '<div class="x-chat-examples">'+
    ['When is the next FIFA World Cup?','Ktoré moje lístky ešte nemajú PDF?','How much revenue did I record?','Are there any double-sale risks?']
      .map(q=>'<button class="x-example" type="button" data-x-example="'+xEsc(q)+'">'+xEsc(q)+'</button>').join('')+
    '</div><form id="x-chat-form" class="x-chat-form">'+
    '<textarea id="x-chat-question" placeholder="Ask anything about your tickets, events or the world…" rows="3" minlength="2" maxlength="500" required></textarea>'+
    '<div class="x-chat-controls x-copilot-options">'+
      '<label class="x-toggle-option"><input type="checkbox" id="x-use-online-ai" '+(enabled?'checked':'')+
        (enabled?'':' disabled')+'><span>Use GPT-5.4 mini</span></label>'+
      '<label class="x-toggle-option"><input type="checkbox" id="x-use-web-search" '+
        (enabled&&status.web_available?'checked':'')+
        (enabled&&status.web_available?'':' disabled')+'><span>Web search (may cost extra)</span></label>'+
      '<label class="x-toggle-option"><input type="checkbox" id="x-share-inventory" '+
        (enabled?'':'disabled')+'><span>Include ticket details</span></label>'+
    '</div><div class="x-chat-submit"><span class="x-chat-caption">Online AI is billed through the server API account. '+
      'The operator can set a usage limit.</span><button type="submit" class="btn primary" id="x-chat-send">'+
      (enabled?'Ask GPT-5.4 mini ↗':'Ask offline helper ↗')+'</button></div>'+
    '<small class="x-disclosure">When GPT is selected, your question, recent chat and aggregate account numbers are sent to OpenAI. '+
    'Enable “Include ticket details” only when needed; it additionally shares a limited preview of event names, dates and ticket lot fields. '+
    'The provider does not receive PDF bytes, saved email addresses, passwords or API keys. '+
    'Web search is limited to one tool call per answer. Answers are read-only and may be inaccurate; verify ticket rules and event dates.</small>'+
    '</form></div>';
  renderXChatMessages();
}

function renderXChatMessages(){
  const el=$('#x-chat-messages');if(!el)return;
  if(!xChatHistory.length){
    el.innerHTML='<div class="x-chat-start"><div class="x-chat-orb">✦</div><h3>Welcome to Ceyrl AI.</h3>'+
      '<p>Ask a real question. With GPT-5.4 mini configured, you can discuss current events, ticket operations and follow-ups in context.</p>'+
      xTag('Encrypted chat history','green')+'</div>';return;
  }
  el.innerHTML=xChatHistory.map(m=>
    '<div class="x-chat-bubble '+(m.role==='user'?'x-from-user':'x-from-assistant')+'"><span>'+
    (m.role==='user'?'YOU':'CEYRL '+(m.mode==='ai'?'· GPT-5.4 mini':'· OFFLINE HELPER'))+'</span><p>'+
    xEsc(m.text)+'</p>'+
    (Array.isArray(m.citations)&&m.citations.length?
      '<div class="x-chat-citations"><strong>Sources</strong>'+
        m.citations.filter(c=>/^https?:\/\//.test(c.url||'')).map(c=>
          '<a href="'+xEsc(c.url)+'" target="_blank" rel="noopener noreferrer">'+
          xEsc(c.title||'Source')+' ↗</a>').join('')+'</div>':'')+
    (m.notice?'<small>'+xEsc(m.notice)+'</small>':'')+
    (m.pages?.length?'<div class="x-chat-actions">'+m.pages.map(p=>
      '<button type="button" data-x-goto="'+xEsc(p)+'">'+xEsc(p.replaceAll('_',' '))+' ↗</button>').join('')+'</div>':'')+
    '</div>').join('');
  el.scrollTop=el.scrollHeight;
}

async function xAskCopilot(){
  const field=$('#x-chat-question'),button=$('#x-chat-send');
  const question=field?.value.trim();
  if(!question || question.length<2 || button.disabled)return;
  const useAI=$('#x-use-online-ai')?.checked||false;
  const webSearch=useAI&&Boolean($('#x-use-web-search')?.checked);
  const includeInventory=useAI&&Boolean($('#x-share-inventory')?.checked);
  button.disabled=true;
  xChatHistory.push({role:'user',text:question});
  field.value='';
  renderXChatMessages();
  try{
    const response=await api('/x/copilot',{method:'POST',body:{
      question,use_ai:useAI,web_search:webSearch,include_inventory:includeInventory
    }});
    xChatHistory.push({role:'assistant',mode:response.mode,text:response.answer,
      notice:response.notice,pages:response.pages,citations:response.citations});
    if(xChatHistory.length>60)xChatHistory=xChatHistory.slice(-60);
    renderXChatMessages();
    if(response.usage?.estimated_cost_usd!=null){
      const el=$('.x-chat-toolbar small');
      if(el)el.textContent=(response.model||'gpt-5.4-mini')+
        ' · last request estimate: $'+Number(response.usage.estimated_cost_usd).toFixed(4);
    }
  }catch(e){
    xChatHistory.push({role:'assistant',mode:'local',text:'The online AI request did not complete: '+
      (e.message||'Unknown error')+
      ' Check your API key, project billing or monthly request limit. No AI response was generated.'});
    renderXChatMessages();
    notifyError(e);
  }finally{
    button.disabled=false;
    field.focus();
  }
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
    '<button type="button" class="btn outline" data-x-action="x-refresh-shield">Refresh checks ↻</button>')+
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
    'Discover public events instantly, without any personal API key.')+
    '<section class="x-hero x-radar-hero"><div><span class="x-eyebrow">CEYRL / EVENT DISCOVERY</span>'+
    '<h2>Find concerts worldwide.<br><em>From BTS to Noah Kahan.</em></h2>'+
    '<p>Find tour dates for international artists, bands, K-pop, festivals and sports across public catalogs. No personal API key needed.</p>'+
    '</div><span class="x-hero-decoration" aria-hidden="true">⌾</span></section>'+
    '<div class="x-radar-status">'+xTag('No personal API key needed','neutral')+
    '<span>'+xEsc(status.provider)+'</span></div>'+
    '<p class="x-description x-radar-coverage">'+xEsc(status.coverage_note||'Only events listed by the source are available.')+'</p>'+
    '<form class="x-radar-form" id="x-radar-form"><input name="query" id="x-radar-query" minlength="2" maxlength="80" required '+
    'placeholder="Artist, club, competition or event…" value="'+xEsc(xRadarQuery)+'">'+
    '<select name="kind" id="x-radar-kind" aria-label="Event category">'+
    [['all','All events'],['music','Concerts & festivals'],['sports','Sports & football']]
      .map(([c,n])=>'<option value="'+c+'" '+(xRadarKind===c?'selected':'')+'>'+n+'</option>').join('')+
    '</select>'+
    '<select name="country" id="x-radar-country">'+
    [['','All countries'],['SK','Slovakia'],['CZ','Czechia'],['DE','Germany'],['AT','Austria'],['PL','Poland'],
     ['GB','United Kingdom'],['US','USA'],['FR','France'],['IT','Italy'],['ES','Spain'],['NL','Netherlands']]
       .map(([c,n])=>'<option value="'+c+'" '+(xRadarCountry===c?'selected':'')+'>'+n+'</option>').join('')+
    '</select><button class="btn primary" type="submit">Search events ↗</button></form>'+
    '<section class="x-radar-artists"><div class="x-radar-artists-header">'+
      '<strong>Quick-search popular artists</strong><small>Shortcuts only — tour dates must be verified</small></div>'+
      '<div class="x-radar-artist-chips">'+xRadarPopularArtists.map(a=>
        '<button type="button" class="x-radar-artist-chip" data-x-artist="'+xEsc(a)+'">'+
        xEsc(a)+'</button>').join('')+'</div></section>'+
    '<div class="x-search-actions"><button class="btn outline" type="button" data-x-action="radar-follow">+ Follow this search</button>'+
    '<button class="btn outline" type="button" data-x-action="radar-refresh">Refresh watched events</button></div>'+
    '<div id="x-radar-results">'+(xRadarEvents.length?xRadarResultsHtml(xRadarEvents):xNote('Enter an artist or event to search public listings. No personal API key required.'))+'</div>'+
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
    xNote('Coverage depends on the data source. Verify event date, ticket availability and transfer rules at the source.');
}
function xRadarResultsHtml(rows){
  return '<section class="x-panel x-radar-results"><div class="x-panel-header"><div><h3>Public event results</h3><small>'+
    rows.length+' events</small></div></div><div class="x-radar-grid">'+rows.map(e=>
    '<article class="x-event-result"><div class="x-card-top"><span class="x-eyebrow">'+xEsc(e.provider||xRadarSource)+'</span>'+
    xTag(e.category||'Event')+'</div><h3>'+xEsc(e.name)+'</h3>'+
    '<p>▤ '+xEsc(e.local_date||e.starts_at||'Date not confirmed')+'</p>'+
    '<p>⌾ '+xEsc([e.venue,e.city,e.country].filter(Boolean).join(' · ')||'Location unavailable')+'</p>'+
    '<div class="x-result-actions"><button class="btn primary" type="button" data-x-import="'+xEsc(e.id)+'" '+
    (!e.starts_at?'disabled title="UTC event time missing"':'')+'>Add to my calendar</button>'+
    (e.url?'<a href="'+xEsc(e.url)+'" target="_blank" rel="noopener noreferrer">View source ↗</a>':'')+
    '</div></article>').join('')+'</div></section>';
}

function xRadarExternalLinks(query){
  const safeQuery=encodeURIComponent(query||'');
  return '<section class="x-radar-external"><strong>Look for more dates from ticketing sites</strong>'+
    '<p>These are links to external search pages, not verified results in Ceyrl. '+
    'A missing result in Ceyrl does not mean the artist has no shows.</p>'+
    '<a target="_blank" rel="noopener noreferrer" href="https://www.ticketmaster.com/search?q='+safeQuery+
      '">Ticketmaster ↗</a>'+
    '<a target="_blank" rel="noopener noreferrer" href="https://www.songkick.com/search?query='+safeQuery+
      '">Songkick ↗</a>'+
    (/nations?\s*league|liga\s*n[áa]rodov/i.test(query)?
      '<a target="_blank" rel="noopener noreferrer" href="https://www.uefa.com/uefanationsleague/fixtures-results/">'+
      'UEFA Nations League fixtures ↗</a>':'')+
    '</section>';
}

async function xRadarSearch(){
  const query=$('#x-radar-query')?.value.trim()||'';
  const country=$('#x-radar-country')?.value||'';
  const kind=$('#x-radar-kind')?.value||'all';
  if(query.length<2)return;
  xRadarQuery=query;xRadarCountry=country;xRadarKind=kind;
  const resultPanel=$('#x-radar-results');
  if(!resultPanel)return;
  resultPanel.innerHTML='<div class="x-loading">Searching concert and event sources…</div>';
  try{
    const data=await api('/x/radar/search?q='+encodeURIComponent(query)+'&country='+encodeURIComponent(country)+'&kind='+encodeURIComponent(kind));
    xRadarEvents=data.events||[];
    xRadarSource=data.source||'Public catalogs';
    xRadarCoverage=data.coverage_note||'';
    if(app.page==='radar'){
      const sources=(data.sources_checked||[]).join(' + ');
      const unavailable=data.provider_warnings||[];
      const status='<p class="x-description x-radar-search-source">Live catalogs checked: '+
        xEsc(sources||xRadarSource)+'. '+xEsc(xRadarCoverage)+'</p>';
      // A broken backup provider is not a failed user search. Don't display a
      // prominent red error for every artist when Gigora answered successfully.
      const degraded=unavailable.length&&xRadarEvents.length===0?
        '<p class="x-radar-provider-note">Some extra catalogs were unavailable. '+
        'The available results may not cover all concerts.</p>':'';
      const results=xRadarEvents.length?
        xRadarResultsHtml(xRadarEvents):
        '<div class="x-empty">No confirmed matching tour dates in the catalogs that answered. '+
        'Try the links below to check other ticketing sources.</div>';
      const panel=$('#x-radar-results');
      if(panel)panel.innerHTML=status+degraded+results+xRadarExternalLinks(query);
    }
  }catch(error){
    const panel=$('#x-radar-results');
    if(panel){
      panel.innerHTML='<div class="x-api-error">Live event lookup is temporarily unavailable: '+
        xEsc(error.message||'Please try again shortly.')+'</div>'+
        xRadarExternalLinks(query);
    }
  }
}

function initXPages(){
  $('#page-content').addEventListener('click',async event=>{
    const btn=event.target.closest('[data-x-action], [data-x-example], [data-x-import], [data-x-delivery], [data-x-goto], [data-x-remove-watch], [data-x-artist]');
    if(!btn)return;
    try{
      if(btn.dataset.xArtist){
        $('#x-radar-query').value=btn.dataset.xArtist;
        $('#x-radar-kind').value='music';
        $('#x-radar-country').value='';
        return xRadarSearch();
      }
      if(btn.dataset.xExample){$('#x-chat-question').value=btn.dataset.xExample;return xAskCopilot()}
      if(btn.dataset.xGoto)return navigate(btn.dataset.xGoto);
      if(btn.dataset.xDelivery)return xEditDelivery(Number(btn.dataset.xDelivery));
      if(btn.dataset.xImport){
        if(!confirm('Import this event listing into your private Ceyrl calendar? Verify the date and source first.'))return;
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
      if(action==='clear-chat'){
        if(!confirm('Delete your encrypted Ceyrl AI chat history? This cannot be undone.'))return;
        await api('/x/copilot/history',{method:'DELETE'});
        xChatHistory=[];
        renderXChatMessages();
        notify('Your AI conversation history was cleared.');
        return;
      }
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
