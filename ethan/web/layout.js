'use strict';
let layoutHead=null, layoutDraft=null, layoutPreview=null, layoutRegistry=[];
const layoutNodes = new Map();
for(const type of ['agents','core','tasks','conversation','approvals','activity']) {
  const el=document.querySelector(type==='core'?'.core-panel':type==='conversation'?'.conversation':`[data-widget="${type}"]`);
  el.dataset.widget=type;layoutNodes.set(type,el);
}
function renderLayout(layout) {
  const grid=document.querySelector('.dashboard');grid.classList.add('dynamic-layout');
  const present=new Set(layout.widgets.map(w=>w.type));
  for(const [type,el] of layoutNodes) el.hidden=!present.has(type);
  for(const w of layout.widgets) {
    const el=layoutNodes.get(w.type);if(!el)continue;
    el.classList.toggle('span-two',w.width===2);el.hidden=false;grid.append(el);
    if(!['core','conversation'].includes(w.type)){const heading=el.querySelector('.panel-head h2');heading.replaceChildren(node('span',String(['agents','tasks','conversation','approvals','activity'].indexOf(w.type)+1).padStart(2,'0')),document.createTextNode(w.title));}
  }
}
function layoutNotice(text){$('layout-status').textContent=text;}
function editLayout(){
  if(!layoutDraft)return;$('layout-editor').replaceChildren();
  const order=[...layoutDraft.widgets.map(w=>w.type),...layoutRegistry.map(w=>w.type).filter(t=>!layoutDraft.widgets.some(w=>w.type===t))];
  for(const type of order){
    const reg=layoutRegistry.find(r=>r.type===type),w=layoutDraft.widgets.find(r=>r.type===type),row=node('div',undefined,'layout-row');
    const label=node('label'),check=node('input');check.type='checkbox';check.checked=!!w;check.disabled=reg.mandatory;
    check.onchange=()=>{if(check.checked)layoutDraft.widgets.push({id:type,type,width:reg.width,title:reg.title});else layoutDraft.widgets=layoutDraft.widgets.filter(x=>x.type!==type);invalidateLayoutPreview();editLayout();};
    label.append(check,document.createTextNode(reg.title+(reg.mandatory?' · required':'')));row.append(label);
    if(w){const controls=node('div',undefined,'layout-controls');const title=node('input');title.value=w.title;title.maxLength=64;title.disabled=reg.mandatory;title.setAttribute('aria-label',type+' title');title.oninput=()=>{w.title=title.value;invalidateLayoutPreview();};controls.append(title);
      const size=node('select');size.setAttribute('aria-label',type+' width');for(const n of [1,2]){const o=node('option',n===1?'Compact':'Wide');o.value=String(n);size.append(o);}size.value=String(w.width);size.disabled=reg.mandatory;size.onchange=()=>{w.width=Number(size.value);invalidateLayoutPreview();};controls.append(size);
      for(const [sign,delta] of [['↑',-1],['↓',1]]){const b=node('button',sign,'quiet');b.type='button';b.setAttribute('aria-label',`Move ${type} ${delta<0?'up':'down'}`);const index=layoutDraft.widgets.indexOf(w);b.disabled=index+delta<0||index+delta>=layoutDraft.widgets.length;b.onclick=()=>{const target=index+delta;[layoutDraft.widgets[index],layoutDraft.widgets[target]]=[layoutDraft.widgets[target],layoutDraft.widgets[index]];invalidateLayoutPreview();editLayout();};controls.append(b);}row.append(controls);
    }$('layout-editor').append(row);
  }
}
function invalidateLayoutPreview(){layoutPreview=null;$('layout-apply').disabled=true;$('layout-preview-banner').hidden=true;if(layoutHead)renderLayout(layoutHead.layout);layoutNotice('Unsaved changes. Preview to validate before applying.');}
async function fetchLayout(){try{const data=await api('/api/layout');layoutRegistry=data.registry;if(!layoutHead)layoutNotice(`Current revision ${data.revision}. Edit a card, then preview your changes.`);if(!layoutPreview){layoutHead=data;renderLayout(data.layout);if(!$('settings').open){layoutDraft=structuredClone(data.layout);editLayout();}}if(data.recovered)layoutNotice('Saved layout was invalid. Safe defaults are shown; preview and apply to repair.');}catch(e){layoutNotice('Layout unavailable: '+e.message);} }
async function previewLayout(reset=false){try{const candidate=reset?{version:1,widgets:layoutRegistry.map(r=>({id:r.type,type:r.type,width:r.width,title:r.title}))}:layoutDraft;const p=await api('/api/layout/preview',{layout:candidate});layoutPreview=p;layoutDraft=structuredClone(p.layout);renderLayout(p.layout);editLayout();$('layout-apply').disabled=false;$('layout-preview-banner').hidden=false;layoutNotice(`Preview only · based on revision ${p.expected_revision}. Added: ${p.diff.added.join(', ')||'none'}; removed: ${p.diff.removed.join(', ')||'none'}; changed: ${p.diff.changed.join(', ')||'none'}. Order: ${p.diff.order_after.join(' → ')}. Expires in 10 minutes.`);}catch(e){layoutNotice('Preview refused: '+e.message);} }
async function applyLayout(){if(!layoutPreview)return;try{const h=await api('/api/layout/apply',{preview_id:layoutPreview.preview_id});layoutHead=h;layoutDraft=structuredClone(h.layout);layoutPreview=null;renderLayout(h.layout);$('layout-preview-banner').hidden=true;$('layout-apply').disabled=true;editLayout();layoutNotice(`Applied revision ${h.revision}. Shared across desktop and web.`);}catch(e){layoutNotice('Apply refused: '+e.message);layoutPreview=null;$('layout-preview-banner').hidden=true;$('layout-apply').disabled=true;await fetchLayout();}}
$('layout-preview').onclick=()=>previewLayout();$('layout-reset').onclick=()=>previewLayout(true);$('layout-apply').onclick=applyLayout;
$('layout-discard').onclick=()=>{layoutPreview=null;$('layout-preview-banner').hidden=true;$('layout-apply').disabled=true;layoutDraft=structuredClone(layoutHead.layout);renderLayout(layoutHead.layout);editLayout();layoutNotice('Preview discarded; current layout unchanged.');};
$('layout-rollback').onclick=async()=>{if(!layoutHead)return;try{const h=await api('/api/layout/rollback',{expected_revision:layoutHead.revision});layoutHead=h;layoutPreview=null;layoutDraft=structuredClone(h.layout);renderLayout(h.layout);editLayout();$('layout-preview-banner').hidden=true;$('layout-apply').disabled=true;layoutNotice(`Previous layout restored as revision ${h.revision}.`);}catch(e){layoutNotice('Rollback refused: '+e.message);}};
$('layout-return').onclick=()=>$('settings').showModal();
$('settings-open').addEventListener('click',()=>{if(layoutHead&&!layoutPreview){layoutDraft=structuredClone(layoutHead.layout);editLayout();}});
fetchLayout();setInterval(fetchLayout,5000);
