import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from pilot_chain import Rpc, Curve, buy_intent, load_config
from pilot_runtime import Journal, Pilot
from pilot_wallets import Wallets

ADDRESS='0x'+'1'*40

class FakeBrains:
    def decide(self,i,observation,tick):return 'buy_input',{'firing':1,'neurons':1,'spikes_per_sec':1,'action':'buy_input'}
    def reward(self,*args):pass
    def checkpoint(self,i):return b'test-only'
    def restore(self,*args):pass

class Tests(unittest.TestCase):
    def test_router_comparison_rejects_opcode_and_nonaddress_changes(self):
        from verify_v3_router import compare
        template=b'\x7f'+bytes(32)+b'\x00'
        actual=b'\x7f'+bytes.fromhex(ADDRESS[2:]).rjust(32,b'\0')+b'\x00'
        self.assertEqual(compare(template,actual,[ADDRESS]),1)
        for bad in [actual[:-1]+b'\x01',actual[:-2]+b'\x02\x00',actual+b'\x00']:
            with self.assertRaises(ValueError):compare(template,bad,[ADDRESS])

    def test_paper_market_cap_cooldown_and_loss_stop(self):
        from pilot_paper_market import PaperMarket
        m=PaperMarket();f={'id':0,'paper_cash_wei':10**15}
        with patch('pilot_paper_market.inspect_market',side_effect=lambda amount:{'bought_units':str(amount),'block':1}),patch('pilot_paper_market.sell_quote',side_effect=lambda units:units*98//100):
            for tick in range(100):
                e=m.decide(f,tick)
                self.assertLessEqual(f.get('token_value_wei',0),f['paper_cash_wei'])
                if e:self.assertEqual(e['settlement'],'paper_only')
            f['paper_cash_wei']=10**14
            e=m.decide(f,101)
            self.assertEqual(e['kind'],'paper_pons_sell');self.assertEqual(f['pons_units'],0)
            self.assertIsNone(m.decide(f,120))

    def test_paper_token_trades_survive_restart_with_external_ledger(self):
        from pilot_paper_market import PaperMarket
        class MarketBrains(FakeBrains):
            def decide(self,*args):return 'inspect_market',{'action':'inspect_market'}
        with tempfile.TemporaryDirectory() as d,patch('pilot_paper_market.inspect_market',side_effect=lambda amount:{'bought_units':str(amount),'block':1}),patch('pilot_paper_market.sell_quote',side_effect=lambda units:units*98//100):
            path=Path(d)/'journal.sqlite';wallets=[{'id':i,'name':str(i),'address':'0x'+format(i+1,'040x')} for i in range(10)]
            p=Pilot(MarketBrains(),Journal(path),wallets,PaperMarket());p.tick()
            self.assertEqual(len(p.state['events']),10)
            self.assertEqual(sum(f['paper_cash_wei'] for f in p.state['flies'])+p.state['paper_external_net_wei'],int(p.config['total_budget_wei']))
            q=Pilot(MarketBrains(),Journal(path),wallets,PaperMarket());self.assertEqual(p.state,q.state)
            q.journal.db.close();p.journal.db.close()

    def curve(self):return Curve(ADDRESS,ADDRESS,100,time.time(),10**18,10**25,10**17,10**20,100,100,'test')

    def test_rpc_can_never_broadcast(self):
        for method in ['eth_sendRawTransaction','eth_sendTransaction','personal_sign','eth_sign']:
            with self.assertRaises(PermissionError):Rpc('https://example.com').call(method,[])

    def test_exposure_fees_and_stale_quotes(self):
        c=self.curve();cfg=load_config()
        intent=buy_intent(c,ADDRESS,10**14,10**15,0,10**12,cfg)
        self.assertEqual(intent['from'],ADDRESS);self.assertGreater(int(intent['minimum_units']),0)
        with self.assertRaises(ValueError):buy_intent(c,ADDRESS,10**14,6*10**14,5*10**14,10**12,cfg)
        with self.assertRaises(ValueError):buy_intent(c,ADDRESS,10**14,10**15,0,10**12,cfg,now=c.observed_at+31)
        with self.assertRaises(ValueError):buy_intent(c,ADDRESS,True,10**15,0,10**12,cfg)

    def test_curve_fee_rounding_and_liquidity(self):
        c=self.curve();spend=10**14;net=spend-spend//100-spend//100
        self.assertEqual(c.buy_quote(spend),net*c.token_reserve//(c.quote_reserve+net))
        with self.assertRaises(ValueError):c.sell_quote(10**30)

    def test_atomic_persistence_restart_and_conservation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.sqlite';wallets=[{'id':i,'name':str(i),'address':'0x'+format(i+1,'040x')} for i in range(10)]
            p=Pilot(FakeBrains(),Journal(path),wallets)
            for _ in range(10):p.tick()
            self.assertEqual(sum(f['paper_cash_wei'] for f in p.state['flies']),int(p.config['total_budget_wei']))
            restarted=Pilot(FakeBrains(),Journal(path),wallets)
            self.assertEqual(restarted.state,p.state)
            with self.assertRaises(ValueError):restarted.journal.save(p.state,[],[])
            restarted.journal.db.close();p.journal.db.close()

    def test_wallet_encryption_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'vault.json';w=Wallets(path);public=w.create();before=path.read_bytes()
            self.assertEqual(w.create(),public);self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len(w.verify_signers()),10)
            self.assertTrue(all('sealed' not in row for row in public))
            data=json.loads(path.read_text());self.assertTrue(all(len(r['sealed'])>100 for r in data['wallets']))

if __name__=='__main__':unittest.main()
