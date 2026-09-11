"""Public, read-only chain observations for the Railway spectator website."""
import json
import re
import threading
import time
from pathlib import Path
from pilot_chain import Rpc

ROOT = Path(__file__).parent
TOKEN = '0x39dBED3a2bd333467115dE45665cC57F813C4571'
POOL = '0x10cc6bd38112cac182db90b6a71d8bb5939526ba'

class Observatory:
    def __init__(self, root=ROOT, rpc_factory=Rpc):
        self.root, self.rpc_factory = root, rpc_factory
        self.lock = threading.Lock()
        self.cached, self.cache_at = None, 0

    def status(self):
        with self.lock:
            if self.cached is not None and time.monotonic() - self.cache_at < 15:
                return {**self.cached, 'heartbeat': self.heartbeat()}
            rpc = self.rpc_factory()
            try:
                result = self.read(rpc)
            finally:
                rpc.session.close()
            self.cached, self.cache_at = result, time.monotonic()
            return result

    def heartbeat(self):
        path = self.root / '.garden/live-status.json'
        if not path.exists():
            return None
        stored = json.loads(path.read_text(encoding='utf-8'))
        result = {k: stored.get(k) for k in ('observed_at', 'status', 'round')}
        result.update(backup_ready=stored.get('backup_ready') is True, enabled=stored.get('enabled') is True,
                      error='Runner paused after a safety or connection check' if stored.get('error') else None,
                      telemetry=[{k: t.get(k) for k in ('id', 'measured_at', 'firing', 'neurons', 'action', 'observation_block')}
                                 for t in stored.get('telemetry', [])[:10]])
        return result

    def read(self, rpc):
        rpc.validate_chain()
        block = rpc.call('eth_blockNumber')
        head = int(block, 16)
        slot = rpc.call('eth_call', [{'to': POOL, 'data': '0x3850c7bd'}, block])
        sqrt = int(slot[2:66], 16)
        if sqrt <= 0:
            raise ValueError('Market unavailable')
        wallets = []
        for w in json.loads((self.root / 'web/wallets.json').read_text(encoding='utf-8')):
            address = w['address']
            eth = int(rpc.call('eth_getBalance', [address, block]), 16)
            token = int(rpc.call('eth_call', [{'to': TOKEN, 'data': '0x70a08231' + address[2:].lower().zfill(64)}, block]), 16)
            wallets.append(dict(id=w['id'], name=w['name'], address=address, eth_wei=str(eth),
                                pons_units=str(token), token_mark_wei=str(token * 2**192 // sqrt**2)))
        path = self.root / '.garden/live-status.json'
        stored = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        heartbeat, transactions = None, []
        if stored:
            heartbeat = {k: stored.get(k) for k in ('observed_at', 'status', 'round')}
            heartbeat.update(backup_ready=stored.get('backup_ready') is True,
                             enabled=stored.get('enabled') is True,
                             error='Runner paused after a safety or connection check' if stored.get('error') else None,
                             telemetry=[{k: t.get(k) for k in ('id', 'measured_at', 'firing', 'neurons', 'action', 'observation_block')}
                                        for t in stored.get('telemetry', [])[:10]])
            for t in stored.get('transactions', [])[:20]:
                if not re.fullmatch(r'0x[0-9a-fA-F]{64}', t.get('hash', '')) or type(t.get('fly')) is not int or not 0 <= t['fly'] < 10:
                    continue
                receipt = rpc.call('eth_getTransactionReceipt', [t['hash']])
                if receipt and receipt.get('from', '').lower() != wallets[t['fly']]['address'].lower():
                    continue
                height = int(receipt['blockNumber'], 16) if receipt else None
                confirmations = max(0, head - height + 1) if receipt else 0
                status = ('reverted' if int(receipt['status'], 16) == 0 else
                          'confirmed' if confirmations >= 12 else 'confirming') if receipt else 'pending'
                transactions.append(dict(hash=t['hash'], fly=t['fly'], kind=t['kind'], created=t['created'],
                                         status=status, confirmations=confirmations, block=height))
        return dict(observed_at=time.time(), block=head, chain_id=4663, wallets=wallets,
                    market=dict(token=TOKEN, pool=POOL, price_wei=str(10**18 * 2**192 // sqrt**2), fee_bps=100),
                    heartbeat=heartbeat, transactions=transactions, source='Robinhood Chain RPC')
