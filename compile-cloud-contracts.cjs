const fs=require('node:fs'),crypto=require('node:crypto');
let solc;try{solc=require('solc')}catch{solc=require('./.garden/evm/node_modules/solc')}
fs.mkdirSync('build',{recursive:true});
for(const name of ['FlyGarden','QuoteProbe']){
 const source=fs.readFileSync('contracts/'+name+'.sol','utf8');
 const result=JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources:{[name+'.sol']:{content:source}},settings:{optimizer:{enabled:true,runs:200},evmVersion:name==='FlyGarden'?'shanghai':'paris',outputSelection:{'*':{'*':['abi','evm.bytecode.object','evm.deployedBytecode.object']}}}})));
 if((result.errors||[]).some(e=>e.severity==='error'))throw Error(JSON.stringify(result.errors));
 fs.writeFileSync('build/'+name+'.json',JSON.stringify({compiler:solc.version(),sourceSha256:crypto.createHash('sha256').update(source).digest('hex'),...result.contracts[name+'.sol'][name]}));
}
console.log('Garden settlement and quote artifacts compiled.');
