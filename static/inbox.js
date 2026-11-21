/* Ceyrl Magic Inbox — encrypted draft review before any inventory modification. */
'use strict';

let magicInboxView={settings:null,drafts:[],events:[],selected:null,filter:'pending',busy:false};
const miEsc=(v)=>escapeHtml(v==null?'':v);
const miDate=(date)=>date?niceDate(date):'Unknown';
const miQuantity=(value)=>Number.isInteger(Number(value))&&Number(value)>0?Number(value):1;

function magicSummaryCard(draft){
  const c=draft.candidate||{};
  return '<button class="mi-mail-card" type="button" data-mi-review="'+Number(draft.id)+'">'+
    '<span class="mi-mail-icon">✉</span><span class="mi-mail-main">'+
      '<span class="mi-mail-kicker">'+miEsc(draft.sender||'Sender not identified')+
        ' · '+miDate(draft.created_at)+'</span>'+
      '<strong>'+miEsc(c.event_title||draft.subject||'Confirmation needs review')+'</strong>'+
      '<small>'+miEsc(draft.subject||'No subject')+'</small>'+
      '<span class="mi-mail-info">'+
        (c.date_hint?'▤ '+miEsc(c.date_hint)+' ':'')+
        (c.section?' · Section '+miEsc(c.section):'')+
        (draft.pdfs.length?' · '+draft.pdfs.length+' encrypted PDF(s)':'')+
      '</span></span><span class="mi-mail-right">'+
    '<span class="mi-state mi-'+miEsc(draft.status)+'">'+miEsc(draft.status)+'</span>'+
    '<span class="mi-open">Review ↗</span></span></button>';
}

async function renderInbox(){
  const page=$('#page-content');
  page.innerHTML=heading('Magic Inbox',
    'Turn emailed ticket purchase confirmations into reviewable, private ticket records.')+
    '<div class="mi-loading">Loading your encrypted inbox…</div>';
  let [settings,drafts,events]=await Promise.all([
    api('/inbox/settings'),api('/inbox/drafts'),api('/events')
  ]);
  if(app.page!=='inbox')return;
  magicInboxView={...magicInboxView,settings,drafts,events,selected:null};
  page.innerHTML=heading('Magic Inbox',
    'Purchase confirmations are extracted into private drafts. Nothing enters your ticket inventory until you approve it.')+
    '<section class="mi-hero"><div><span class="mi-kicker">CEYRL / PRIVATE PURCHASE IMPORT</span>'+
    '<h2>Forward it. Review it.<br><em>Save your tickets.</em></h2>'+
    '<p>From email confirmations to organized events in one review. Original messages and staged PDFs are encrypted in your account. Unknown details stay blank.</p></div>'+
    '<div class="mi-hero-stamp" aria-hidden="true"><span>✉</span><strong>MAGIC INBOX</strong></div></section>'+
    '<div class="mi-stats"><div><span>Awaiting review</span><strong>'+drafts.filter(x=>x.status==='pending').length+'</strong></div>'+
    '<div><span>Imported</span><strong>'+drafts.filter(x=>x.status==='imported').length+'</strong></div>'+
    '<div><span>Mail forwarding</span><strong>'+(settings.email_enabled?'Configured':'Setup needed')+'</strong></div></div>'+
    '<div class="mi-two-cols"><section class="mi-panel mi-forward"><div class="mi-panel-head">'+
    '<div><h3>Your private forwarding address</h3><p>Unique to your account, never shared with other users</p></div><span>✦</span></div>'+
    (settings.email_enabled?
      '<div class="mi-address"><code id="mi-alias">'+miEsc(settings.email)+'</code>'+
      '<button type="button" data-mi-action="copy" title="Copy address">Copy</button></div>'+
      '<p class="mi-note">Forward purchase confirmations to this address. Mailgun must deliver inbound mail to the configured webhook.</p>'+
      '<button type="button" class="mi-link-button" data-mi-action="rotate">Regenerate address · old one stops working</button>':
      '<div class="mi-disabled"><span>⌁</span><div><strong>Email receiving is not configured yet</strong>'+
      '<p>The server owner must configure an inbound domain and a signed Mailgun route. Meanwhile, import .eml files or paste confirmation text.</p></div></div>')+
    '</section><section class="mi-panel"><div class="mi-panel-head"><div><h3>Import a confirmation</h3>'+
    '<p>Works now, without configuring external email delivery</p></div><span>▣</span></div>'+
    '<form id="mi-upload-form" class="mi-upload-form"><label class="mi-dropzone">'+
    '<span class="mi-drop-icon">⇧</span><strong>Upload an email (.eml)</strong>'+
    '<small>Max 3 MB. Up to 3 PDFs are staged securely for review.</small>'+
    '<input id="mi-eml-file" type="file" accept=".eml,message/rfc822" required></label>'+
    '<button type="submit" class="btn primary">Extract email ↗</button></form>'+
    '<div class="mi-upload-sep"><span>or</span></div>'+
    '<button class="btn outline" type="button" data-mi-action="paste">Paste confirmation text</button>'+
    '</section></div>'+
    '<section class="mi-panel mi-inbox-list"><div class="mi-panel-head"><div><h3>Confirmation queue</h3>'+
    '<p>Review identified fields before creating ticket lots</p></div>'+
    '<div class="mi-pills"><button data-mi-filter="pending" class="mi-pill '+(magicInboxView.filter==='pending'?'on':'')+'">Pending</button>'+
    '<button data-mi-filter="imported" class="mi-pill '+(magicInboxView.filter==='imported'?'on':'')+'">Imported</button>'+
    '<button data-mi-filter="all" class="mi-pill '+(magicInboxView.filter==='all'?'on':'')+'">All</button></div></div>'+
    '<div id="mi-inbox-rows"></div></section>'+
    '<p class="mi-footer-note">Safety: forwarded emails can contain inaccurate or forged data. Check the original seller confirmation, event date and delivery rules before importing. Nothing is automatically listed or sold.</p>';
  magicRenderList();
}

