const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base='./.garden/evm/node_modules/';
const solc=require(base+'solc'),ganache=require(base+'ganache'),{ethers}=require(base+'ethers');
const source=fs.readFileSync('contracts/FlyGarden.sol','utf8');
const output=JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources:{'FlyGarden.sol':{content:source}},settings:{optimizer:{enabled:true,runs:200},evmVersion:'shanghai',outputSelection:{'*':{'*':['abi','evm.bytecode.object','evm.deployedBytecode.object']}}}})));
const errors=(output.errors||[]).filter(e=>e.severity==='error');assert.deepEqual(errors,[]);
const artifact=output.contracts['FlyGarden.sol'].FlyGarden;
fs.mkdirSync('build',{recursive:true});fs.writeFileSync('build/FlyGarden.json',JSON.stringify({compiler:solc.version(),sourceSha256:require('crypto').createHash('sha256').update(source).digest('hex'),...artifact},null,2));
test('on-chain resources, exact settlement, restrictions and cooldown',async()=>{
 const chain=ganache.provider({logging:{quiet:true},wallet:{totalAccounts:11},chain:{chainId:4663,hardfork:'shanghai'}});
 try{
  const provider=new ethers.BrowserProvider(chain);provider.pollingInterval=10;
  const signers=await Promise.all(Array.from({length:11},(_,i)=>provider.getSigner(i))),addresses=await Promise.all(signers.slice(0,10).map(s=>s.getAddress()));
  const contract=await new ethers.ContractFactory(artifact.abi,artifact.evm.bytecode.object,signers[0]).deploy(addresses);await contract.waitForDeployment();
  assert.equal(await contract.member(addresses[9]),10n);
  const price=await contract.ask(addresses[1]);
  const before=BigInt(await chain.request({method:'eth_getBalance',params:[addresses[1],'latest']}));
  await(await contract.buy(addresses[1],price,{value:price})).wait();
  assert.equal(await contract.resourceBalance(addresses[0],1),3n);
  assert.equal(await contract.resourceBalance(addresses[1],1),4n);
  const after=BigInt(await chain.request({method:'eth_getBalance',params:[addresses[1],'latest']}));assert.equal(after-before,price);
  assert.equal(await provider.getBalance(await contract.getAddress()),0n);
  await assert.rejects(contract.buy(addresses[0],price,{value:price}));
  await assert.rejects(contract.buy(addresses[2],price,{value:price}));
  await assert.rejects(contract.buy(addresses[1],price-1n,{value:price}));
  await assert.rejects(contract.connect(signers[10]).produce());
  await assert.rejects(contract.connect(signers[1]).setAsk(ethers.parseEther('.1')));
  await(await contract.produce()).wait();assert.equal(await contract.resourceBalance(addresses[0],0),7n);assert.equal(await contract.resourceBalance(addresses[0],1),2n);
  await(await contract.harvest()).wait();await assert.rejects(contract.harvest.staticCall());
  await(await contract.connect(signers[1]).setAsk(0)).wait();await assert.rejects(contract.buy.staticCall(addresses[1],price,{value:price}));
  await assert.rejects(new ethers.ContractFactory(artifact.abi,artifact.evm.bytecode.object,signers[0]).deploy(Array(10).fill(addresses[0])));
 }finally{await chain.disconnect();}
});
