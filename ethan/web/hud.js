'use strict';
const $ = id => document.getElementById(id);
let accessToken = '', authRequired = false, authEpoch = 0;
const WIDGETS = ['agents', 'tasks', 'approvals', 'activity'];
const DEFAULTS = {version: 1, motion: false, spoken: false, theme: 'dark', widgets: WIDGETS};
let prefs = {...DEFAULTS}, online = false, latest = null, sending = false, after = 0, historyLoaded = false;
let voice = {supported: false, muted: true, state: 'unavailable'}, lastTranscript = '', speaking = false, pttHeld = false;
function loadPrefs() {
  try { const p = JSON.parse(localStorage.getItem('ethan.display.v1'));
    if (p && p.version === 1 && typeof p.motion === 'boolean' && typeof p.spoken === 'boolean' && Array.isArray(p.widgets))
      prefs = {version: 1, motion: p.motion, spoken: p.spoken, theme: p.theme === 'light' ? 'light' : 'dark', widgets: WIDGETS.filter(w => p.widgets.includes(w))};
  } catch (_) { /* Corrupt storage falls back to a safe fixed layout. */ }
}
function applyPrefs() {
  document.body.classList.toggle('reduce-motion', prefs.motion);
  document.body.classList.toggle('light-theme', prefs.theme === 'light');
  $('theme-toggle').textContent = prefs.theme === 'light' ? 'Dark theme' : 'Light theme';
  $('theme-toggle').setAttribute('aria-pressed', String(prefs.theme === 'light'));
  $('motion').checked = prefs.motion; $('spoken').checked = prefs.spoken;

  try { localStorage.setItem('ethan.display.v1', JSON.stringify(prefs)); } catch (_) { $('send-state').textContent = 'Browser storage unavailable; preferences last this session.'; }
}
async function api(path, body) {
  const epoch = authEpoch;
  const headers = {...(body === undefined ? {} : {'Content-Type':'application/json'}), ...(accessToken ? {Authorization:'Bearer '+accessToken} : {})};
  const r = await fetch(path, {cache:'no-store', redirect:'error', signal:AbortSignal.timeout(10000), headers, ...(body === undefined ? {} : {method:'POST', body:JSON.stringify(body)})});
  if(epoch!==authEpoch)throw new Error('Access changed; stale response discarded');
  if(r.status===401){authRequired=true;$('auth-form').hidden=false;throw new Error('Local API authentication required');}
  const data=await r.json(); if(epoch!==authEpoch)throw new Error('Access changed; stale response discarded'); if(!r.ok)throw new Error(data.error || `Request refused (${r.status})`);
  authRequired=false;$('auth-form').hidden=true;return data;
}
function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
function empty(el, text) { el.replaceChildren(node('p', text, 'empty')); }
function when(ts) { return ts ? new Date(ts * 1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'No timestamp'; }
function bubble(text, role) {
  const m = node('div', undefined, 'message ' + (role === 'user' ? 'user' : 'assistant'));
  m.append(node('span', role === 'user' ? 'YOU' : 'ETHAN', 'speaker'), document.createTextNode(text));
  $('feed').append(m); while ($('feed').children.length > 120) $('feed').firstChild.remove(); $('feed').scrollTop = $('feed').scrollHeight;
}
function speak(text) {
  if (!prefs.spoken || !('speechSynthesis' in window)) return;
  const localVoice = speechSynthesis.getVoices().find(v => v.localService && v.lang.startsWith('en'));
  if (!localVoice) { $('voice-detail').textContent = 'No local browser voice is available; reply remains text.'; return; }
  const u = new SpeechSynthesisUtterance(text.slice(0, 2500)); u.voice = localVoice;
  u.onstart = () => { speaking = true; coreState(); }; u.onend = u.onerror = () => { speaking = false; coreState(); };
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}
function coreState() {
  let state = authRequired ? 'locked' : !online ? 'offline' : latest?.presence || 'ready';
  if (online && latest?.approvals?.length) state = 'approval';
  if (online && ['starting','wake-listening','listening','transcribing'].includes(voice.state)) state = ['listening','wake-listening'].includes(voice.state) ? voice.state : 'handling';
  if (speaking) state = 'speaking';
  const labels = {locked:['Access locked','Enter the service owner-provided token to access local data and controls.'],'wake-listening':['Wake listening','Microphone on locally. Say hey Ethan; expires after 60 seconds.'],offline:['Offline','Waiting for the local service. Records may be stale.'], ready:['Ready when you are','Your next move starts here.'], handling:['Thinking it through','The local coordinator is handling your request.'], working:['Work in progress','Follow the recorded task and relay states below.'], approval:['Your decision is needed','Review the exact request before you approve it.'], listening:['Listening',voice.wake_enabled?'Use Finish transcript to review your words. Nothing is sent automatically.':'Release to preview your words. Nothing is sent automatically.'], speaking:['Speaking','Reading the reply with a local voice.']};
  const label = labels[state] || labels.ready;
  $('core').dataset.state = state; $('core-state').textContent = state.toUpperCase(); $('core-title').textContent = label[0]; $('core-detail').textContent = label[1];
}
const responseRequests = new Map();
let unresolvedSubmission = null;
const responseTerminal = new Set(['completed','failed','cancelled','interrupted']);
function saveResponseIds() {
  try { sessionStorage.setItem('ethan.response.ids.v1', JSON.stringify([...responseRequests.keys()])); } catch (_) {}
}
function restoreResponseIds() {
  try { const ids=JSON.parse(sessionStorage.getItem('ethan.response.ids.v1'));
    if(Array.isArray(ids)) for(const id of ids.slice(-8)) if(typeof id==='string'&&/^[a-f0-9]{32}$/.test(id)) responseRequests.set(id,{id,state:'reconnecting',after:0});
  } catch (_) {}
}
function renderResponseRequests() {
  const box=$('response-requests');box.replaceChildren();
  for(const [id,r] of responseRequests) {
    const row=node('div',undefined,'response-request');
    row.append(node('strong',`${id.slice(0,8)} / ${r.state}`));
    const capability=r.capabilities||{};
    row.append(node('p',capability.live_text_deltas===true?'Live answer transport available.': 'Final reply only · text is checked before display.'));
    if(r.notice)row.append(node('p',r.notice));
    if(!responseTerminal.has(r.state)) {
      const stop=node('button','Stop tracking','quiet');stop.type='button';
      stop.title='Stops local delivery tracking. An already dispatched agent or action may continue.';
      stop.onclick=async()=>{stop.disabled=true;try{const updated=await api('/api/requests/cancel',{request_id:id});if(responseRequests.get(id)!==r)return;responseRequests.set(id,{...r,...updated,latestAfter:updated.after,after:r.after,notice:updated.state==='cancelled'?'Local tracking stopped. Already dispatched work may continue.':r.notice});if(unresolvedSubmission===id)unresolvedSubmission=null;renderResponseRequests();}catch(e){r.notice=e.message+' No remote stop is confirmed.';renderResponseRequests();}};
      row.append(stop);
    }
    const dismiss=node('button',r.state==='unknown'?'Dismiss uncertain tracking':'Dismiss','quiet');dismiss.type='button';
    dismiss.disabled=!responseTerminal.has(r.state)&&r.state!=='unknown';
    dismiss.onclick=()=>{responseRequests.delete(id);if(unresolvedSubmission===id)unresolvedSubmission=null;saveResponseIds();renderResponseRequests();$('send-state').textContent='Tracking dismissed. This does not cancel dispatched work; check activity before sending again.';};row.append(dismiss);box.append(row);
  }
}
async function refreshResponses() {
  for(const [id,r] of [...responseRequests]) {
    if(responseTerminal.has(r.state)&&r.after>=(r.latestAfter??r.after))continue;
    try {
      const data=await api('/api/requests?request_id='+id+'&after='+r.after);
      if(responseRequests.get(id)!==r)continue;
      let notice=r.notice;
      for(const event of data.events||[]) {
        if(!Number.isInteger(event.seq)||event.seq<=r.after)continue;
        r.after=event.seq;
        if(['status','error','cancelled','interrupted'].includes(event.kind)&&typeof event.text==='string')notice=event.text.slice(0,400);
      }
      responseRequests.set(id,{...r,...data.request,notice,latestAfter:data.request.after,after:r.after});
      if(unresolvedSubmission===id)unresolvedSubmission=null;
    } catch(e) {
      if(responseRequests.get(id)!==r)continue;
      r.state='unknown';r.notice='Delivery state unavailable. No resend was attempted. '+e.message;
    }
  }
  renderResponseRequests();
}
async function send(text) {
  if(sending || !text.trim()) return;
  if(unresolvedSubmission||[...responseRequests.values()].some(r=>['unknown','reconnecting'].includes(r.state))){$('send-state').textContent='Check or explicitly dismiss unresolved tracking before sending again; no automatic retry.';await refreshResponses();return;}
  if(latest?.setup?.response_tracking!==true){
    sending=true;$('send').disabled=true;
    try{await api('/api/ask',{text,chat:'console',door:'console',cwd:$('project-path').value.trim()||null,chat_provider_ref:$('chat-provider').value||null,chat_privacy:$('chat-provider').value&&$('project-path').value.trim()?$('project-privacy').value:null});bubble(text,'user');$('command').value='';$('send-state').textContent='Accepted using the existing reply path. Resumable tracking is unavailable in this service.';}
    catch(e){$('send-state').textContent=e.message+' — draft preserved; do not resend until delivery is checked.';}
    finally{sending=false;$('send').disabled=false;}
    return;
  }
  for(const [id,r] of responseRequests)if(responseRequests.size>=8&&responseTerminal.has(r.state))responseRequests.delete(id);
  if(responseRequests.size>=8){$('send-state').textContent='Dismiss completed tracking entries before another request.';return;}
  const id=crypto.randomUUID().replaceAll('-','');
  responseRequests.set(id,{id,state:'submitting',after:0});saveResponseIds();renderResponseRequests();
  sending=true;$('send').disabled=true;$('send-state').textContent='Submitting request '+id.slice(0,8)+'.';
  try {
    const accepted=await api('/api/requests',{request_id:id,text,cwd:$('project-path').value.trim()||null,chat_provider_ref:$('chat-provider').value||null,chat_privacy:$('chat-provider').value&&$('project-path').value.trim()?$('project-privacy').value:null});
    const current=responseRequests.get(id);
    if(!current)return;
    // An acceptance snapshot is older than any subsequent poll or cancellation.
    if(current.after===0&&['submitting','unknown'].includes(current.state))responseRequests.set(id,{...current,...accepted.request,after:current.after});
    if(unresolvedSubmission===id)unresolvedSubmission=null;
    bubble(text,'user');$('command').value='';$('send-state').textContent='Accepted. Follow delivery status below; no live text is claimed.';
  } catch(e) {
    if(!responseRequests.has(id)||responseTerminal.has(responseRequests.get(id).state))return;
    unresolvedSubmission=id;const r=responseRequests.get(id);if(r){r.state='unknown';r.notice='Submission not confirmed. Check this identity before retrying. '+e.message;}
    $('send-state').textContent=e.message+' — draft preserved; no automatic resend.';
  } finally {sending=false;$('send').disabled=false;renderResponseRequests();}
}
restoreResponseIds();renderResponseRequests();

function renderTasks(s) {
  $('task-count').textContent = s.tasks.length; $('tasks').replaceChildren();
  for(const t of s.tasks.slice(0,5)) { const b = node('button', undefined, 'task-row'); b.append(node('strong', t.ask || `Task #${t.id}`), node('small', `#${t.id} · ${t.state} · ${t.hand || t.kind}`)); b.onclick = () => showTask(t.id); $('tasks').append(b); }
  if(!s.tasks.length) empty($('tasks'), 'No tasks yet. Ask Ethan to help with your next piece of work.');
  $('reminders').replaceChildren();
  for(const r of s.scheduled.slice(0,3)) { const p = node('div', undefined, 'task-row'); p.append(node('strong', r.what || r.kind), node('small', when(r.due))); $('reminders').append(p); }
  if(!s.scheduled.length) empty($('reminders'), 'No upcoming reminders.');
}
function renderActivity(s) {
  const items = [...s.runs.map(r=>({...r,label:`${r.hand} run #${r.id}`,kind:'run'})), ...s.relays.map(r=>({...r,label:`Relay #${r.id} → ${r.target || 'choosing agent'}`,kind:'relay'}))].sort((a,b)=>(b.ts||0)-(a.ts||0)).slice(0,6);
  const box = node('div', undefined, 'activity-list');
  for(const r of items) { const e = node('div', undefined, 'event'); e.append(node('span',r.state || 'unknown','state'),node('div',r.label),node('small',when(r.ts))); const b=node('button','View result','quiet'); b.onclick=()=>showEvent(r);e.append(b);box.append(e); }
  $('activity').replaceChildren(box); if(!items.length) empty($('activity'),'No agent activity recorded yet. A queued request will appear here before any reply arrives.');
}
function renderApprovals(s) {
  const el=$('approvals'); el.replaceChildren();
  if(!s.approvals_supported) { empty(el,'Approval controls are unavailable in this service version.');return; }
  if(!s.approvals.length) { empty(el,'Nothing waiting on you. Requests requiring confirmation will appear here.');return; }
  for(const a of s.approvals) { const r=node('div',undefined,'approval-row');r.append(node('strong',`#${a.id} · ${a.kind}`),node('p',a.summary),node('p',`Expires ${when(a.expires)}`));
    for(const action of ['approve','deny']) { const b=node('button',action==='approve'?'Review & approve':'Deny',action);b.onclick=()=> { if(action==='approve') { $('command').value=`approve ${a.id}`; $('command').focus(); $('send-state').textContent=`Review approval #${a.id} above, then press Send to confirm.`; } else send(`deny ${a.id}`); };r.append(b); } el.append(r); }
}
async function showTask(id) { $('result-title').textContent=`Task #${id}`;$('result-body').textContent='Loading…';$('result').showModal();try{const t=await api('/api/task?id='+id);$('result-body').textContent=`${t.state || 'Unknown'}\n\n${t.ask || ''}\n\n${t.result || 'No result recorded yet.'}`;}catch(e){$('result-body').textContent=e.message;} }
async function showEvent(r) { $('result-title').textContent=r.label;$('result-body').textContent='Loading…';$('result').showModal();try{if(r.kind==='run'){const l=await api(`/api/log?run=${r.id}&offset=0`);$('result-body').textContent=`${l.state}\n\n${l.text || 'No output recorded yet.'}`;}else $('result-body').textContent=`${r.state}\n\n${r.ask || ''}\n\n${r.result || r.note || 'No answer recorded yet. Queued is not completed.'}`;}catch(e){$('result-body').textContent=e.message;} }
async function agents() {
  try { const a=await api('/api/agents');$('agents').replaceChildren();$('agent-count').textContent=a.sessions.length;
    for(const s of a.sessions.filter(s=>['claude','codex'].includes(s.agent))) { const card=node('div',undefined,'agent');const title=node('div',undefined,'agent-title');title.append(node('span',s.agent==='claude'?'CL':'CX','agent-avatar'),node('strong',s.name));card.append(title,node('div',`${s.agent.toUpperCase()} · REGISTERED\nLast reported: ${s.status || 'unknown'}\n${when(s.last_seen)}\n${s.project || 'Project not recorded'}`,'agent-meta'));const b=node('button','Draft a handoff');b.onclick=()=>{$('command').value=`ask the ${s.agent} session ${s.name} to review `;$('command').focus();};card.append(b);$('agents').append(card); }
    if(!a.sessions.length) empty($('agents'),a.note || 'No registered sessions.');
    $('provider-info').textContent=a.note;
    const selection=$('chat-provider').value;
    $('chat-provider').replaceChildren(new Option('Ethan commands / configured router',''));
    for(const session of a.sessions.filter(s=>['claude','codex'].includes(s.agent)&&s.native_id)) {
      const ref=`${session.agent}:${session.native_id}`;
      $('chat-provider').append(new Option(`${session.agent.toUpperCase()}: ${session.name} (registered)`,ref));
    }
    if(selection && !Array.from($('chat-provider').options).some(o=>o.value===selection)) {
      $('chat-provider').append(new Option('Previously selected session — unavailable',selection));
    }
    $('chat-provider').value=selection;
  } catch(e) { empty($('agents'),'Registry unavailable. '+e.message);$('agent-count').textContent='—'; }
}
function updateVoice(v) {
  voice=v; $('ptt').disabled=!online || !v.supported || v.muted || Boolean(v.wake_enabled);
  $('ptt').textContent=v.state==='listening'?'◉ Listening — release to preview':'◉ Hold to speak';
  $('mute').textContent=v.muted?'Unmute microphone':'Mute microphone';$('mute').setAttribute('aria-pressed',String(v.muted));$('mic-setting').checked=!v.muted;
  $('mute').disabled=!v.supported;$('mic-setting').disabled=!v.supported;
  $('voice-cancel').hidden=!['starting','wake-listening','listening','transcribing'].includes(v.state);
  $('voice-detail').textContent=v.detail || (v.supported?'Local voice ready.':'Local voice unavailable.');
  $('voice-settings').textContent=`${v.supported?'Local speech available':'Local speech unavailable'} · ${v.state}. ${v.detail || ''}`;
  $('wake-toggle').disabled=!online || !v.supported || (v.muted && !v.wake_enabled);
  $('wake-toggle').textContent=v.wake_enabled?'Disable wake / discard':'Enable wake listening (60s)';
  $('voice-finish').hidden=!(v.wake_enabled && v.state==='listening');
  if(v.transcript && v.transcript!==lastTranscript) { lastTranscript=v.transcript; $('command').value=[$('command').value.trim(),v.transcript].filter(Boolean).join(' ');$('send-state').textContent='Voice draft ready. Review it before pressing Send.'; }
  if(!v.transcript) lastTranscript=''; coreState();
}
const voiceCommandQueue = createVoiceQueue(action => api('/api/voice/'+action,{}));
async function voiceCommand(action) {try{updateVoice(await voiceCommandQueue(action));}catch(e){$('voice-detail').textContent=e.message;} }
async function refresh() {
  try { const s=await api('/api/state');latest=s;online=true;$('connection').textContent='SERVICE CONNECTED';$('connection-light').classList.add('online');$('offline').hidden=true;$('uptime').textContent=`UP ${Math.floor(s.uptime_sec/60)} MIN`;
    renderTasks(s);renderActivity(s);renderApprovals(s);$('response-capability').textContent=s.setup.response_tracking?'Resumable request tracking · current providers deliver checked final replies, not live text.':'Existing reply delivery · resumable tracking unavailable in this service; no live text.';
    $('setup-info').textContent=`Python service connected. General model key: ${s.setup.router_key?'configured':'not configured'}. Agent handoffs: ${s.setup.bridge?'configured':'not configured'}. Local knowledge base: ${s.setup.local_kb?'configured':'not configured'}.`;
    $('last-sync').textContent='SYNCED '+new Date().toLocaleTimeString();coreState();
    if(!historyLoaded){const h=await api('/api/conversation?chat=console');$('feed').replaceChildren();h.messages.forEach(m=>bubble(m.text,m.role));after=h.after;historyLoaded=true;if(!h.messages.length)bubble('I’m Ethan. Ask for your status, set a reminder, or send a review request to an existing agent.','assistant');}
    await refreshResponses();
    const r=await api('/api/replies?chat=console&after='+after);for(const m of r.replies){after=m.id;bubble(m.text,'assistant');speak(m.text);$('send-state').textContent='Enter to send · Shift+Enter for a new line';}
  }catch(e){online=false;$('connection').textContent=authRequired?'ACCESS LOCKED':'SERVICE OFFLINE';$('connection-light').classList.remove('online');$('offline').hidden=false;coreState();}
  try{updateVoice(await api('/api/voice/status'));}catch(e){updateVoice({supported:false,muted:true,state:'unavailable',detail:'Voice endpoint unavailable.'});}
  setTimeout(refresh,2000);
}
$('command-form').onsubmit=e=>{e.preventDefault();send($('command').value);};
$('command').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('command').value);}};
for(const b of document.querySelectorAll('[data-command]')) b.onclick=()=>{$('command').value=b.dataset.command;send(b.dataset.command);};
$('settings-open').onclick=()=>$('settings').showModal();$('settings-close').onclick=()=>$('settings').close();$('result-close').onclick=()=>$('result').close();
$('motion').onchange=e=>{prefs.motion=e.target.checked;applyPrefs();};$('spoken').onchange=e=>{prefs.spoken=e.target.checked;if(!prefs.spoken&&'speechSynthesis'in window){speechSynthesis.cancel();speaking=false;}applyPrefs();coreState();};
$('theme-toggle').onclick=()=>{prefs.theme=prefs.theme==='light'?'dark':'light';applyPrefs();};
$('reset-settings').onclick=()=>{prefs={...DEFAULTS};applyPrefs();};
$('mute').onclick=()=>voiceCommand(voice.muted?'unmute':'mute');$('mic-setting').onchange=e=>voiceCommand(e.target.checked?'unmute':'mute');$('voice-cancel').onclick=()=>{pttHeld=false;voiceCommand('cancel');};
function startPTT(){if(pttHeld||$('ptt').disabled)return;pttHeld=true;if('speechSynthesis'in window)speechSynthesis.cancel();voiceCommand('start');}
function stopPTT(){if(!pttHeld)return;pttHeld=false;voiceCommand('stop');}
$('ptt').onpointerdown=e=>{e.preventDefault();$('ptt').setPointerCapture(e.pointerId);startPTT();};$('ptt').onpointerup=stopPTT;$('ptt').onpointercancel=()=>{pttHeld=false;voiceCommand('cancel');};
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.code==='Space'&&!e.repeat){e.preventDefault();startPTT();}});document.addEventListener('keyup',e=>{if(e.code==='Space')stopPTT();});
window.addEventListener('blur',()=>{if(pttHeld){pttHeld=false;voiceCommand('cancel');}});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&pttHeld){pttHeld=false;voiceCommand('cancel');}});
loadPrefs();applyPrefs();refresh();agents();setInterval(agents,15000);function tickClock(){$('clock').textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});}tickClock();setInterval(tickClock,1000);

