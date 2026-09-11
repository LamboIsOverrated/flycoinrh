"""Bounded mainnet transaction construction and durable receipt recovery.

No arbitrary transaction API: plans come only from the operations below. All
signed transactions are durable before submission. An unresolved nonce prevents
another transaction from that fly. No signing occurs before backup and funding.
"""
import base64
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from eth_abi import encode, decode
from eth_account import Account
from eth_utils import keccak, to_checksum_address
from pilot_chain import Rpc, load_config
from pilot_wallets import Wallets, protect
from pilot_v3 import TOKEN, POOL, ROUTER, WETH, inspect_market, sell_quote

ROOT=Path(__file__).parent
SWAP='exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))'
PARAM='(address,address,uint24,address,uint256,uint256,uint160)'
PINNED={TOKEN.lower():'0x16c3d3ede897688ddff79262606f13bead398332e65001f192460fbac4e1fb85',
        POOL.lower():'0x6b805cc147fb0d1392158bffce6dbdc926d32a88063ef74b9142efce5320d774',
        ROUTER.lower():'0x6f36c378e272c6324c48f045182bcb54bd8ad654cf9ebd42e8893d52c4cb25dc',
        WETH.lower():'0x5706be52f64875fee65a2cec0d80e47a23d8793cbe85d214b48445e2d05f5353'}

def data(sig,types=(),values=()):
    return '0x'+(keccak(text=sig)[:4]+encode(list(types),list(values))).hex()

def backup_ready(wallets=None,root=ROOT):
    try:
        proof=json.loads((root/'.garden/backup-proof.json').read_text())
        path=root/'.garden/backups'/proof['filename']
        return (path.parent.resolve()==(root/'.garden/backups').resolve()
                and hashlib.sha256(path.read_bytes()).hexdigest()==proof['sha256']
                and proof['addresses']==[w['address'] for w in (wallets or Wallets()).public()])
    except (OSError,ValueError,KeyError):return False

