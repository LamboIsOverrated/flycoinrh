const fs=require('node:fs'),path=require('node:path');
const root=__dirname,assets={};
for(const [file,type] of [['index.html','text/html; charset=utf-8'],['observatory.js','text/javascript; charset=utf-8'],['observatory.css','text/css; charset=utf-8']])assets['/'+file]={type,body:fs.readFileSync(path.join(root,'web',file),'utf8')};
const wallets=JSON.parse(fs.readFileSync(path.join(root,'web/wallets.json'),'utf8'));
const output=path.join(root,'dist');
// Explicit known obsolete assets only; paper tools remain in Git history.
for(const file of ['index.html','app.js','engine.js','garden.css','pilot.html','pilot.css','pilot.js','pilot-status.json']){
 const p=path.join(output,file);if(fs.existsSync(p))fs.unlinkSync(p);
}
fs.mkdirSync(path.join(output,'server'),{recursive:true});fs.mkdirSync(path.join(output,'.openai/drizzle'),{recursive:true});
fs.writeFileSync(path.join(output,'server/index.js'),'const ASSETS='+JSON.stringify(assets)+';\nconst WALLETS='+JSON.stringify(wallets)+';\n'+fs.readFileSync(path.join(root,'web/worker.mjs'),'utf8'));
fs.copyFileSync(path.join(root,'.openai/hosting.json'),path.join(output,'.openai/hosting.json'));
fs.copyFileSync(path.join(root,'drizzle/0000_garden_heartbeat.sql'),path.join(output,'.openai/drizzle/0000_garden_heartbeat.sql'));
console.log('Built the real-data observatory. Simulation assets excluded.');