function contextDraft(write) {
  const project=$('project-path').value.trim(),privacy=$('project-privacy').value;
  if(!project){$('context-feedback').textContent='Choose an absolute project directory first.';return;}
  const data={project,privacy};
  if(write){for(const key of ['kind','name','summary','source','owner'])data[key]=$('context-'+key).value.trim();if(Object.values(data).some(v=>!v)){$('context-feedback').textContent='Complete every field; keep the summary short and cite its source.';return;}}
  $('command').value=(write?'coordinate ':'show coordination ')+JSON.stringify(data);$('settings').close();$('command').focus();$('send-state').textContent=write?'Review the coordination record, then Send to save it. This grants no permission.':'Send to retrieve saved coordination for this project.';
}
$('context-draft').onclick=()=>contextDraft(true);$('context-show').onclick=()=>contextDraft(false);

$('ptt').addEventListener('keydown',e=>{if((e.code==='Space'||e.key==='Enter')&&!e.repeat){e.preventDefault();startPTT();}});$('ptt').addEventListener('keyup',e=>{if(e.code==='Space'||e.key==='Enter'){e.preventDefault();stopPTT();}});$('ptt').addEventListener('blur',()=>{if(pttHeld){pttHeld=false;voiceCommand('cancel');}});

function saveProjectScope(){try{const project=$('project-path').value.trim(),privacy=$('project-privacy').value;if(project.length<=1000&&['personal','work','client'].includes(privacy))localStorage.setItem('ethan.project.v1',JSON.stringify({version:1,project,privacy}));}catch(_){} }
try{const scope=JSON.parse(localStorage.getItem('ethan.project.v1'));if(scope&&scope.version===1&&typeof scope.project==='string'&&scope.project.length<=1000&&['personal','work','client'].includes(scope.privacy)){$('project-path').value=scope.project;$('project-privacy').value=scope.privacy;}}catch(_){}
$('project-path').addEventListener('change',saveProjectScope);$('project-privacy').addEventListener('change',saveProjectScope);