function magicRenderList(){
  const list=$('#mi-inbox-rows');
  if(!list)return;
  const filter=magicInboxView.filter;
  const drafts=magicInboxView.drafts.filter(x=>filter==='all'||x.status===filter);
  list.innerHTML=drafts.length?
    drafts.map(magicSummaryCard).join(''):
    '<div class="mi-empty"><span>✉</span><strong>No '+miEsc(filter==='all'?'confirmations':filter+' confirmations')+' yet</strong>'+
    '<p>Upload an .eml file or paste a purchase confirmation to get started.</p></div>';
}

function magicPasteForm(){
  const page=$('#page-content');
  const section=document.createElement('section');
  section.className='mi-panel mi-paste-section';
  section.id='mi-paste-panel';
  section.innerHTML='<div class="mi-panel-head"><div><h3>Paste order confirmation</h3>'+
    '<p>Plain text only — it will be encrypted and scanned for ticket fields</p></div>'+
    '<button type="button" data-mi-action="close-paste" class="mi-close">×</button></div>'+
    '<form id="mi-paste-form" class="mi-paste-form">'+
    '<label>Subject<input name="subject" maxlength="300" placeholder="Your tickets for…"></label>'+
    '<label>Sender (optional)<input name="sender" maxlength="255" placeholder="Confirmation email sender"></label>'+
    '<label class="wide">Confirmation text<textarea name="body" rows="8" minlength="2" maxlength="36000" required placeholder="Paste the entire order confirmation text…"></textarea></label>'+
    '<div class="mi-form-actions"><button class="btn primary" type="submit">Extract and review ↗</button></div></form>';
  page.querySelector('.mi-two-cols').after(section);
  section.querySelector('textarea').focus();
  section.scrollIntoView({behavior:'smooth',block:'center'});
}

function miSelectOpts(items,current){
  return items.map(([value,label])=>
    '<option value="'+miEsc(value)+'" '+(String(value)===String(current)?'selected':'')+'>'+
    miEsc(label)+'</option>').join('');
}

