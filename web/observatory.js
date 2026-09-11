'use strict';
const $=id=>document.getElementById(id);
const node=(tag,value,cls)=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
const units=(s,d=6)=>(Number(s)/1e18).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
const age=t=>Math.max(0,Math.floor(Date.now()/1000-t));
const phases={recovery_required:'Recovering the garden’s saved transaction history',starting:'The garden is waking up',observing:'Observing the chain',waiting_for_backup:'Waiting for wallet backup',waiting_for_funding:'Waiting for funding',deploying:'Preparing the garden economy',running:'The garden is running',stopped:'The garden is paused for a safety check'};
const actions={produce:['Workshop','Selected resource production'],harvest:['Gathering ground','Selected resource gathering'],buy_input:['Exchange','Selected a resource purchase'],inspect_market:['PONS lookout','Selected a market inspection']};
const journal=new Map();let lastData=null,lastRefresh=0,busy=false;
function record(key,time,text,kind='observation',hash=null){if(!journal.has(key))journal.set(key,{time,text,kind,hash});}
function renderJournal(){
 const entries=[...journal.values()].sort((a,b)=>b.time-a.time).slice(0,80);
 $('events').replaceChildren(...entries.map(e=>{const row=node('div','','event '+e.kind),body=node('div','');body.append(node('small',new Date(e.time*1000).toLocaleTimeString()+' · '+e.kind),node('span',e.text));row.append(body);if(e.hash){const a=node('a','Receipt ↗');a.href='https://rh-scan.com/tx/'+e.hash;a.target='_blank';a.rel='noreferrer';row.append(a);}return row;}));
 if(!entries.length)$('events').append(node('p','Waiting for verified observations.'));
 if(journal.size>120){const keep=new Set(entries);for(const [key,e] of journal)if(!keep.has(e))journal.delete(key);}
}
function clock(){
 if(!lastData)return;
 const h=lastData.heartbeat,fresh=h&&age(h.observed_at)<360;
 $('live-clock').textContent='Chain observed '+age(lastData.observed_at)+'s ago · '+(h?'Runner reported '+age(h.observed_at)+'s ago':'No runner report')+' · next check in '+Math.max(0,5-age(lastRefresh))+'s';
 if(!fresh){$('phase').textContent='Runner offline or heartbeat unavailable';$('narration').textContent='Waiting for a fresh runner report. Last observations remain below.';}
 document.querySelectorAll('[data-measured]').forEach(el=>{const seconds=age(Number(el.dataset.measured));el.textContent='Measured '+seconds+'s ago'+(seconds>=600?' · stale':'');});
 document.querySelectorAll('.fly[data-measured-at]').forEach(el=>el.classList.toggle('outdated',age(Number(el.dataset.measuredAt))>=600));
}
setInterval(clock,1000);
async function refresh(){
 if(busy)return;busy=true;
 try{
  const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('Live data is unavailable. Previously loaded values may be stale.');const d=await r.json();
  lastData=d;lastRefresh=Date.now()/1000;const h=d.heartbeat,fresh=h&&age(h.observed_at)<360;
  if(h)record('phase-'+h.status+'-'+h.round,h.observed_at,(phases[h.status]||h.status)+' · observation round '+h.round,'service');
  document.body.classList.remove('stale');$('error').textContent='';
  $('connection').textContent='Connected to Robinhood Chain';$('block').textContent=d.block.toLocaleString();
  $('updated').textContent='Chain checked '+new Date(d.observed_at*1000).toLocaleTimeString();
  $('phase').textContent=fresh?phases[h.status]:'Runner offline or heartbeat unavailable';
  $('round').textContent=fresh?'Measured neural round '+h.round:'No current runner heartbeat';
  $('backup').textContent=h?(h.backup_ready?'Portable wallet backup verified.':'Wallet backup must be completed before funding.'):'Wallet readiness has not been reported.';
  $('eth').textContent=units(d.wallets.reduce((n,w)=>n+BigInt(w.eth_wei),0n))+' ETH';
  $('pons').textContent=units(d.wallets.reduce((n,w)=>n+BigInt(w.pons_units),0n),4)+' PONS';
  $('price').textContent=units(d.market.price_wei,8)+' ETH / PONS';
  $('trades').textContent=d.transactions.filter(t=>t.status==='confirmed').length;
  $('flies').replaceChildren(...d.wallets.map(w=>{
   const card=node('article','','fly'),portrait=node('img','','portrait');portrait.src='/fly-logo.png';portrait.alt='';card.append(portrait,node('h3',w.name));
   const link=node('a',w.address.slice(0,7)+'…'+w.address.slice(-5),'address');link.href='https://rh-scan.com/address/'+w.address;link.target='_blank';link.rel='noreferrer';card.append(link);
   card.append(node('div',units(w.eth_wei)+' ETH','money'),node('div',units(w.pons_units,4)+' PONS','money'));
   const t=h?.telemetry?.find(t=>t.id===w.id),brain=node('div','','neural');
   if(t&&age(t.measured_at)<600){
    const [place,description]=actions[t.action]||['Habitat','Selected '+t.action.replaceAll('_',' ')];
    card.dataset.measuredAt=t.measured_at;card.classList.add(t.action);
    card.prepend(node('span',place,'location'));
    brain.append(node('strong',description),node('span','Decision recorded; execution depends on safety checks.'));
    const meter=node('meter','');meter.min=0;meter.max=t.neurons||165122;meter.value=t.firing;meter.setAttribute('aria-label','Measured firing neurons');brain.append(meter,node('span',t.firing.toLocaleString()+' / '+(t.neurons||165122).toLocaleString()+' neurons firing'));
    const when=node('span','');when.dataset.measured=t.measured_at;brain.append(when);
    record('brain-'+w.id+'-'+t.measured_at,t.measured_at,w.name+': '+description.toLowerCase()+'. '+t.firing.toLocaleString()+' neurons firing. This is a decision, not confirmation of execution.','decision');
   }else brain.textContent='Waiting for a fresh neural measurement.';
   card.append(brain);return card;
  }));
  const names={deploy:'Garden deployment',buy_pons:'Bought PONS',sell_pons:'Sold PONS for ETH',approve_pons:'Approved an exact PONS exit',buy_resource:'Bought a resource',produce:'Produced resources',harvest:'Gathered resources'};
  for(const t of d.transactions){
   const name=d.wallets.find(w=>w.id===t.fly)?.name||'Fly';
   const operation={deploy:'garden deployment',buy_pons:'PONS purchase',sell_pons:'PONS sale',approve_pons:'PONS exit approval',buy_resource:'resource purchase',produce:'resource production',harvest:'resource gathering'}[t.kind]||t.kind;
   record('tx-'+t.hash+'-'+t.status, t.created,name+' · '+operation+' · '+t.status+(t.block?' at block '+t.block:'. Waiting for an on-chain receipt.'),'transaction',t.hash);
  }
  const measured=(h?.telemetry||[]).filter(t=>age(t.measured_at)<600);
  const pending=d.transactions.filter(t=>['pending','confirming'].includes(t.status));
  $('narration').textContent=!fresh?'Waiting for a fresh runner report.':h.status!=='running'?(phases[h.status]+'. '+(h.status==='recovery_required'?'Funding is present. Previous wallet transactions were detected, but the saved journal is unavailable. Trading is paused until recovery.':h.status==='deploying'?'The shared economy is being prepared.':h.status==='stopped'?'Execution is paused; chain observations continue.':'The flies are observing while activation checks finish.')):pending.length?pending.length+' transaction'+(pending.length===1?' is':'s are')+' awaiting confirmation.':measured.length+' flies have recent measured decisions. Watching for the next on-chain action.';
  renderJournal();clock();
 }catch(error){document.body.classList.add('stale');$('connection').textContent='Chain connection unavailable';$('error').textContent=error.message;$('narration').textContent='Live connection interrupted. Displayed observations may be stale.';}finally{busy=false;}
}
refresh();setInterval(refresh,5000);
