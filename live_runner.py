"""Automatic garden service. The website has no execution controls.

Starts observing immediately; signs only after backup, exact initial funding,
chain/code verification, and the configured activation flag all pass.
"""
import argparse
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
import requests
from live_execution import Execution, backup_ready, ROOT, TOKEN, ROUTER, sell_quote

class Garden:
    def __init__(self):
        if os.name!='nt':
            from cloud_wallets import CloudWallets
            self.execution=Execution(wallets=CloudWallets())
        else:self.execution=Execution()
        self.brains=None;self.brain_error=None
        self.db=self.execution.db
        self.db.execute('CREATE TABLE IF NOT EXISTS brains (id INTEGER PRIMARY KEY, state BLOB NOT NULL)')
        self.db.commit()
        self.round=self.execution.meta('round') or 0
        self.telemetry=self.execution.meta('telemetry') or []
        self.status='starting';self.stop=threading.Event()
        self.brain_thread=None

    def load_brains(self):
        def load():
            try:
                from pilot_brain import BrainGarden
                b=BrainGarden()
                # Separate connection avoids concurrent cursor use during the load.
                db=sqlite3.connect(ROOT/'.garden/live.sqlite')
                for i,state in db.execute('SELECT id,state FROM brains'):b.restore(i,state)
                db.close();self.brains=b
            except Exception:self.brain_error='Neural engine could not load; execution stopped'
        self.brain_thread=threading.Thread(target=load,daemon=True);self.brain_thread.start()

    def publish(self,rows,error=None):
        settings_path=ROOT/'.garden/publisher.json'
        state={'observed_at':time.time(),'status':self.status,'round':self.round,'error':error,
               'backup_ready':backup_ready(self.execution.wallets),'enabled':self.execution.cfg['broadcast_enabled'],
               'settlement':self.execution.meta('settlement'),'telemetry':self.telemetry,
               'transactions':self.execution.events()}
        # Wallet amounts are read independently by the website; never accept paper fields.
        target=ROOT/'.garden/live-status.json';temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(state),encoding='utf-8');os.replace(temp,target)
        settings=json.loads(settings_path.read_text()) if settings_path.exists() else {
            'url':os.getenv('GARDEN_SITE_URL',''), 'publisher_key':os.getenv('GARDEN_PUBLISHER_KEY',''),
            'site_token':os.getenv('GARDEN_SITE_TOKEN','')}
        if all(settings.get(k) for k in ['url','publisher_key','site_token']):
            try:
                r=requests.post(settings['url']+'/api/heartbeat',json=state,headers={
                    'Authorization':'Bearer '+settings['publisher_key'],
                    'OAI-Sites-Authorization':'Bearer '+settings['site_token']},timeout=15)
                if r.status_code!=200:print('Website heartbeat delivery failed; local state retained',flush=True)
            except requests.RequestException:print('Website unreachable; local state retained',flush=True)

    def round_once(self):
        e=self.execution;e.reconcile();rows=e.balances()
        if self.brain_error:self.status='stopped';self.publish(rows,self.brain_error);return
        funded=e.meta('initial_funding')
        ready=backup_ready(e.wallets) and e.cfg['broadcast_enabled']
        if not ready:self.status='waiting_for_backup' if not backup_ready(e.wallets) else 'observing'
        elif not funded and any(int(e.rpc.call('eth_getTransactionCount',[r['address'],'latest']),16) for r in rows):
            self.status='recovery_required'
        elif not funded and not e.funding_matches(rows):self.status='waiting_for_funding'
        else:
            e.gate();e.rebroadcast()
            if not e.settlement():
                self.status='deploying'
                if not e.open_tx(0):e.submit(0,'deploy','garden-deployment-v1')
            else:self.status='running'
        if self.brains is None:
            self.publish(rows);return
        self.round+=1;telemetry=[]
        settlement=e.settlement()
        for row in rows:
            i=row['id'];value=sell_quote(row['pons_units'],e.rpc) if row['pons_units'] else 0
            own=other=0
            if settlement:
                own=e.rpc.view(settlement,'resourceBalance(address,uint8)',['uint256'],['address','uint8'],[row['address'],i%2])[0]
                other=e.rpc.view(settlement,'resourceBalance(address,uint8)',['uint256'],['address','uint8'],[row['address'],1-i%2])[0]
            action,t=self.brains.decide(i,{'cash_fraction':row['eth_wei']/10**15,'own_inventory':own,
                                         'input_inventory':other,'margin':0,'token_exposure':value/max(1,value+row['eth_wei'])},self.round)
            t.update({'id':i,'measured_at':time.time(),'observation_block':row['block']})
            telemetry.append(t)
            self.telemetry=telemetry+[old for old in self.telemetry if old['id']>i]
            self.publish(rows)
            previous=e.meta('worth-'+str(i))
            worth=row['eth_wei']+value
            if previous is not None:self.brains.reward(i,(worth-previous)/10**18)
            e.meta('worth-'+str(i),worth)
            if self.status!='running' or e.open_tx(i):continue
            baseline=e.allocation(i)[0]-((e.meta('setup_cost_wei') or 0) if i==0 else 0)
            stop=worth*10000<baseline*(10000-e.cfg['max_drawdown_bps'])
            pending_exit=e.meta('exit-'+str(i))
            if not row['pons_units'] and pending_exit:e.meta('exit-'+str(i),False)
            force_exit=value>row['eth_wei'] or stop or bool(pending_exit)
            last=e.db.execute("SELECT MAX(created) FROM transactions WHERE fly=? AND kind IN ('buy_pons','sell_pons','approve_pons')",(i,)).fetchone()[0] or 0
            key=f'round-{self.round}-fly-{i}'
            try:
                if row['pons_units'] and (force_exit or (action=='inspect_market' and time.time()-last>3600 and value>worth*45//100)):
                    allowance=e.rpc.view(TOKEN,'allowance(address,address)',['uint256'],['address','address'],[row['address'],ROUTER])[0]
                    if allowance<row['pons_units']:
                        e.meta('exit-'+str(i),True)
                        e.submit(i,'approve_pons',key,amount=row['pons_units'])
                    else:e.submit(i,'sell_pons',key,amount=row['pons_units'])
                elif stop:continue
                elif action=='inspect_market' and time.time()-last>3600:
                    amount=min(int(e.cfg['max_trade_wei']),max(0,(row['eth_wei']-value)//2-int(e.cfg['gas_reserve_wei'])))
                    if amount>=10**12:e.submit(i,'buy_pons',key,amount=amount)
                elif action=='buy_input' and other<2:
                    sellers=[]
                    for seller in rows:
                        if seller['id']%2==i%2:continue
                        stock=e.rpc.view(settlement,'resourceBalance(address,uint8)',['uint256'],['address','uint8'],[seller['address'],1-i%2])[0]
                        ask=e.rpc.view(settlement,'ask(address)',['uint256'],['address'],[seller['address']])[0]
                        if stock and ask:sellers.append((ask,seller['id']))
                    if sellers:
                        ask,seller_id=min(sellers)
                        own_ask=e.rpc.view(settlement,'ask(address)',['uint256'],['address'],[row['address']])[0]
                        if own_ask*2>ask:e.submit(i,'buy_resource',key,seller=seller_id)
                elif action=='produce' and other:e.submit(i,'produce',key)
                elif own<2:e.submit(i,'harvest',key)
            except (ValueError,PermissionError):
                t['execution']='Rejected by spending, quote, or loss limits'
        # Financial state always comes from the chain. Neural checkpoints never
        # turn a planned transaction into a claimed trade after a crash.
        with self.db:
            for i in range(10):self.db.execute('INSERT OR REPLACE INTO brains VALUES (?,?)',(i,self.brains.checkpoint(i)))
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('round',json.dumps(self.round)))
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('telemetry',json.dumps(telemetry)))
        self.telemetry=telemetry;self.publish(rows)

    def run(self):
        self.load_brains()
        while not self.stop.is_set():
            if (ROOT/'.garden/STOP').exists():break
            try:self.round_once()
            except Exception:
                self.status='stopped'
                self.publish([], 'A chain or recovery check failed; no new transactions will be created')
                # The supervisor restarts from the last atomic checkpoint. Saved
                # transaction IDs and nonces make repeated rounds idempotent.
                raise
            self.stop.wait(120)

def main():
    (ROOT/'.garden').mkdir(exist_ok=True)
    lock=open(ROOT/'.garden/live.lock','a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:raise SystemExit('The garden service is already running')
    garden=Garden()
    try:
        if os.getenv('PORT'):
            from cloud_health import start_health
            start_health(garden)
        garden.run()
    finally:garden.execution.db.close();lock.close()

if __name__=='__main__':main()
