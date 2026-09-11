'use strict';
let economy=new Economy(), selected=0, timer=null;
const $=id=>document.getElementById(id), eth=n=>n.toFixed(4), pct=n=>(n*100).toFixed(1)+'%';
function render(){
 const e=economy,f=e.flies[selected],worth=e.worth(f),exposure=e.exposure(f)/worth;
 $('wealth').innerHTML=eth(e.flies.reduce((s,f)=>s+e.worth(f),0))+' <small>paper ETH</small>';
 $('volume').innerHTML=eth(e.volume)+' <small>paper ETH</small>';$('trades').textContent=e.trades;$('tick').textContent='Day '+e.tick;
 $('status').textContent=timer?'Running · observing the economy':'Paused · day '+e.tick;$('play').textContent=timer?'Pause garden Ⅱ':'Run garden ↗';$('step').disabled=!!timer;
 if(!$('flies').children.length)$('flies').innerHTML=e.flies.map(f=>`<button class="fly" data-fly="${f.id}" aria-label="Inspect ${f.name}"><b aria-hidden="true">🪰</b><span>${f.name}</span></button>`).join('');
 [...$('flies').children].forEach((node,i)=>{node.style.left=e.flies[i].x+'%';node.style.top=e.flies[i].y+'%';node.classList.toggle('selected',i===selected);node.setAttribute('aria-pressed',String(i===selected));});
 $('links').innerHTML=e.events.filter(x=>x.type==='trade'&&x.tick>e.tick-2).slice(0,8).map(x=>{const a=e.flies[x.from],b=e.flies[x.to];return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#829861" stroke-width=".25" stroke-dasharray="1 1" opacity=".65"/>`;}).join('');
 const min=Math.min(...f.trail)*.999,max=Math.max(...f.trail)*1.001;
 const points=f.trail.map((v,i)=>`${i/Math.max(1,f.trail.length-1)*250},${44-(v-min)/(max-min)*40}`).join(' ');
 $('detail').innerHTML=`<span class="detail-id">INHABITANT ${String(f.id+1).padStart(2,'0')} / PAPER ACCOUNT</span><h2>${f.name}</h2><p class="role">${f.role}</p><div class="balance">${eth(worth)}<small>financial net worth · paper ETH</small></div><svg class="spark" viewBox="0 0 250 48" role="img" aria-label="Recent net worth"><polyline points="${points}" fill="none" stroke="#627d43" stroke-width="1.5"/></svg><dl><div><dt>Cash</dt><dd>${eth(f.cash)} ETH</dd></div><div><dt>Paper tokens</dt><dd>${eth(e.exposure(f))} ETH</dd></div><div><dt>Nectar / silk</dt><dd>${f.goods[0].toFixed(1)} / ${f.goods[1].toFixed(1)}</dd></div><div><dt>Resource income</dt><dd>${eth(f.earned)} ETH</dd></div><div><dt>Resource spending</dt><dd>${eth(f.spent)} ETH</dd></div></dl><div class="meter"><i style="width:${exposure*100}%"></i></div><div class="allocation"><span>${pct(exposure)} in tokens</span><span>50% cap</span></div><p class="activity">${f.activity}</p>`;
 $('leaderboard').innerHTML=[...e.flies].sort((a,b)=>e.worth(b)-e.worth(a)).map((f,i)=>`<button class="row" data-fly="${f.id}" aria-label="Inspect ${f.name}"><span class="rank">${String(i+1).padStart(2,'0')}</span><span>${f.name}<small>${f.role}</small></span><span class="number">${eth(e.worth(f))}<small>paper ETH</small></span><span class="number ${e.worth(f)>=1?'positive':'negative'}">${e.worth(f)>=1?'+':''}${pct(e.worth(f)-1)}</span></button>`).join('');
 const events=e.events.filter(x=>$('filter').value==='all'||x.type===$('filter').value);
 $('events').innerHTML=events.length?events.map(x=>`<div class="event"><time>D ${x.tick}</time><div>${x.text}<small>${eth(x.value)} paper ETH · ${x.type==='trade'?'fly-to-fly trade':'simulated pool'}</small></div></div>`).join(''):'<div class="empty">A quiet garden, for now.<p>Run the garden to see its first trades.</p></div>';
 const audit=e.audit();$('audit').textContent=Object.entries(audit).every(([k,v])=>k==='total'||v)?'✓ ETH conserved · exposure cap respected':'Accounting check failed — paused';
 if(!audit.ethConserved||!audit.capRespected||!audit.balancesValid||!audit.tokensConserved){pause();throw new Error('Simulation invariant failed');}
}
function pause(){if(timer)clearInterval(timer);timer=null;}
function run(){pause();timer=setInterval(()=>{try{economy.step();render();}catch(err){pause();$('status').textContent='Paused: '+err.message;}},Number($('speed').value));render();}
document.addEventListener('click',event=>{const button=event.target.closest('[data-fly]');if(button){selected=Number(button.dataset.fly);render();}});
$('play').onclick=()=>{if(timer){pause();render();}else run();};$('step').onclick=()=>{economy.step();render();};$('speed').onchange=()=>{if(timer)run();};$('filter').onchange=render;
$('reset').onclick=()=>{if(economy.tick&&!confirm('Reset this simulated run? Export it first if you want to keep a record.'))return;pause();economy=new Economy();selected=0;render();};
$('export').onclick=()=>{const blob=new Blob([JSON.stringify({version:1,mode:'simulation',...economy,audit:economy.audit()},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`fly-garden-day-${economy.tick}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
render();
if(document.modelContext?.registerTool){
 for(const tool of [
  {name:'read_garden',description:'Read simulated garden balances and accounting checks.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute(input){if(!input||Object.keys(input).length)throw new Error('No arguments expected');return {day:economy.tick,flies:economy.flies.map(f=>({name:f.name,netWorth:economy.worth(f),cash:f.cash})),audit:economy.audit()};}},
  {name:'advance_garden',description:'Pause the simulation and advance 1 to 100 simulated days. Never sends real transactions.',inputSchema:{type:'object',properties:{days:{type:'integer',minimum:1,maximum:100}},required:['days'],additionalProperties:false},annotations:{readOnlyHint:false},execute(input){if(!input||Object.keys(input).length!==1||!Number.isInteger(input.days)||input.days<1||input.days>100)throw new Error('days must be an integer from 1 to 100');pause();for(let i=0;i<input.days;i++)economy.step();render();return {day:economy.tick,trades:economy.trades,audit:economy.audit()};}}
 ])try{Promise.resolve(document.modelContext.registerTool(tool)).catch(()=>{});}catch{}
}
