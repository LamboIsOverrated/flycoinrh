"""Interactive portable keystore backup. Enter passwords only in the local terminal."""
import base64
from getpass import getpass
import json
import hashlib
from pathlib import Path
import time
from eth_account import Account
from pilot_wallets import Wallets,protect

def create_backup(password):
    if len(password)<16:raise ValueError('Use at least 16 characters')
    records=[]
    for row in Wallets().records():
        key=protect(base64.b64decode(row['sealed']),True)
        encrypted=Account.encrypt(key,password,kdf='scrypt')
        if Account.from_key(Account.decrypt(encrypted,password)).address!=row['address']:
            raise RuntimeError('Backup verification failed')
        records.append({'id':row['id'],'name':row['name'],'address':row['address'],'keystore':encrypted})
    directory=Path(__file__).parent/'.garden'/'backups';directory.mkdir(parents=True,exist_ok=True)
    target=directory/f'fly-garden-{int(time.time())}.json'
    with target.open('x',encoding='utf-8') as out:json.dump({'version':1,'wallets':records},out,indent=2)
    proof={'filename':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'addresses':[r['address'] for r in records],'verified_at':time.time()}
    (directory.parent/'backup-proof.json').write_text(json.dumps(proof,indent=2))
    print(f'Encrypted backup verified: {target}')
    print('Keep a copy somewhere separate from this computer and retain its password.')

def main():
    import sys
    if '--stdin-password' in sys.argv:
        password=sys.stdin.readline().rstrip('\r\n')
    else:
        password=getpass('Choose a backup password (at least 16 characters): ')
        if password!=getpass('Repeat the backup password: '):raise ValueError('Passwords must match')
    create_backup(password)

if __name__=='__main__':main()
