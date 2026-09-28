const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const state = { leads: [], reminders: [], dashboard: null, activeView: 'dashboard' };
const statuses = ['NEW','CONTACTED','QUALIFIED','QUOTE_SENT','WAITING','WON','LOST'];
const statusLabels = {NEW:'New',CONTACTED:'Contacted',QUALIFIED:'Qualified',QUOTE_SENT:'Quote sent',WAITING:'Waiting',WON:'Won',LOST:'Lost'};

async function api(path, options={}) {
  const res = await fetch(path, {headers:{'Content-Type':'application/json',...(options.headers||{})}, ...options});
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
function money(v){ return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Number(v||0)); }
function dateText(v){ if(!v) return '—'; const d=new Date(v); return d.toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}); }
function relative(v){ if(!v) return '—'; const diff=Date.now()-new Date(v).getTime(); const h=Math.round(diff/36e5); if(h<1)return 'just now'; if(h<24)return `${h}h ago`; const d=Math.round(h/24);return `${d}d ago`; }
function escapeHtml(s=''){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function toast(msg){ const el=$('#toast'); el.textContent=msg; el.classList.add('show'); clearTimeout(toast.t); toast.t=setTimeout(()=>el.classList.remove('show'),2500); }
function badge(status){return `<span class="badge ${status}">${statusLabels[status]||status}</span>`}

async function refreshAll(){
  const [dash, leads, rem, health] = await Promise.all([api('/api/dashboard'), api('/api/leads'), api('/api/reminders'), api('/api/health')]);
  state.dashboard=dash; state.leads=leads.leads; state.reminders=rem.reminders;
  $('#aiModeBadge').textContent = health.ai_mode==='openai' ? `AI · ${health.model}` : 'AI · Demo fallback';
  renderDashboard(); renderLeads(); renderReminders();
}

function renderDashboard(){
  const d=state.dashboard;
  $('#metricTotal').textContent=d.total_leads;
  $('#metricQuotes').textContent=d.active_quotes;
  $('#metricOverdue').textContent=d.overdue_followups;
  $('#metricWon').textContent=money(d.won_value);
  $('#followupNavCount').textContent=state.reminders.length;
  const max=Math.max(...Object.values(d.pipeline),1);
  $('#pipelineBars').innerHTML=statuses.map(s=>`<div class="pipeline-row"><label>${statusLabels[s]}</label><div class="bar-track"><div class="bar-fill" style="width:${(d.pipeline[s]/max)*100}%"></div></div><b>${d.pipeline[s]}</b></div>`).join('');
  $('#activityList').innerHTML=d.recent_activities.length?d.recent_activities.map(a=>`<div class="activity-item"><span class="activity-dot"></span><div><strong>${escapeHtml(a.lead_name)} · ${escapeHtml(a.type.replaceAll('_',' ').toLowerCase())}</strong><p>${escapeHtml(a.note)}</p><time>${relative(a.created_at)}</time></div></div>`).join(''):'<p class="subtext">No activity yet.</p>';
  const risk=state.leads.filter(l=>['QUOTE_SENT','WAITING'].includes(l.status)).sort((a,b)=>new Date(a.next_followup_at||'9999')-new Date(b.next_followup_at||'9999')).slice(0,5);
  $('#riskTable').innerHTML=tableHtml(risk,true);
}
function tableHtml(leads, risk=false){
  if(!leads.length)return '<div class="subtext" style="padding:18px">No leads found.</div>';
  return `<table class="data-table"><thead><tr><th>Lead</th><th>Service</th><th>Status</th><th>Priority</th><th>${risk?'Follow-up':'Created'}</th><th>Value</th></tr></thead><tbody>${leads.map(l=>`<tr data-lead="${l.id}"><td><span class="lead-name">${escapeHtml(l.name)}</span><span class="subtext">${escapeHtml(l.company||l.email)}</span></td><td>${escapeHtml(l.service||'—')}</td><td>${badge(l.status)}</td><td><span class="priority ${l.priority}">${l.priority}</span></td><td>${risk?dateText(l.next_followup_at):relative(l.created_at)}</td><td>${l.quote_amount?money(l.quote_amount):(l.budget?`~${money(l.budget)}`:'—')}</td></tr>`).join('')}</tbody></table>`;
}
function renderLeads(){
  const search=($('#leadSearch')?.value||'').toLowerCase(); const filter=$('#statusFilter')?.value||'';
  const leads=state.leads.filter(l=>(!filter||l.status===filter)&&(!search||[l.name,l.email,l.company,l.service].join(' ').toLowerCase().includes(search)));
  $('#leadsTable').innerHTML=tableHtml(leads,false);
}
function renderReminders(){
  $('#followupNavCount').textContent=state.reminders.length;
  $('#reminderGrid').innerHTML=state.reminders.length?state.reminders.map(r=>`<article class="reminder-card"><div class="reminder-top"><div><span class="eyebrow ${new Date(r.due_at)<new Date()?'accent':''}">${new Date(r.due_at)<new Date()?'OVERDUE':'UPCOMING'}</span><h3>${escapeHtml(r.lead_name)}</h3><div class="meta">${escapeHtml(r.lead_company||r.lead_email)} · ${escapeHtml(r.lead_service||'Service inquiry')}</div></div><div>${r.quote_amount?money(r.quote_amount):''}</div></div><div class="draft-box">${escapeHtml(r.generated_draft||'No draft yet.')}</div><div class="card-actions"><button class="btn secondary copy-draft" data-id="${r.id}">Copy draft</button><button class="btn primary complete-reminder" data-id="${r.id}">Mark followed up</button></div></article>`).join(''):'<article class="panel"><strong>Queue is clear.</strong><p class="subtext">No open follow-up reminders right now.</p></article>';
}
function switchView(view){
  state.activeView=view; $$('.view').forEach(v=>v.classList.remove('active')); $(`#${view}View`).classList.add('active');
  $$('.nav-item[data-view]').forEach(n=>n.classList.toggle('active',n.dataset.view===view));
  $('#pageTitle').textContent={dashboard:'Lead Rescue Dashboard',leads:'Lead Pipeline',followups:'Follow-up Queue'}[view];
}
async function openLead(id){
  const l=await api(`/api/leads/${id}`); const d=$('#leadDialog');
  $('#leadDetail').innerHTML=`<div class="modal-head"><div><span class="eyebrow">LEAD #${l.id}</span><h3>${escapeHtml(l.name)}</h3></div><button class="icon-btn" onclick="document.getElementById('leadDialog').close()">×</button></div><div class="detail-grid"><div class="detail-main"><h2>${escapeHtml(l.company||'Individual inquiry')}</h2><div class="lead-email">${escapeHtml(l.email)}${l.phone?` · ${escapeHtml(l.phone)}`:''}</div><div class="detail-section"><h4>Customer need</h4><p>${escapeHtml(l.message||'No message provided.')}</p></div><div class="detail-section"><h4>AI lead brief</h4><div class="ai-box" id="aiSummaryBox">${escapeHtml(l.ai_summary||'No summary generated yet.')}</div><button class="btn secondary" style="margin-top:10px" id="genSummaryBtn">Generate AI summary</button></div><div class="detail-section"><h4>Activity timeline</h4><div class="timeline">${(l.activities||[]).map(a=>`<div class="timeline-item"><span class="dot"></span><div><strong>${escapeHtml(a.type.replaceAll('_',' '))}</strong><p>${escapeHtml(a.note)} · ${relative(a.created_at)}</p></div></div>`).join('')||'<span class="subtext">No activity.</span>'}</div></div></div><aside class="side-stack"><div class="side-card"><label>Status</label>${badge(l.status)}<select class="select status-select" id="leadStatus">${statuses.map(s=>`<option value="${s}" ${s===l.status?'selected':''}>${statusLabels[s]}</option>`).join('')}</select></div><div class="side-card"><label>Service</label><strong>${escapeHtml(l.service||'—')}</strong></div><div class="side-card"><label>Budget signal</label><strong>${l.budget?money(l.budget):'Not provided'}</strong></div><div class="side-card"><label>Quote</label><strong>${l.quote_amount?money(l.quote_amount):'Not sent'}</strong><div class="quote-form"><input id="quoteAmount" type="number" min="1" placeholder="Amount" value="${l.quote_amount||''}"><button class="btn primary" id="sendQuoteBtn">Set quote</button></div></div><div class="side-card"><label>Next follow-up</label><strong>${dateText(l.next_followup_at)}</strong><button class="btn secondary full" style="margin-top:10px" id="draftBtn">Draft follow-up</button></div></aside></div>`;
  d.showModal();
  $('#leadStatus').addEventListener('change',async e=>{await api(`/api/leads/${id}/status`,{method:'POST',body:JSON.stringify({status:e.target.value})});toast('Status updated');await refreshAll();d.close();});
  $('#genSummaryBtn').addEventListener('click',async()=>{const b=$('#genSummaryBtn');b.disabled=true;b.textContent='Generating…';try{const r=await api(`/api/leads/${id}/ai-summary`,{method:'POST',body:'{}'});$('#aiSummaryBox').textContent=r.summary;toast('AI summary ready');await refreshAll();}finally{b.disabled=false;b.textContent='Generate AI summary';}});
  $('#sendQuoteBtn').addEventListener('click',async()=>{const amount=Number($('#quoteAmount').value);if(!amount)return toast('Enter a quote amount');await api(`/api/leads/${id}/quote`,{method:'POST',body:JSON.stringify({amount,followup_days:2})});toast('Quote tracked and follow-up scheduled');await refreshAll();d.close();});
  $('#draftBtn').addEventListener('click',async()=>{const r=await api(`/api/leads/${id}/followup-draft`,{method:'POST',body:'{}'});await navigator.clipboard.writeText(r.draft);toast('Follow-up draft copied');});
}
async function runAutomation(){ const r=await api('/api/automation/run',{method:'POST',body:'{}'}); toast(r.created?`${r.created} follow-up reminder created`:'No new overdue quotes'); await refreshAll(); }

$('#newLeadBtn').addEventListener('click',()=>$('#newLeadDialog').showModal());
$$('[data-close]').forEach(b=>b.addEventListener('click',()=>document.getElementById(b.dataset.close).close()));
$('#newLeadForm').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);const obj=Object.fromEntries(fd.entries());try{await api('/api/leads',{method:'POST',body:JSON.stringify(obj)});e.target.reset();$('#newLeadDialog').close();toast('Lead added');await refreshAll();}catch(err){toast(err.message)}});
$('#runAutomationBtn').addEventListener('click',runAutomation); $('#runAutomationBtn2').addEventListener('click',runAutomation);
$$('.nav-item[data-view]').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));
$$('[data-view-target]').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.viewTarget)));
$('#leadSearch').addEventListener('input',renderLeads); $('#statusFilter').innerHTML += statuses.map(s=>`<option value="${s}">${statusLabels[s]}</option>`).join(''); $('#statusFilter').addEventListener('change',renderLeads);
document.addEventListener('click',async e=>{const row=e.target.closest('[data-lead]');if(row)return openLead(Number(row.dataset.lead));const copy=e.target.closest('.copy-draft');if(copy){const r=state.reminders.find(x=>x.id===Number(copy.dataset.id));if(r){await navigator.clipboard.writeText(r.generated_draft||'');toast('Draft copied');}}const done=e.target.closest('.complete-reminder');if(done){await api(`/api/reminders/${done.dataset.id}/complete`,{method:'POST',body:'{}'});toast('Follow-up marked complete');await refreshAll();}});
refreshAll().catch(err=>toast(err.message));