async function magicReviewDraft(id){
  const page=$('#page-content');
  const data=await api('/inbox/drafts/'+Number(id));
  if(app.page!=='inbox')return;
  magicInboxView.selected=data;
  page.querySelector('#mi-review-panel')?.remove();
  const candidate=data.candidate||{};
  const canImport=data.status==='pending';
  const isoDate=candidate.local_date||'';
  const isoTime=candidate.local_time||'';
  const dateValue=isoDate?(isoDate+'T'+(isoTime||'19:00')):'';
  const options=[['','Create a new event'],...magicInboxView.events.map(e=>[String(e.id),e.title+' · '+miDate(e.starts_at)])];
  const region=document.createElement('section');
  region.className='mi-review mi-panel';region.id='mi-review-panel';
  const warnings=(candidate.warnings||[]).map(w=>'<li>'+miEsc(w)+'</li>').join('');
  region.innerHTML='<div class="mi-panel-head"><div><span class="mi-kicker">MESSAGE #'+Number(data.id)+'</span>'+
    '<h3>'+miEsc(data.subject||'Ticket confirmation')+'</h3><p>From: '+miEsc(data.sender||'Unknown')+'</p></div>'+
    '<button type="button" data-mi-action="close-review" class="mi-close">×</button></div>'+
    '<div class="mi-review-body">'+
    '<div class="mi-review-banner"><span>✦</span><div><strong>Human verification required</strong>'+
    '<p>Detected fields are only suggestions. Complete or correct them; no ticket is created automatically.</p></div>'+
    '<span class="mi-confidence">'+miEsc(candidate.confidence||'manual_review').replaceAll('_',' ')+'</span></div>'+
    (data.status!=='pending'?'<div class="mi-imported-note">This message has been '+miEsc(data.status)+
     '. Event #'+miEsc(data.event_id||'—')+' · Ticket lot #'+miEsc(data.ticket_id||'—')+'</div>':'')+
    (canImport?'<form id="mi-approve-form" data-draft-id="'+Number(data.id)+'">'+
    '<div class="mi-review-grid">'+
    '<label class="wide">Add tickets to<select name="existing_event_id" id="mi-existing-event">'+
      miSelectOpts(options,'')+'</select></label>'+
    '<label class="wide">Event or artist name<input name="event_title" required maxlength="200" value="'+miEsc(candidate.event_title)+'" placeholder="Confirm event name"></label>'+
    '<label>Event date and local time<input name="local_start" type="datetime-local" required value="'+miEsc(dateValue)+'"></label>'+
    '<label>Venue<input name="venue" maxlength="200" value="'+miEsc(candidate.venue)+'" placeholder="Arena / Stadium"></label>'+
    '<label>City<input name="city" maxlength="120" value="'+miEsc(candidate.city)+'"></label>'+
    '<label>Country<input name="country" maxlength="100" placeholder="Country where event takes place"></label>'+
    '<label>Event category<select name="category">'+miSelectOpts([['Concert','Concert'],['Sports','Sports'],['Festival','Festival'],['Theatre','Theatre'],['Other','Other']],'Concert')+'</select></label>'+
    '<label>Ticket provider<input name="provider" maxlength="100" value="'+miEsc(candidate.provider)+'" placeholder="Ticketmaster / Eventim / AXS"></label>'+
    '<label>Ticket type<select name="ticket_type">'+miSelectOpts([
      ['E-Ticket','E-Ticket'],['Mobile Transfer','Mobile Transfer'],['PDF','PDF'],
      ['Physical','Physical']], 'E-Ticket')+'</select></label>'+
    '<label>Section<input name="section" maxlength="100" value="'+miEsc(candidate.section)+'"></label>'+
    '<label>Row<input name="row_label" maxlength="70" value="'+miEsc(candidate.row_label)+'"></label>'+
    '<label>Seats<input name="seats" maxlength="150" value="'+miEsc(candidate.seats)+'"></label>'+
    '<label>Number of tickets<input type="number" name="quantity" min="1" max="1000" required value="'+miQuantity(candidate.quantity)+'"></label>'+
    '<label>Purchase price / ticket<input name="purchase_price" type="number" step=".01" min="0" required value="'+miEsc(candidate.purchase_price||'0')+'"></label>'+
    '<label>Currency<select name="currency">'+miSelectOpts([
      ['EUR','EUR'],['USD','USD'],['GBP','GBP'],['CZK','CZK'],['PLN','PLN'],['CHF','CHF']
    ],candidate.currency||'EUR')+'</select></label>'+
    '</div>'+
    '<div class="mi-review-notes"><div><strong>Extracted from email</strong>'+
      '<p>Original date: '+miEsc([candidate.date_hint,candidate.time_hint].filter(Boolean).join(' '))+
      ' · Order total: '+miEsc(candidate.total_price||'Not provided')+' '+miEsc(candidate.currency||'')+
      '</p></div>'+
    (warnings?'<ul>'+warnings+'</ul>':'')+
    '</div>'+
    (data.pdfs.length?
      '<div class="mi-pdf-box"><div><strong>Encrypted PDF attachments</strong><small>'+
      data.pdfs.map(x=>miEsc(x.filename)).join(', ')+'</small></div>'+
      '<label><input type="checkbox" name="include_pdfs" checked> Attach to approved ticket</label></div>':
      '<p class="mi-footer-note">No PDF attachment was detected. If needed, you can upload it to the ticket vault later.</p>')+
    '<label class="mi-confirm-checkbox"><input type="checkbox" name="verified" required>'+
      'I checked the event, exact date/time, tickets, purchase price and transfer restrictions against the original confirmation.</label>'+
    '<div class="mi-form-actions"><button type="submit" class="btn primary" id="mi-import-button">Confirm and create tickets ↗</button>'+
    '<button type="button" class="btn outline" data-mi-dismiss="'+Number(data.id)+'">Dismiss draft</button></div>'+
    '</form>':'')+
    '<div class="mi-record-controls"><button class="mi-link-button" type="button" data-mi-delete="'+Number(data.id)+'">Delete inbox record</button>'+
    '<span>Deleting the inbox record does not delete already imported tickets.</span></div>'+
    '<details class="mi-original"><summary>Show original email text (private)</summary><pre>'+
      miEsc(data.body_preview||'No text was available.')+'</pre></details>'+
    '</div>';
  const base=page.querySelector('.mi-inbox-list')||page.lastElementChild;
  base.after(region);
  region.scrollIntoView({behavior:'smooth',block:'start'});
  const sel=region.querySelector('#mi-existing-event');
  if(sel)sel.addEventListener('change',()=>{
    const e=magicInboxView.events.find(x=>x.id===Number(sel.value));
    if(!e)return;
    const form=region.querySelector('#mi-approve-form');
    form.elements.event_title.value=e.title;
    form.elements.venue.value=e.venue||'';
    form.elements.city.value=e.city||'';
    form.elements.country.value=e.country||'';
    if(e.starts_at){
      const d=new Date(e.starts_at);
      if(Number.isFinite(+d)){
        form.elements.local_start.value=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);
      }
    }
  });
}

