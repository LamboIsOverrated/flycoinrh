// Compile only the independently verified factory build's curve/token sources.
const fs=require('node:fs'),crypto=require('node:crypto'),solc=require('./.garden/pons-compiler/node_modules/solc');
const record=JSON.parse(fs.readFileSync('scratch/verified-factory.json','utf8'));
if(!solc.version().startsWith(record.compilation.compilerVersion))throw new Error('Compiler version mismatch');
const input=record.stdJsonInput;
input.settings.outputSelection={'*':{'*':['evm.deployedBytecode.object','evm.deployedBytecode.immutableReferences','evm.deployedBytecode.linkReferences']}};
const result=JSON.parse(solc.compile(JSON.stringify(input)));
if((result.errors||[]).some(e=>e.severity==='error'))throw new Error(JSON.stringify(result.errors));
const targets={};
for(const [file,contracts] of Object.entries(result.contracts))for(const [name,data] of Object.entries(contracts)){
 if(['PonsV2BondingCurve','PonsV2LauncherToken'].includes(name))targets[name]={...data.evm.deployedBytecode,sourceSha256:crypto.createHash('sha256').update(input.sources[file].content).digest('hex')};
}
fs.writeFileSync('scratch/pons-bytecode-templates.json',JSON.stringify(targets));
console.log(JSON.stringify(Object.fromEntries(Object.entries(targets).map(([k,v])=>[k,v.object.length/2]))));
