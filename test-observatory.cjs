const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
async function worker(){return (await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('dist/server/index.js','utf8')).toString('base64'))).default;}
test('spectator routes contain no simulation or execution controls',async()=>{
 const app=await worker();const html=await(await app.fetch(new Request('https://garden.test/'),{})).text();
 assert.match(html,/<title>Garden of Flies<\/title>/);assert.doesNotMatch(html,/<button|engine\.js|app\.js|pilot-status\.json/);
 for(const route of ['/engine.js','/pilot-status.json','/api/start','/api/step']){
  const r=await app.fetch(new Request('https://garden.test'+route),{});assert.equal(r.status,404);
 }
 assert.equal((await app.fetch(new Request('https://garden.test/api/start',{method:'POST'}),{})).status,405);
 assert.equal((await app.fetch(new Request('https://garden.test/api/heartbeat',{method:'POST',body:'{}'}),{})).status,401);
});
test('provider failure does not produce invented balances',async()=>{
 const app=await worker();const r=await app.fetch(new Request('https://garden.test/api/status'),{});
 assert.equal(r.status,503);const body=await r.json();assert.ok(body.error);assert.equal(body.wallets,undefined);
});
