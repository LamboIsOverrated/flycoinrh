'use strict';
const el=id=>document.getElementById(id);let statusData=null,isLocal=false,busy=false;
const text=(tag,value,cls)=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
const money=n=>n===null||n===undefined?'Not verified':(Number(n)/1e18).toFixed(6)+' ETH';
async function refresh(){
 if(busy)return;busy=true;
 try{
  let response;
  if(location.hostname==='127.0.0.1'){response=await fetch('/api/pilot',{cache:'no-store'});isLocal=true;}
  else{response=await fetch('./pilot-status.json',{cache:'no-store'});isLocal=false;}
  if(!response.ok)throw new Error('Pilot status is not available.');
  statusData=await response.json();const check=statusData.preflight,state=statusData.state;
  el('source').textContent=isLocal?'Connected to the local neural pilot. Economic balances remain simulated.':'Saved readiness report. This page does not control or stream the local pilot.';
  el('funding').textContent=check.ready_to_fund?'Funding readiness verified.':'Do not fund yet.';
  el('runtime').textContent=isLocal?(statusData.running?'Neural pilot running':statusData.busy?'Finishing this round':'Neural pilot paused'):'Neural pilot · saved report';
  el('time').textContent=`Round ${state?.tick??0} · Updated ${new Date((state?.updated_at||check.checked_at)*1000).toLocaleString()}`;
  el('checks').replaceChildren(...check.blockers.map(s=>text('div',s,'check')));
  const market=check.markets?.find(m=>m.symbol==='PONS');
  if(market)el('checks').append(text('div',`PONS / WETH · 1% pool fee · Buy/sell simulation passed at block ${market.block.toLocaleString()}. Quotes are historical, not a promise of execution.`, 'check'));
  const cards=check.wallets.map(w=>{const f=state?.flies?.find(x=>x.id===w.id),t=f?.telemetry,card=text('article','','fly-card');
   card.append(text('h3',w.name),text('div',w.address,'address'));
   const figures=text('div','','figures');
   for(const [label,value] of [['Mainnet balance',money(w.balance_wei)],['Paper ETH',money(f?.paper_cash_wei)],['Paper PONS',(Number(f?.pons_units||0)/1e18).toFixed(4)],['PONS liquidation quote',money(f?.token_value_wei||0)],['Firing neurons',t?t.firing.toLocaleString():'Not measured'],['Spikes / second',t?Math.round(t.spikes_per_sec).toLocaleString():'Not measured']]){const d=document.createElement('div');d.append(text('label',label),text('strong',value));figures.append(d);}
   card.append(figures,text('p',t?`Neural choice: ${t.action.replaceAll('_',' ')} · ${t.neurons.toLocaleString()} neurons`:'Brain has not completed a round.','activity'));return card;});
  el('wallets').replaceChildren(...cards);
  el('start').disabled=!isLocal||statusData.busy;el('step').disabled=!isLocal||statusData.busy;el('pause').disabled=!isLocal||!statusData.running;
  el('error').textContent=statusData.error||'';
 }catch(error){el('error').textContent=error.message;for(const id of ['start','step','pause'])el(id).disabled=true;}finally{busy=false;}
}
async function action(name){try{const r=await fetch('/api/'+name,{method:'POST',headers:{'X-Garden-Control':statusData.control_token}});if(!r.ok)throw new Error('Pilot is busy or the request was rejected.');await refresh();}catch(e){el('error').textContent=e.message;}}
for(const id of ['start','step','pause'])el(id).onclick=()=>action(id);
refresh();setInterval(refresh,3000);
