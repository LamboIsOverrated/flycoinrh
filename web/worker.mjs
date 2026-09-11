// Read-only observatory plus authenticated, bounded runner telemetry ingestion.
// ASSETS and WALLETS are inserted by build-observatory.cjs; no keys are bundled.
const TOKEN='0x39dBED3a2bd333467115dE45665cC57F813C4571';
const POOL='0x10cc6bd38112cac182db90b6a71d8bb5939526ba';
let cached=null,cacheAt=0;
const headers={'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers});
async function rpc(env,method,params=[]){
 if(!env.GARDEN_RPC_URL)throw Error('Provider unavailable');
 const r=await fetch(env.GARDEN_RPC_URL,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params}),signal:AbortSignal.timeout(12000)});
 if(!r.ok)throw Error('Provider unavailable');const d=await r.json();if(d.error||d.result===undefined)throw Error('Chain read failed');return d.result;
}
async function authorized(request,env){
 const value=request.headers.get('authorization')||'';
 if(!env.GARDEN_PUBLISHER_KEY)return false;
 const hash=async x=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(x)));
 const [a,b]=await Promise.all([hash(value),hash('Bearer '+env.GARDEN_PUBLISHER_KEY)]);let result=0;for(let i=0;i<a.length;i++)result|=a[i]^b[i];return result===0;
}
async function ingest(request,env){
 if(!await authorized(request,env))return json({error:'Unauthorized'},401);
 if(Number(request.headers.get('content-length'))>65000)return json({error:'Too large'},413);
 const text=await request.text();if(text.length>65000)return json({error:'Too large'},413);
 const d=JSON.parse(text);
 if(!Number.isFinite(d.observed_at)||Math.abs(Date.now()/1000-d.observed_at)>120||!Number.isInteger(d.round)||d.round<0)return json({error:'Invalid heartbeat'},400);
 const statuses=['starting','observing','waiting_for_backup','waiting_for_funding','deploying','running','stopped'];
 if(!statuses.includes(d.status))return json({error:'Invalid status'},400);
 const telemetry=(d.telemetry||[]).slice(0,10).filter(t=>Number.isInteger(t.id)&&t.id>=0&&t.id<10&&Number.isFinite(t.measured_at)&&Number.isFinite(t.firing)&&t.firing>=0&&t.firing<=165122).map(t=>({id:t.id,measured_at:t.measured_at,firing:t.firing,neurons:t.neurons,action:String(t.action).slice(0,40),observation_block:t.observation_block}));
 const transactions=(d.transactions||[]).slice(0,20).filter(t=>/^0x[0-9a-f]{64}$/i.test(t.hash)&&Number.isInteger(t.fly)&&t.fly>=0&&t.fly<10).map(t=>({hash:t.hash,fly:t.fly,kind:String(t.kind).slice(0,40),created:t.created}));
 const body={observed_at:d.observed_at,status:d.status,round:d.round,backup_ready:d.backup_ready===true,enabled:d.enabled===true,
  error:d.error?'Runner paused after a safety or connection check':null,telemetry,transactions};
 await env.DB.prepare('INSERT INTO garden_heartbeat (id, observed, body) VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET observed=excluded.observed,body=excluded.body WHERE excluded.observed>garden_heartbeat.observed').bind(d.observed_at,JSON.stringify(body)).run();
 cached=null;return json({ok:true});
}
async function status(env){
 if(cached&&Date.now()-cacheAt<15000)return cached;
 if(BigInt(await rpc(env,'eth_chainId'))!==4663n)throw Error('Wrong chain');
 const block=await rpc(env,'eth_blockNumber');const head=Number(BigInt(block));
 const [stored,slot]=await Promise.all([env.DB.prepare('SELECT body FROM garden_heartbeat WHERE id=1').first(),rpc(env,'eth_call',[{to:POOL,data:'0x3850c7bd'},block])]);
 const heartbeat=stored?JSON.parse(stored.body):null;
 const sqrt=BigInt('0x'+slot.slice(2,66));if(sqrt<=0n)throw Error('Invalid market');
 const price=10n**18n*(2n**192n)/(sqrt*sqrt);
 const wallets=await Promise.all(WALLETS.map(async w=>{
  const [eth,token]=await Promise.all([rpc(env,'eth_getBalance',[w.address,block]),rpc(env,'eth_call',[{to:TOKEN,data:'0x70a08231'+w.address.slice(2).toLowerCase().padStart(64,'0')},block])]);
  return {...w,eth_wei:BigInt(eth).toString(),pons_units:BigInt(token).toString(),token_mark_wei:(BigInt(token)*(2n**192n)/(sqrt*sqrt)).toString()};
 }));
 const transactions=[];
 for(const t of heartbeat?.transactions||[]){
  const receipt=await rpc(env,'eth_getTransactionReceipt',[t.hash]);
  if(receipt&&receipt.from?.toLowerCase()!==WALLETS[t.fly].address.toLowerCase())continue;
  const confirmations=receipt?head-Number(BigInt(receipt.blockNumber))+1:0;
  transactions.push({...t,status:receipt?(BigInt(receipt.status)===0n?'reverted':confirmations>=12?'confirmed':'confirming'):'pending',confirmations,
   block:receipt?Number(BigInt(receipt.blockNumber)):null});
 }
 cached={observed_at:Date.now()/1000,block:head,chain_id:4663,wallets,market:{token:TOKEN,pool:POOL,price_wei:price.toString(),fee_bps:100},
  heartbeat,transactions,source:'Robinhood Chain RPC'};cacheAt=Date.now();return cached;
}
export default {async fetch(request,env){
 const path=new URL(request.url).pathname;
 try{
  if(path==='/api/heartbeat'&&request.method==='POST')return await ingest(request,env);
  if(request.method!=='GET')return json({error:'Read-only website'},405);
  if(path==='/api/status')return json(await status(env));
  const asset=ASSETS[path==='/'||path==='/pilot.html'?'/index.html':path];
  if(!asset)return json({error:'Not found'},404);
  return new Response(asset.body,{headers:{'content-type':asset.type,'cache-control':'no-cache','x-content-type-options':'nosniff',
   'content-security-policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"}});
 }catch{return json({error:'Live data is temporarily unavailable. No estimated balances are substituted.'},503);}
}};
