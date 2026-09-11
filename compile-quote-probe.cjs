const fs=require('node:fs');
const solc=require('./.garden/evm/node_modules/solc');
const source=fs.readFileSync('contracts/QuoteProbe.sol','utf8');
const out=JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources:{'QuoteProbe.sol':{content:source}},settings:{optimizer:{enabled:true,runs:200},evmVersion:'paris',outputSelection:{'*':{'*':['abi','evm.deployedBytecode.object']}}}})));
if((out.errors||[]).some(e=>e.severity==='error'))throw Error(JSON.stringify(out.errors));
fs.mkdirSync('build',{recursive:true});
fs.writeFileSync('build/QuoteProbe.json',JSON.stringify(out.contracts['QuoteProbe.sol'].QuoteProbe));
console.log('Read-only quote probe compiled; no deployment.');
