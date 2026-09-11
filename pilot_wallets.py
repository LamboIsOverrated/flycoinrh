"""Ten Windows-user-bound encrypted wallets. Never print or persist plaintext keys.

The vault requires this Windows user profile to decrypt. It is not a portable
backup. Only public addresses may enter the UI. No broadcast function exists.
"""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from eth_account import Account

ROOT = Path(__file__).parent
VAULT = ROOT / '.garden' / 'wallets.dpapi.json'
NAMES = ['Clover', 'Fig', 'Juniper', 'Miso', 'Olive', 'Pip', 'Sage', 'Taro', 'Willow', 'Zest']

class Blob(ctypes.Structure):
    _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def protect(value, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('This vault requires Windows DPAPI; no plaintext fallback')
    buf = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source, target = Blob(len(value), buf), Blob()
    crypto = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    fn.restype = wintypes.BOOL
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.length)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))

class Wallets:
    def __init__(self, path=VAULT):
        self.path = Path(path)

    def create(self):
        if self.path.exists():
            return self.public()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for i, name in enumerate(NAMES):
            account = Account.create()
            sealed = protect(bytes(account.key))
            # Round trip proves the key can be recovered before it is saved.
            if Account.from_key(protect(sealed, True)).address != account.address:
                raise RuntimeError('Vault round-trip failed')
            records.append({'id': i, 'name': name, 'address': account.address,
                            'sealed': base64.b64encode(sealed).decode()})
        # Exclusive creation prevents overwriting an existing wallet set.
        with self.path.open('x', encoding='utf-8') as out:
            json.dump({'version': 1, 'encryption': 'Windows DPAPI CurrentUser', 'wallets': records}, out, indent=2)
        return self.public()

    def records(self):
        data = json.loads(self.path.read_text(encoding='utf-8'))
        rows = data['wallets']
        if data.get('version') != 1 or len(rows) != 10 or [r['id'] for r in rows] != list(range(10)):
            raise ValueError('Invalid vault structure')
        if len({r['address'].lower() for r in rows}) != 10:
            raise ValueError('Duplicate wallet address')
        return rows

    def public(self):
        return [{k: r[k] for k in ('id', 'name', 'address')} for r in self.records()]

    def verify_signers(self):
        """Sign only a zero-value self transaction, locally; never expose raw bytes."""
        results = []
        for row in self.records():
            key = protect(base64.b64decode(row['sealed'], validate=True), True)
            account = Account.from_key(key)
            if account.address != row['address']:
                raise ValueError('Vault address does not match its encrypted key')
            tx = {'chainId': 4663, 'nonce': 0, 'to': account.address, 'value': 0,
                  'gas': 21000, 'gasPrice': 1, 'data': '0x'}
            signed = account.sign_transaction(tx)
            recovered = Account.recover_transaction(signed.raw_transaction)
            if recovered != account.address:
                raise RuntimeError('Signing verification failed')
            results.append({'id': row['id'], 'address': row['address'], 'signature_verified': True})
        return results

if __name__ == '__main__':
    wallets = Wallets()
    wallets.create()
    print(json.dumps(wallets.verify_signers(), indent=2))
