"""Persistent, local neural pilot. All economic settlement remains paper-only."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
from decimal import Decimal as D
from pilot_chain import load_config, preflight
from pilot_wallets import Wallets

ROOT=Path(__file__).parent
STATE=ROOT/'.garden'
WEI=10**18

class Journal:
    def __init__(self,path=None):
        STATE.mkdir(exist_ok=True)
        self.db=sqlite3.connect(path or STATE/'pilot.sqlite',check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), tick INTEGER NOT NULL, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS brains (id INTEGER PRIMARY KEY, state BLOB NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, tick INTEGER NOT NULL, body TEXT NOT NULL)')
        self.db.commit()

    def load(self):
        row=self.db.execute('SELECT body FROM checkpoint WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def save(self,state,brain_states,events):
        with self.db:
            current=self.db.execute('SELECT tick FROM checkpoint WHERE id=1').fetchone()
            if current and state['tick']!=current[0]+1:
                raise ValueError('Duplicate or nonsequential checkpoint rejected')
            self.db.execute('INSERT OR REPLACE INTO checkpoint VALUES (1,?,?)',(state['tick'],json.dumps(state)))
            for i,blob in enumerate(brain_states):
                self.db.execute('INSERT OR REPLACE INTO brains VALUES (?,?)',(i,blob))
            for event in events:
                self.db.execute('INSERT INTO events (tick,body) VALUES (?,?)',(state['tick'],json.dumps(event)))

class Pilot:
    def __init__(self, brains=None,journal=None,wallets=None,market=None):
        self.config=load_config()
        self.market=market
        self.wallets=wallets or Wallets().public()
        self.journal=journal or Journal()
        if brains is None:
            from pilot_brain import BrainGarden
            brains=BrainGarden()
        self.brains=brains
        self.state=self.journal.load() or {'mode':'neural_paper','tick':0,'updated_at':None,
              'flies':[{**w,'paper_cash_wei':int(self.config['funding_allocations'][w['id']]['budget_wei']) if self.config.get('funding_allocations') else int(self.config['per_fly_budget_wei']),
                        'goods':[5000,2000] if w['id']%2==0 else [2000,5000],
                        'telemetry':None,'resource_income_wei':0,'resource_spending_wei':0} for w in self.wallets]}
        if [f['address'] for f in self.state['flies']] != [w['address'] for w in self.wallets]:
            raise ValueError('Wallet set differs from persisted economy')
        for i,blob in self.journal.db.execute('SELECT id,state FROM brains'):
            self.brains.restore(i,blob)

    def ask(self,seller):
        return max(10**11,12*10**12*4000//(4000+seller['goods'][seller['id']%2]))

    def tick(self):
        self.state['tick']+=1
        events=[]
        flies=self.state['flies']
        opening_worth=[f['paper_cash_wei']+f.get('token_value_wei',0) for f in flies]
        self.state.setdefault('paper_external_net_wei',0)
        if self.market:
            # Quotes fail closed: no invented price may become a checkpoint.
            for fly in flies:self.market.mark(fly)
        # Rotate execution order so one fly never always gets first choice.
        order=flies[self.state['tick']%10:]+flies[:self.state['tick']%10]
        for fly in order:
            i=fly['id'];own=i%2;other=1-own;before=fly['paper_cash_wei']
            fly['goods']=[n*99//100 for n in fly['goods']]
            action,telemetry=self.brains.decide(i,{'cash_fraction':fly['paper_cash_wei']/10**15,
                'own_inventory':fly['goods'][own]/1000,'input_inventory':fly['goods'][other]/1000,
                'margin':.5,'token_exposure':fly.get('token_value_wei',0)/max(1,fly['paper_cash_wei']+fly.get('token_value_wei',0))},self.state['tick'])
            fly['telemetry']=telemetry
            if action=='buy_input' and fly['goods'][other]<3000:
                sellers=sorted([s for s in flies if s['id']%2==other and s['goods'][other]>=1000],key=self.ask)
                for seller in sellers:
                    cost=self.ask(seller)
                    if self.ask(fly)*2<=cost or fly['paper_cash_wei']-cost<int(self.config['gas_reserve_wei']):continue
                    fly['paper_cash_wei']-=cost;seller['paper_cash_wei']+=cost
                    fly['goods'][other]+=1000;seller['goods'][other]-=1000
                    fly['resource_spending_wei']+=cost;seller['resource_income_wei']+=cost
                    events.append({'kind':'paper_resource_trade','buyer':i,'seller':seller['id'],'wei':str(cost),
                                   'resource':'nectar' if other==0 else 'silk','settlement':'paper_only'})
                    break
            elif action=='produce' and fly['goods'][other]>=1000:
                fly['goods'][other]-=1000;fly['goods'][own]+=2000
            elif action=='inspect_market':
                if self.market:
                    event=self.market.decide(fly,self.state['tick'])
                    if event:
                        events.append(event)
                        self.state['paper_external_net_wei']+=int(event['wei'])*(1 if event['kind']=='paper_pons_buy' else -1)
                else:
                    events.append({'kind':'market_blocked','fly':i,'reason':'Mainnet paper quotes disabled; no token trade executed'})
            fly['goods'][own]+=100  # Passive gathering; never mints ETH.
        for fly in flies:
            if self.market:
                value=self.market.mark(fly)
                stop=int(self.config['per_fly_budget_wei'])*(10000-self.config['max_drawdown_bps'])//10000
                if value and (value>fly['paper_cash_wei'] or value+fly['paper_cash_wei']<stop):
                    event=self.market.decide(fly,self.state['tick'])
                    if event:
                        events.append(event)
                        self.state['paper_external_net_wei']-=int(event['wei'])
            self.brains.reward(fly['id'],(fly['paper_cash_wei']+fly.get('token_value_wei',0)-opening_worth[fly['id']])/WEI)
        assert sum(f['paper_cash_wei'] for f in flies)+self.state['paper_external_net_wei']==int(self.config['total_budget_wei'])
        assert all(f['paper_cash_wei']>=0 and min(f['goods'])>=0 for f in flies)
        self.state['updated_at']=time.time()
        self.state['events']=events
        self.state['audit']={'paper_eth_conserved_including_external_market':True,'broadcast_enabled':False,'gas_modeled':False}
        self.journal.save(self.state,[self.brains.checkpoint(i) for i in range(10)],events)
        return self.state

def setup():
    STATE.mkdir(exist_ok=True)
    connection=STATE/'connection.json'
    if not connection.exists():
        connection.write_text(json.dumps({'rpc_url':''},indent=2))
    wallets=Wallets();wallets.create()
    verified=wallets.verify_signers()
    result=preflight(wallets.public())
    result['signers_verified']=len(verified)
    result['brain_data_ready']=(ROOT/'build'/'graph.npz').exists()
    (STATE/'preflight.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--setup',action='store_true');parser.add_argument('--steps',type=int,default=0);parser.add_argument('--market-quotes',action='store_true')
    args=parser.parse_args()
    if args.setup:print(json.dumps(setup(),indent=2))
    if args.steps:
        from pilot_paper_market import PaperMarket
        pilot=Pilot(market=PaperMarket() if args.market_quotes else None)
        for _ in range(args.steps):
            state=pilot.tick();print(json.dumps({'tick':state['tick'],'events':len(state['events']),'firing':[f['telemetry']['firing'] for f in state['flies']],'audit':state['audit']}),flush=True)
