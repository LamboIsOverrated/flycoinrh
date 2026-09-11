"""Portable Linux recovery from the user's encrypted backup; no new wallets."""
import base64
import json
import os
from pathlib import Path
from Crypto.Cipher import AES
from eth_account import Account

ROOT=Path(__file__).parent

def protect_state(value,decrypt=False):
    try:key=base64.b64decode(os.environ['GARDEN_STATE_KEY'],validate=True)
    except (KeyError,ValueError):raise RuntimeError('GARDEN_STATE_KEY must be a persistent base64-encoded 32-byte secret') from None
    if len(key)!=32:raise ValueError('GARDEN_STATE_KEY must decode to 32 bytes')
    if decrypt:
        if len(value)<36 or value[:4]!=b'GOF1':raise ValueError('Invalid encrypted state')
        cipher=AES.new(key,AES.MODE_GCM,nonce=value[4:20]);cipher.update(b'Garden of Flies transaction state v1')
        return cipher.decrypt_and_verify(value[36:],value[20:36])
    cipher=AES.new(key,AES.MODE_GCM);cipher.update(b'Garden of Flies transaction state v1')
    encrypted,tag=cipher.encrypt_and_digest(value)
    return b'GOF1'+cipher.nonce+tag+encrypted

class CloudWallets:
    def __init__(self):
        self._public=json.loads((ROOT/'web/wallets.json').read_text())
        self._records=None

    def public(self):return [dict(w) for w in self._public]

    def backup_verified(self):
        configured=os.getenv('GARDEN_WALLET_BACKUP_FILE') or os.getenv('GARDEN_WALLET_BACKUP_JSON')
        if not configured or not os.getenv('GARDEN_WALLET_PASSWORD') or not os.getenv('GARDEN_STATE_KEY'):return False
        self.records();return True

    def records(self):
        if self._records is not None:return self._records
        filename=os.getenv('GARDEN_WALLET_BACKUP_FILE')
        content=Path(filename).read_text() if filename else os.environ.get('GARDEN_WALLET_BACKUP_JSON','')
        try:backup=json.loads(content);password=os.environ['GARDEN_WALLET_PASSWORD']
        except (ValueError,KeyError):raise RuntimeError('Configure the encrypted wallet backup and its password as runtime secrets') from None
        records=backup.get('wallets',[])
        if backup.get('version')!=1 or [r.get('address') for r in records]!=[r['address'] for r in self._public]:
            raise ValueError('Cloud backup must contain the existing ten garden wallets in order')
        result=[]
        for public,record in zip(self._public,records):
            try:key=Account.decrypt(record['keystore'],password)
            except Exception:raise ValueError('Encrypted backup could not be recovered') from None
            if Account.from_key(key).address.lower()!=public['address'].lower():raise ValueError('Backup signer differs from the garden wallet')
            result.append({**public,'sealed':base64.b64encode(protect_state(key)).decode()})
        self._records=result
        return result
