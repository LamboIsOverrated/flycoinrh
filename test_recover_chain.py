import unittest,json,tempfile
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from eth_abi import encode
from live_execution import Execution,data,TOKEN
from recover_chain import recover,RECORDS,CONTRACT

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.wallets=json.loads(Path('web/wallets.json').read_text())
  self.e=Execution(wallets=SimpleNamespace(public=lambda:self.wallets),path=':memory:')
  self.artifact={'evm':{'bytecode':{'object':'1234'},'deployedBytecode':{'object':'abcd'}}}
  self.extra=False;self.bad=False
 def tearDown(self):self.e.db.close()
 def call(self,method,params=None):
  if method=='eth_blockNumber':return hex(60420000)
  if method=='eth_getCode':return '0xabcd'
  if method=='eth_getTransactionCount':return hex((1 if params[0] in [w['address'] for w in self.wallets[:2]] else 0)+(1 if self.extra else 0))
  if method=='eth_getBalance':
   i=next(w['id'] for w in self.wallets if w['address']==params[0]);a,b=self.e.allocation(i);return hex(a+b-(100 if i<2 else 0))
  index=next(i for i,r in enumerate(RECORDS) if (hex(r[1])==params[0] if method=='eth_getBlockByNumber' else r[2]==params[0]))
  fly,height,h,kind=RECORDS[index];address=self.wallets[fly]['address']
  if method=='eth_getBlockByNumber':
   calldata='0x1234'+encode(['address[10]'],[[w['address'] for w in self.wallets]]).hex() if fly==0 else data('produce()')
   return {'hash':'0xabc','timestamp':'0x123','transactions':[{'hash':h,'from':address,'nonce':'0x0','value':'0x0','to':None if fly==0 else CONTRACT,'input':calldata}]}
  return {'blockHash':'0xwrong' if self.bad else '0xabc','blockNumber':hex(height),'transactionHash':h,'status':'0x1','from':address,'contractAddress':CONTRACT if fly==0 else None,'gasUsed':'0x64','effectiveGasPrice':'0x1'}
 def view(self,address,signature,outputs,types,values,block):
  return (self.wallets[values[0]]['address'],) if signature.startswith('flies') else (0,)
 def run_recovery(self):
  with patch.object(self.e,'verify_code'),patch.object(self.e,'artifact',return_value=self.artifact),patch.object(self.e.rpc,'call',side_effect=self.call),patch.object(self.e.rpc,'view',side_effect=self.view):return recover(self.e)
 def test_atomic_recovery_and_idempotence(self):
  self.assertTrue(self.run_recovery());self.assertFalse(self.run_recovery())
  self.assertEqual(len(self.e.events()),2);self.assertEqual(self.e.meta('setup_cost_wei'),100)
  self.assertEqual(self.e.meta('initial_funding')['amounts'],[self.e.allocation(i)[0] for i in range(10)])
  self.assertIsNone(self.e.open_tx(0))
 def test_unknown_nonce_writes_nothing(self):
  self.extra=True
  with self.assertRaisesRegex(ValueError,'history'):self.run_recovery()
  self.assertFalse(self.e.events());self.assertIsNone(self.e.meta('initial_funding'))
 def test_mismatched_receipt_writes_nothing(self):
  self.bad=True
  with self.assertRaisesRegex(ValueError,'receipt'):self.run_recovery()
  self.assertFalse(self.e.events());self.assertIsNone(self.e.meta('settlement'))
