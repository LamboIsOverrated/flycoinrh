"""Guarded mainnet settlement, disabled by default. No web route exposes this.

Transactions are signed only after live activation, backup, cash, fee, contract,
nonce and loss checks. Signed bytes are encrypted before the network sees them.
An uncertain transaction blocks the wallet until its receipt is reconciled.
"""
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from eth_account import Account
from eth_abi import encode
from eth_utils import keccak,to_checksum_address
from pilot_chain import Rpc,Pons,buy_intent,load_config
from pilot_wallets import Wallets,protect

ROOT=Path(__file__).parent

def calldata(signature,types=(),values=()):
    return '0x'+(keccak(text=signature)[:4]+encode(list(types),list(values))).hex()

class Executor:
    def __init__(self):
        self.cfg=load_config();self.rpc=Rpc();self.wallets=Wallets()
        self.db=sqlite3.connect(ROOT/'.garden'/'execution.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, wallet INTEGER, nonce INTEGER, hash TEXT, sealed TEXT, status TEXT, receipt TEXT, UNIQUE(wallet,nonce))')
        self.db.execute('CREATE TABLE IF NOT EXISTS opening (wallet INTEGER PRIMARY KEY, balance TEXT NOT NULL)')
        self.db.execute('PRAGMA synchronous=FULL');self.db.commit()

    def gate(self):
        if self.cfg['broadcast_enabled'] is not True:raise PermissionError('Mainnet broadcasting is disabled')
        proof_path=ROOT/'.garden'/'backup-proof.json'
        if not proof_path.exists():raise PermissionError('Complete the local encrypted backup first')
        proof=json.loads(proof_path.read_text())
        backup=ROOT/'.garden'/'backups'/proof['filename']
        if backup.parent.resolve()!=(ROOT/'.garden'/'backups').resolve() or hashlib.sha256(backup.read_bytes()).hexdigest()!=proof['sha256']:
            raise ValueError('Encrypted backup proof is invalid')
        if proof['addresses']!=[w['address'] for w in self.wallets.public()]:raise ValueError('Backup does not cover this wallet set')
        self.rpc.validate_chain()

    def resource_contract(self):
        path=ROOT/'.garden'/'deployment.json'
        if not path.exists():raise ValueError('Garden settlement contract has not been deployed')
        record=json.loads(path.read_text());code=self.rpc.call('eth_getCode',[record['address'],'latest'])
        if '0x'+keccak(bytes.fromhex(code[2:])).hex()!=record['code_hash']:raise ValueError('Settlement code changed')
        for i,wallet in enumerate(self.wallets.public()):
            if self.rpc.view(record['address'],'flies(uint256)',['address'],['uint256'],[i])[0].lower()!=wallet['address'].lower():raise ValueError('Settlement participant mismatch')
        return record['address']

    def reconcile(self):
        for intent_id,txhash in self.db.execute("SELECT id,hash FROM transactions WHERE status='pending'").fetchall():
            receipt=self.rpc.call('eth_getTransactionReceipt',[txhash])
            if receipt:
                status='confirmed' if int(receipt['status'],16)==1 else 'reverted'
                with self.db:self.db.execute('UPDATE transactions SET status=?,receipt=? WHERE id=?',(status,json.dumps(receipt),intent_id))

    def submit(self,fly_id,target,value,data,intent_id,token_exposure=0):
        self.gate()
        if type(fly_id) is not int or not 0<=fly_id<10 or not intent_id or len(intent_id)>128:raise ValueError('Invalid fly or intent identifier')
        # Submission is private to internally constructed plans. Decode and whitelist
        # the complete payload again so this method cannot be an arbitrary signer.
        from eth_abi import decode
        allowed_tokens=self.cfg['approved_tokens']
        method=data[:10]
        settlement=ROOT/'.garden'/'deployment.json'
        resource=json.loads(settlement.read_text())['address'] if settlement.exists() else None
        if resource and target.lower()==resource.lower():
            allowed={calldata('produce()'),calldata('harvest()')}
            if data in allowed:
                if value!=0:raise ValueError('Unexpected ETH value')
            elif method==calldata('buy(address,uint256)')[:10]:
                seller,maximum=decode(['address','uint256'],bytes.fromhex(data[10:]))
                public=self.wallets.public()
                if seller.lower() not in [w['address'].lower() for w in public] or seller.lower()==public[fly_id]['address'].lower():raise ValueError('Seller outside this garden')
                if not 0<value<=maximum<=10**13:raise ValueError('Resource price exceeds contract policy')
            else:raise ValueError('Settlement method not allowed')
        else:
            raise ValueError('This executor currently permits only the verified garden settlement contract')
        self.resource_contract()
        existing=self.db.execute('SELECT status,hash FROM transactions WHERE id=?',(intent_id,)).fetchone()
        if existing:return {'status':existing[0],'hash':existing[1],'duplicate':True}
        self.reconcile()
        if self.db.execute("SELECT 1 FROM transactions WHERE wallet=? AND status='pending'",(fly_id,)).fetchone():raise RuntimeError('A previous transaction is unresolved; this wallet is paused')
        row=self.wallets.records()[fly_id];address=row['address']
        cash=int(self.rpc.call('eth_getBalance',[address,'latest']),16)
        opening=self.db.execute('SELECT balance FROM opening WHERE wallet=?',(fly_id,)).fetchone()
        if not opening:
            if cash<=0:raise ValueError('Wallet is not funded')
            if cash>int(self.cfg['per_fly_budget_wei']):raise ValueError('Funding exceeds the approved per-fly budget')
            with self.db:self.db.execute('INSERT INTO opening VALUES (?,?)',(fly_id,str(cash)))
            baseline=cash
        else:baseline=int(opening[0])
        if baseline<=0:raise ValueError('Wallet is not funded')
        tx={'from':address,'to':to_checksum_address(target),'value':hex(value),'data':data}
        self.rpc.call('eth_call',[tx,'latest'])
        gas=int(self.rpc.call('eth_estimateGas',[tx]),16)*12//10
        price=int(self.rpc.call('eth_gasPrice'),16)*2
        fee=gas*price
        if fee>2*10**13 or cash-value-fee<int(self.cfg['gas_reserve_wei']):raise ValueError('Fee or gas-reserve limit rejected the transaction')
        if (cash-value-fee+token_exposure)*10000<baseline*(10000-self.cfg['max_drawdown_bps']):raise ValueError('20% drawdown stop reached')
        nonce=int(self.rpc.call('eth_getTransactionCount',[address,'pending']),16)
        signed_tx={'chainId':4663,'nonce':nonce,'to':to_checksum_address(target),'value':value,'data':data,'gas':gas,'gasPrice':price}
        key=protect(base64.b64decode(row['sealed']),True);account=Account.from_key(key)
        if account.address!=address:raise ValueError('Signer/address mismatch')
        signed=account.sign_transaction(signed_tx);txhash='0x'+keccak(signed.raw_transaction).hex()
        encrypted=base64.b64encode(protect(signed.raw_transaction)).decode()
        with self.db:self.db.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?)',(intent_id,fly_id,nonce,txhash,encrypted,'pending',None))
        # The only real send in this project extension. It is never called by setup,
        # preflight, the neural paper runner, the web UI, or the automated tests.
        try:
            response=self.rpc.session.post(self.rpc.url,json={'jsonrpc':'2.0','id':1,'method':'eth_sendRawTransaction','params':['0x'+signed.raw_transaction.hex()]},timeout=20)
            result=response.json()
            if result.get('result','').lower()!=txhash.lower():raise RuntimeError('Broadcast not confirmed')
        except Exception:
            raise RuntimeError('Submission outcome uncertain; reconcile the saved hash before continuing') from None
        return {'status':'pending','hash':txhash}

    def resource_action(self,fly_id,action,intent_id,seller_id=None):
        self.gate();target=self.resource_contract()
        if action in ('produce','harvest'):return self.submit(fly_id,target,0,calldata(action+'()'),intent_id)
        if action=='buy_input' and type(seller_id) is int and 0<=seller_id<10:
            seller=self.wallets.public()[seller_id]['address']
            price=self.rpc.view(target,'ask(address)',['uint256'],['address'],[seller])[0]
            return self.submit(fly_id,target,price,calldata('buy(address,uint256)',['address','uint256'],[seller,price]),intent_id)
        raise ValueError('Unknown resource action')
