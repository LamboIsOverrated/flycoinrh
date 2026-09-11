"""Transfer DPAPI ownership without writing plaintext private keys.

prepare/finish run as the destination Windows user; seal runs as the old user.
RSA-OAEP transports keys, and its private key is itself destination-DPAPI sealed.
"""
import argparse,base64,json,os
from pathlib import Path
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from eth_account import Account
from pilot_wallets import Wallets,protect,VAULT
ROOT=Path(__file__).parent/'.garden'

def run(phase):
    if phase=='prepare':
        if (ROOT/'owner-transfer-public.pem').exists():raise ValueError('Transfer already prepared')
        key=RSA.generate(3072)
        (ROOT/'owner-transfer-private.dpapi').write_bytes(protect(key.export_key(format='DER')))
        (ROOT/'owner-transfer-public.pem').write_bytes(key.public_key().export_key())
        print('Destination account prepared an encrypted key transfer.')
    elif phase=='seal':
        key=RSA.import_key((ROOT/'owner-transfer-public.pem').read_bytes())
        cipher=PKCS1_OAEP.new(key,hashAlgo=SHA256);rows=[]
        for row in Wallets().records():
            plain=protect(base64.b64decode(row['sealed']),True)
            if Account.from_key(plain).address!=row['address']:raise ValueError('Signer mismatch')
            rows.append({**{k:row[k] for k in ['id','name','address']},'transport':base64.b64encode(cipher.encrypt(plain)).decode()})
        (ROOT/'owner-transfer.json').write_text(json.dumps(rows))
        print('Ten keys sealed for the destination account; addresses preserved.')
    elif phase=='finish':
        key=RSA.import_key(protect((ROOT/'owner-transfer-private.dpapi').read_bytes(),True))
        cipher=PKCS1_OAEP.new(key,hashAlgo=SHA256);rows=[]
        incoming=json.loads((ROOT/'owner-transfer.json').read_text())
        expected=Wallets().public()
        if [r['address'] for r in incoming]!=[r['address'] for r in expected]:raise ValueError('Wallet set changed')
        for row in incoming:
            plain=cipher.decrypt(base64.b64decode(row['transport']))
            if Account.from_key(plain).address!=row['address']:raise ValueError('Transfer mismatch')
            sealed=protect(plain)
            if protect(sealed,True)!=plain:raise ValueError('Destination encryption failed')
            rows.append({**{k:row[k] for k in ['id','name','address']},'sealed':base64.b64encode(sealed).decode()})
        archive=ROOT/'wallets.previous-account.dpapi.json'
        if archive.exists():raise ValueError('Previous account archive already exists')
        archive.write_bytes(VAULT.read_bytes())
        temporary=ROOT/'wallets.migrating.json'
        temporary.write_text(json.dumps({'version':1,'encryption':'Windows DPAPI CurrentUser','wallets':rows},indent=2))
        Wallets(temporary).verify_signers();os.replace(temporary,VAULT)
        print('Ten wallets verified under the destination Windows account.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','seal','finish']);run(p.parse_args().phase)
