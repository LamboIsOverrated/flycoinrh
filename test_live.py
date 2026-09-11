import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from eth_abi import decode
from live_execution import Execution, data, TOKEN, ROUTER, WETH

class Wallets:
    def public(self):return [{'id':i,'name':str(i),'address':'0x'+format(i+1,'040x')} for i in range(10)]

class FakeRpc:
    def __init__(self):self.receipt=None;self.head=100;self.nonce=0
    def call(self,method,params=None):
        if method=='eth_blockNumber':return hex(self.head)
        if method=='eth_getTransactionReceipt':return self.receipt
        if method=='eth_getTransactionCount':return hex(self.nonce)
        if method=='eth_getBlockByNumber':return {'hash':'0xabc'}
        raise AssertionError('Unexpected RPC: '+method)

class LiveTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.path=Path(self.directory.name)/'live.sqlite'
        self.rpc=FakeRpc();self.e=Execution(self.rpc,Wallets(),self.path)
    def tearDown(self):self.e.db.close();self.directory.cleanup()

    def test_disabled_gate_before_network_or_signature(self):
        with self.assertRaises(PermissionError):self.e.submit(0,'buy_pons','test',amount=10**14)
        self.assertEqual(self.e.db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],0)

    def test_buy_and_atomic_eth_exit_recipients_and_minimum(self):
        with patch('live_execution.inspect_market',return_value={'bought_units':str(10**18)}),patch('live_execution.sell_quote',return_value=10**14):
            buy=self.e.construct(0,'buy_pons',10**14)
            deadline,calls=decode(['uint256','bytes[]'],bytes.fromhex(buy['data'][10:]))
            self.assertLessEqual(deadline,int(time.time())+30);self.assertEqual(len(calls),1)
            args=decode(['(address,address,uint24,address,uint256,uint256,uint160)'],calls[0][4:])[0]
            self.assertEqual(args[0].lower(),WETH.lower());self.assertEqual(args[3],Wallets().public()[0]['address'])
            self.assertGreater(args[5],0)
            sale=self.e.construct(0,'sell_pons',10**18)
            _,calls=decode(['uint256','bytes[]'],bytes.fromhex(sale['data'][10:]))
            self.assertEqual(len(calls),2);self.assertEqual(sale['value'],0)
            params=decode(['(address,address,uint24,address,uint256,uint256,uint160)'],calls[0][4:])[0]
            self.assertEqual(params[3],ROUTER.lower())
            minimum,recipient=decode(['uint256','address'],calls[1][4:])
            self.assertEqual(recipient,Wallets().public()[0]['address']);self.assertEqual(minimum,params[5])

    def insert(self):
        self.e.db.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)',('once',0,'buy_pons','{}',0,'0x123','sealed','signed',None,time.time()));self.e.db.commit()

    def test_receipt_confirmation_reorg_and_restart(self):
        self.insert();self.assertTrue(self.e.open_tx(0))
        self.rpc.receipt={'blockNumber':hex(99),'blockHash':'0xabc','status':'0x1'}
        self.e.reconcile();self.assertEqual(self.e.open_tx(0)['status'],'mined')
        self.rpc.receipt=None;self.e.reconcile();self.assertEqual(self.e.open_tx(0)['status'],'signed')
        self.e.db.close();self.e=Execution(self.rpc,Wallets(),self.path)
        self.assertEqual(self.e.open_tx(0)['hash'],'0x123')
        self.rpc.receipt={'blockNumber':hex(89),'blockHash':'0xabc','status':'0x1'}
        self.e.reconcile();self.assertIsNone(self.e.open_tx(0))
        self.assertEqual(self.e.events()[0]['status'],'confirmed')

    def test_unknown_nonce_and_duplicate_nonce_stop(self):
        self.insert();self.rpc.nonce=1
        with self.assertRaises(RuntimeError):self.e.reconcile()
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.e.db.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)',('twice',0,'buy_pons','{}',0,'0x456','sealed','signed',None,time.time()))

    def test_deployment_metadata_recovers_after_receipt_commit_crash(self):
        self.insert()
        receipt={'contractAddress':'0x'+'f'*40,'gasUsed':hex(100),'effectiveGasPrice':hex(2)}
        self.e.db.execute("UPDATE transactions SET kind='deploy',status='confirmed',receipt=?",(json.dumps(receipt),));self.e.db.commit()
        with patch.object(self.e,'settlement',return_value=receipt['contractAddress']):self.e.reconcile()
        self.assertEqual(self.e.meta('settlement'),receipt['contractAddress'])
        self.assertEqual(self.e.meta('setup_cost_wei'),200)

    def test_unavailable_or_wrong_backup_does_not_pass(self):
        from live_execution import backup_ready
        self.assertFalse(backup_ready(Wallets(),Path(self.directory.name)))
        with patch('live_execution.backup_ready',return_value=False):
            self.e.cfg={**self.e.cfg,'broadcast_enabled':True}
            with self.assertRaises(PermissionError):self.e.gate()

if __name__=='__main__':unittest.main()