class Execution:
    def __init__(self,rpc=None,wallets=None,path=None,config=None):
        self.rpc=rpc or Rpc();self.wallets=wallets or Wallets();self.cfg=config or load_config()
        self.db=sqlite3.connect(path or ROOT/'.garden/live.sqlite',check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, fly INTEGER NOT NULL, kind TEXT NOT NULL, plan TEXT NOT NULL, nonce INTEGER NOT NULL, hash TEXT NOT NULL UNIQUE, sealed TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT, created REAL NOT NULL, UNIQUE(fly,nonce))')
        self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.commit()

    def meta(self,key,value=None):
        if value is not None:
            with self.db:self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(key,json.dumps(value)))
        row=self.db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def balances(self):
        block=self.rpc.call('eth_blockNumber')
        return [{'id':w['id'],'name':w['name'],'address':w['address'],
                 'eth_wei':int(self.rpc.call('eth_getBalance',[w['address'],block]),16),
                 'pons_units':self.rpc.view(TOKEN,'balanceOf(address)',['uint256'],['address'],[w['address']],block)[0],
                 'block':int(block,16)} for w in self.wallets.public()]

    def verify_code(self):
        self.rpc.validate_chain()
        for address,pin in PINNED.items():
            code=self.rpc.call('eth_getCode',[address,'latest'])
            if '0x'+keccak(bytes.fromhex(code[2:])).hex()!=pin:raise ValueError('Market contract code changed')

    def gate(self):
        if (ROOT/'.garden/STOP').exists():raise PermissionError('Local emergency stop is active')
        if self.cfg['broadcast_enabled'] is not True:raise PermissionError('Sending is disabled')
        if not backup_ready(self.wallets):raise PermissionError('Encrypted wallet backup required')
        self.verify_code()
        if not self.meta('initial_funding'):
            rows=self.balances(); budget=int(self.cfg['per_fly_budget_wei'])
            if any(w['eth_wei']!=budget or w['pons_units']!=0 for w in rows):
                raise PermissionError('Awaiting exactly 0.001 ETH per fly and no token deposits')
            if sum(w['eth_wei'] for w in rows)>int(self.cfg['total_budget_wei']):raise ValueError('Budget exceeded')
            if any(int(self.rpc.call('eth_getTransactionCount',[w['address'],'latest']),16)!=0 for w in rows):
                raise ValueError('Unexpected wallet history before activation')
            self.meta('initial_funding',{'amounts':[w['eth_wei'] for w in rows],'time':time.time()})

    def artifact(self):
        a=json.loads((ROOT/'build/FlyGarden.json').read_text())
        if hashlib.sha256((ROOT/'contracts/FlyGarden.sol').read_bytes()).hexdigest()!=a['sourceSha256']:
            raise ValueError('Settlement artifact is stale; rebuild and test')
        return a

    def settlement(self):
        address=self.meta('settlement')
        if not address:return None
        actual=self.rpc.call('eth_getCode',[address,'latest'])
        if actual.lower()!='0x'+self.artifact()['evm']['deployedBytecode']['object'].lower():
            raise ValueError('Settlement runtime verification failed')
        for w in self.wallets.public():
            found=self.rpc.view(address,'flies(uint256)',['address'],['uint256'],[w['id']])[0]
            if found.lower()!=w['address'].lower():raise ValueError('Settlement wallets differ')
        return address

    def open_tx(self,fly):
        return self.db.execute("SELECT * FROM transactions WHERE fly=? AND status IN ('signed','pending','mined')",(fly,)).fetchone()

    def reconcile(self):
        head=int(self.rpc.call('eth_blockNumber'),16)
        rows=self.db.execute("SELECT * FROM transactions WHERE status IN ('signed','pending','mined')").fetchall()
        for row in rows:
            receipt=self.rpc.call('eth_getTransactionReceipt',[row['hash']])
            if receipt:
                block=self.rpc.call('eth_getBlockByNumber',[receipt['blockNumber'],False])
                if not block or block['hash'].lower()!=receipt['blockHash'].lower():continue
                confirmations=head-int(receipt['blockNumber'],16)+1
                status=('confirmed' if int(receipt['status'],16)==1 else 'reverted') if confirmations>=12 else 'mined'
                with self.db:self.db.execute('UPDATE transactions SET status=?,receipt=? WHERE id=?',(status,json.dumps(receipt),row['id']))
                if status=='confirmed' and row['kind']=='deploy':
                    self.meta('settlement',receipt['contractAddress']);self.settlement()
                    self.meta('setup_cost_wei',int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16))
            else:
                latest=int(self.rpc.call('eth_getTransactionCount',[self.wallets.public()[row['fly']]['address'],'latest']),16)
                if latest>row['nonce']:raise RuntimeError('Unknown transaction consumed a reserved nonce; stopped')
                # Preserve the reservation even if a formerly mined receipt disappears.
                with self.db:self.db.execute("UPDATE transactions SET status='signed',receipt=NULL WHERE id=?",(row['id'],))
        # Rebuild deployment metadata even if the process died between the receipt
        # commit and metadata update. This never submits another deployment.
        deployed=self.db.execute("SELECT receipt FROM transactions WHERE kind='deploy' AND status='confirmed' ORDER BY created LIMIT 1").fetchone()
        if deployed:
            receipt=json.loads(deployed['receipt'])
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('settlement',json.dumps(receipt['contractAddress'])))
                self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('setup_cost_wei',json.dumps(int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16))))
            self.settlement()

    def rebroadcast(self):
        self.gate()
        for row in self.db.execute("SELECT * FROM transactions WHERE status IN ('signed','pending')").fetchall():
            self._send(row)

    def _send(self,row):
        raw=protect(base64.b64decode(row['sealed']),True)
        if '0x'+keccak(raw).hex()!=row['hash']:raise ValueError('Saved signed transaction corrupted')
        if Account.recover_transaction(raw).lower()!=self.wallets.public()[row['fly']]['address'].lower():raise ValueError('Saved signer differs')
        try:
            response=self.rpc.session.post(self.rpc.url,json={'jsonrpc':'2.0','id':1,'method':'eth_sendRawTransaction','params':['0x'+raw.hex()]},timeout=20)
            response.raise_for_status();result=response.json()
            if result.get('result','').lower()!=row['hash'].lower():
                # Already-known and uncertain outcomes are handled identically:
                # keep the same hash and nonce, reconcile before doing anything else.
                return {'status':'uncertain','hash':row['hash']}
        except Exception:return {'status':'uncertain','hash':row['hash']}
        with self.db:self.db.execute("UPDATE transactions SET status='pending' WHERE id=?",(row['id'],))
        return {'status':'pending','hash':row['hash']}

    def construct(self,fly,kind,amount=0,seller=None):
        address=self.wallets.public()[fly]['address'];deadline=int(time.time())+30
        if kind=='deploy':
            if fly!=0 or self.meta('settlement'):raise ValueError('Deployment not allowed')
            a=self.artifact()
            return {'to':None,'value':0,'data':'0x'+a['evm']['bytecode']['object']+encode(['address[10]'],[[w['address'] for w in self.wallets.public()]]).hex(),'expected_gain':0}
        if kind in ('buy_pons','sell_pons','approve_pons'):
            if type(amount) is not int or amount<=0:raise ValueError('Invalid trade amount')
            if kind=='approve_pons':
                return {'to':TOKEN,'value':0,'data':data('approve(address,uint256)',['address','uint256'],[ROUTER,amount]),'expected_gain':0}
            if kind=='buy_pons':
                q=inspect_market(self.rpc,amount); minimum=int(q['bought_units'])*(10000-self.cfg['max_slippage_bps'])//10000
                args=(WETH,TOKEN,10000,address,amount,minimum,0)
                calls=[bytes.fromhex(data(SWAP,[PARAM],[args])[2:])]
                gain=sell_quote(minimum,self.rpc)
            else:
                quoted=sell_quote(amount,self.rpc);minimum=quoted*(10000-self.cfg['max_slippage_bps'])//10000
                args=(TOKEN,WETH,10000,ROUTER,amount,minimum,0)
                calls=[bytes.fromhex(data(SWAP,[PARAM],[args])[2:]),bytes.fromhex(data('unwrapWETH9(uint256,address)',['uint256','address'],[minimum,address])[2:])]
                gain=minimum
            if minimum<=0:raise ValueError('Zero minimum output')
            return {'to':ROUTER,'value':amount if kind=='buy_pons' else 0,
                    'data':data('multicall(uint256,bytes[])',['uint256','bytes[]'],[deadline,calls]),'expected_gain':gain,'deadline':deadline}
        contract=self.settlement()
        if not contract:raise ValueError('Settlement is not deployed')
        if kind in ('produce','harvest'):
            return {'to':contract,'value':0,'data':data(kind+'()'),'expected_gain':0}
        if kind=='buy_resource':
            if type(seller) is not int or not 0<=seller<10 or seller%2==fly%2:raise ValueError('Invalid seller')
            target=self.wallets.public()[seller]['address']
            price=self.rpc.view(contract,'ask(address)',['uint256'],['address'],[target])[0]
            if not 0<price<=5*10**13:raise ValueError('Resource price rejected')
            return {'to':contract,'value':price,'data':data('buy(address,uint256)',['address','uint256'],[target,price]),'expected_gain':0}
        raise ValueError('Operation not allowed')

    def submit(self,fly,kind,intent_id,amount=0,seller=None):
        if type(fly) is not int or not 0<=fly<10 or not intent_id or len(intent_id)>128:raise ValueError('Invalid operation')
        self.gate();self.reconcile()
        existing=self.db.execute('SELECT status,hash FROM transactions WHERE id=?',(intent_id,)).fetchone()
        if existing:return dict(existing)
        if self.open_tx(fly):raise RuntimeError('Previous transaction is unresolved')
        if self.db.execute("SELECT 1 FROM transactions WHERE kind='deploy' AND status='reverted'").fetchone():raise RuntimeError('Deployment reverted; operator investigation required')
        balances=self.balances();row=balances[fly];address=row['address'];cash=row['eth_wei'];units=row['pons_units']
        value=sell_quote(units,self.rpc) if units else 0
        initial=self.meta('initial_funding')['amounts'];baseline=initial[fly]
        if fly==0:baseline-=self.meta('setup_cost_wei') or 0
        total=sum(w['eth_wei']+(sell_quote(w['pons_units'],self.rpc) if w['pons_units'] else 0) for w in balances)
        stopped=(cash+value)*10000<baseline*(10000-self.cfg['max_drawdown_bps']) or total*10000<sum(initial)*(10000-self.cfg['max_drawdown_bps'])
        if stopped and kind not in ('sell_pons','approve_pons'):raise PermissionError('Drawdown stop reached')
        if kind in ('sell_pons','approve_pons') and not 0<amount<=units:raise ValueError('Cannot sell or approve more than holdings')
        if kind=='buy_pons' and (amount>int(self.cfg['max_trade_wei']) or (value+amount)*2>cash+value):raise ValueError('50% exposure limit')
        plan=self.construct(fly,kind,amount,seller)
        tx={'from':address,'value':hex(plan['value']),'data':plan['data']}
        if plan['to']:tx['to']=to_checksum_address(plan['to'])
        # All estimates and simulations happen before signing; deadline checked again below.
        self.rpc.call('eth_call',[tx,'latest'])
        gas=int(self.rpc.call('eth_estimateGas',[tx]),16)*12//10+1000
        price=int(self.rpc.call('eth_gasPrice'),16)*2;fee=gas*price
        max_fee=6*10**14 if kind=='deploy' else 2*10**13
        if fee>max_fee or cash-plan['value']-fee<int(self.cfg['gas_reserve_wei']):raise ValueError('Gas reserve or maximum fee rejected')
        if kind=='buy_pons':
            if value+plan['expected_gain']>cash-amount-fee:raise ValueError('Post-trade exposure would exceed 50%')
        if kind not in ('deploy','sell_pons','approve_pons') and (cash+value-plan['value']-fee+plan['expected_gain'])*10000<baseline*(10000-self.cfg['max_drawdown_bps']):
            raise ValueError('Operation crosses loss limit')
        if kind in ('produce','harvest','buy_resource') and value>cash-plan['value']-fee:raise ValueError('Resource spending would breach token cap')
        if kind=='buy_resource':
            ask=self.rpc.view(plan['to'],'ask(address)',['uint256'],['address'],[address])[0]
            if ask*2-plan['value']<=fee+80000*price:raise ValueError('Expected resource margin does not cover acquisition and production gas')
        if kind=='approve_pons':
            # Only exact-amount allowances are ever granted.
            if amount!=units:raise ValueError('Approval must match current exit amount')
        if plan.get('deadline',time.time()+10)<=time.time()+3:raise ValueError('Quote expired before signing')
        nonce=int(self.rpc.call('eth_getTransactionCount',[address,'pending']),16)
        count=self.db.execute('SELECT COUNT(*) FROM transactions WHERE fly=?',(fly,)).fetchone()[0]
        if nonce!=count:raise ValueError('Wallet nonce differs from execution journal')
        signed_tx={'chainId':4663,'nonce':nonce,'value':plan['value'],'data':plan['data'],'gas':gas,'gasPrice':price}
        if plan['to']:signed_tx['to']=to_checksum_address(plan['to'])
        record=self.wallets.records()[fly];key=protect(base64.b64decode(record['sealed']),True)
        signer=Account.from_key(key)
        if signer.address.lower()!=address.lower():raise ValueError('Signer mismatch')
        signed=signer.sign_transaction(signed_tx);txhash='0x'+keccak(signed.raw_transaction).hex()
        sealed=base64.b64encode(protect(signed.raw_transaction)).decode()
        with self.db:self.db.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)',
            (intent_id,fly,kind,json.dumps(plan),nonce,txhash,sealed,'signed',None,time.time()))
        return self._send(self.db.execute('SELECT * FROM transactions WHERE id=?',(intent_id,)).fetchone())

    def events(self):
        return [{'id':r['id'],'fly':r['fly'],'kind':r['kind'],'hash':r['hash'],'status':r['status'],
                 'created':r['created'],'receipt':json.loads(r['receipt']) if r['receipt'] else None}
                for r in self.db.execute('SELECT * FROM transactions ORDER BY created DESC LIMIT 50')]