$('chat-provider').addEventListener('change',()=>{$('chat-provider-note').textContent=$('chat-provider').value?'Using the selected existing session for conversation. Commands stay with Ethan; queued is not delivered.':'Using Ethan commands and the configured router. General chat may require its configured API key.';});

$('wake-toggle').addEventListener('click',()=>voiceCommand(voice.wake_enabled?'wake-disable':'wake-enable'));
$('voice-finish').addEventListener('click',()=>voiceCommand('stop'));

$('auth-form').onsubmit=async e=>{e.preventDefault();const candidate=$('auth-token').value;$('auth-token').value='';if(!/^[A-Za-z0-9._~+\/=-]{32,4096}$/.test(candidate)){ $('auth-note').textContent='Enter the service owner-provided access token; it is never a chat message.';return;}const epoch=++authEpoch;accessToken=candidate;try{await api('/api/state');$('auth-note').textContent='Access accepted for this tab only.';historyLoaded=false;agents();}catch(_){if(epoch!==authEpoch)return;accessToken='';$('auth-note').textContent='Access refused or service unavailable. Token was not saved.';}};
$('auth-forget').onclick=()=>{responseRequests.clear();unresolvedSubmission=null;saveResponseIds();renderResponseRequests();authEpoch++;accessToken='';historyLoaded=false;after=0;latest=null;online=false;$('feed').replaceChildren();$('result-body').textContent='';for(const id of ['agents','tasks','reminders','approvals','activity'])$(id).replaceChildren();if('speechSynthesis'in window)speechSynthesis.cancel();$('settings').close();$('send-state').textContent='Tab token forgotten. This does not revoke other clients or stop the service.';};
