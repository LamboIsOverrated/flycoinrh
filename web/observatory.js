'use strict';
const $=id=>document.getElementById(id);
const node=(tag,value,cls)=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
const units=(s,d=6)=>(Number(s)/1e18).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
const age=t=>Math.max(0,Math.floor(Date.now()/1000-t));
const phases={starting:'The garden is waking up',observing:'Observing the chain',waiting_for_backup:'Waiting for wallet backup',waiting_for_funding:'Waiting for funding',deploying:'Preparing the garden economy',running:'The garden is running',stopped:'The garden is paused for a safety check'};
let busy=false;
async function refresh(){
 if(busy)return;busy=true;
 try{
  const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('Live data is unavailable. Previously loaded values may be stale.');const d=await r.json();
  const h=d.heartbeat,fresh=h&&age(h.observed_at)<360;
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
   const card=node('article','','fly'),portrait=node('div','🪰','portrait');portrait.setAttribute('aria-hidden','true');card.append(portrait,node('h3',w.name));
   const link=node('a',w.address.slice(0,7)+'…'+w.address.slice(-5),'address');link.href='https://rh-scan.com/address/'+w.address;link.target='_blank';link.rel='noreferrer';card.append(link);
   card.append(node('div',units(w.eth_wei)+' ETH','money'),node('div',units(w.pons_units,4)+' PONS','money'));
   const t=h?.telemetry?.find(t=>t.id===w.id),brain=node('div','','neural');
   brain.textContent=t&&age(t.measured_at)<600?`${t.firing.toLocaleString()} firing neurons · ${t.action.replaceAll('_',' ')} · measured ${age(t.measured_at)}s ago`:'No recent neural measurement';card.append(brain);return card;
  }));
  const names={deploy:'Garden deployment',buy_pons:'Bought PONS',sell_pons:'Sold PONS for ETH',approve_pons:'Approved an exact PONS exit',buy_resource:'Bought a resource',produce:'Produced resources',harvest:'Gathered resources'};
  $('events').replaceChildren(...d.transactions.map(t=>{const row=node('div','','event'),left=node('div','');left.append(node('span',d.wallets[t.fly].name+' · '+(names[t.kind]||t.kind)),node('small',t.status+' · '+(t.block?'block '+t.block:'waiting for a receipt')));const a=node('a','View transaction ↗');a.href='https://rh-scan.com/tx/'+t.hash;a.target='_blank';a.rel='noreferrer';row.append(left,a);return row;}));
  if(!d.transactions.length)$('events').append(node('p','No garden transactions have been submitted. This feed fills only with actual transaction hashes.'));
 }catch(error){document.body.classList.add('stale');$('connection').textContent='Chain connection unavailable';$('error').textContent=error.message;}finally{busy=false;}
}
refresh();setInterval(refresh,20000);