async function miImport(event){
  const form=event.target;
  const confirmBtn=form.querySelector('#mi-import-button');
  if(confirmBtn.disabled)return;
  const fields=Object.fromEntries(new FormData(form).entries());
  if(!fields.verified)throw Error('Confirm you reviewed the original order details.');
  if(!fields.local_start)throw Error('Event date and time are required.');
  const payload={
    event_title:String(fields.event_title||'').trim(),
    starts_at:isoLocal(fields.local_start),
    existing_event_id:fields.existing_event_id?Number(fields.existing_event_id):null,
    venue:fields.venue||'',city:fields.city||'',country:fields.country||'',
    category:fields.category||'Concert',provider:fields.provider||'',ticket_type:fields.ticket_type||'E-Ticket',
    section:fields.section||'',row_label:fields.row_label||'',seats:fields.seats||'',
    quantity:Number(fields.quantity),purchase_price:fields.purchase_price,
    currency:fields.currency||'EUR',include_pdfs:Boolean(fields.include_pdfs)
  };
  if(!Number.isInteger(payload.quantity)||payload.quantity<1)throw Error('Enter a valid ticket quantity.');
  if(!confirm('Create the event and ticket lot from these reviewed details?'))return;
  confirmBtn.disabled=true;
  try{
    const data=await api('/inbox/drafts/'+Number(form.dataset.draftId)+'/import',{method:'POST',body:payload});
    notify('Imported ticket lot #'+data.ticket_id+' with '+data.attached_pdfs+' encrypted PDFs.');
    await renderInbox();
  }finally{confirmBtn.disabled=false}
}

function initMagicInbox(){
  const root=$('#page-content');
  root.addEventListener('submit',async event=>{
    if(!['mi-upload-form','mi-paste-form','mi-approve-form'].includes(event.target.id))return;
    event.preventDefault();
    if(magicInboxView.busy)return;
    magicInboxView.busy=true;
    try{
      if(event.target.id==='mi-upload-form'){
        const file=$('#mi-eml-file')?.files?.[0];
        if(!file)throw Error('Choose an email .eml file.');
        if(file.size>3*1024*1024)throw Error('Email file exceeds 3 MB.');
        const form=new FormData();form.append('file',file);
        const result=await api('/inbox/upload',{method:'POST',body:form});
        notify(result.duplicate?'This confirmation was already imported to your inbox.':'Email extracted into a private draft.');
        await renderInbox();
        await magicReviewDraft(result.id);
      }else if(event.target.id==='mi-paste-form'){
        const inputs=Object.fromEntries(new FormData(event.target).entries());
        const result=await api('/inbox/paste',{method:'POST',body:inputs});
        notify(result.duplicate?'This confirmation is already in your inbox.':'Confirmation saved as a private draft.');
        await renderInbox();await magicReviewDraft(result.id);
      }else{
        await miImport(event);
      }
    }catch(error){notifyError(error)}
    finally{magicInboxView.busy=false}
  });
  root.addEventListener('click',async event=>{
    const button=event.target.closest('[data-mi-action],[data-mi-review],[data-mi-filter],[data-mi-dismiss],[data-mi-delete]');
    if(!button)return;
    try{
      if(button.hasAttribute('data-mi-review')){
        return magicReviewDraft(Number(button.dataset.miReview));
      }
      if(button.hasAttribute('data-mi-filter')){
        magicInboxView.filter=button.dataset.miFilter;
        root.querySelectorAll('[data-mi-filter]').forEach(el=>el.classList.toggle('on',el===button));
        return magicRenderList();
      }
      if(button.hasAttribute('data-mi-dismiss')){
        if(!confirm('Dismiss this draft? Staged PDFs will be deleted.'))return;
        await api('/inbox/drafts/'+Number(button.dataset.miDismiss)+'/dismiss',{method:'POST'});
        notify('Draft dismissed.');return renderInbox();
      }
      if(button.hasAttribute('data-mi-delete')){
        if(!confirm('Permanently delete this inbox record? Any already imported ticket will remain untouched.'))return;
        await api('/inbox/drafts/'+Number(button.dataset.miDelete),{method:'DELETE'});
        notify('Inbox record deleted.');return renderInbox();
      }
      if(button.dataset.miAction==='paste'){
        if(!root.querySelector('#mi-paste-panel'))magicPasteForm();
      }else if(button.dataset.miAction==='close-paste'){
        root.querySelector('#mi-paste-panel')?.remove();
      }else if(button.dataset.miAction==='close-review'){
        root.querySelector('#mi-review-panel')?.remove();
      }else if(button.dataset.miAction==='copy'){
        if(!magicInboxView.settings?.email)return;
        await navigator.clipboard.writeText(magicInboxView.settings.email);
        notify('Your private inbox address was copied.');
      }else if(button.dataset.miAction==='rotate'){
        if(!confirm('Generate a new forwarding email address? All mail sent to the old address will be rejected.'))return;
        await api('/inbox/rotate',{method:'POST'});
        notify('Your forwarding address was replaced.');
        return renderInbox();
      }
    }catch(error){notifyError(error)}
  });
}
initMagicInbox();
