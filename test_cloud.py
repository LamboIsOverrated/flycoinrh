import base64,json,os,unittest
from unittest.mock import patch
from eth_account import Account
from cloud_wallets import CloudWallets,protect_state
from live_execution import backup_ready

class CloudTests(unittest.TestCase):
    def test_encrypted_transaction_state_roundtrip_and_tamper(self):
        with patch.dict(os.environ,{'GARDEN_STATE_KEY':base64.b64encode(b'a'*32).decode()}):
            sealed=protect_state(b'private-test-transaction')
            self.assertNotIn(b'private-test-transaction',sealed)
            self.assertEqual(protect_state(sealed,True),b'private-test-transaction')
            with self.assertRaises(ValueError):protect_state(sealed[:-1]+bytes([sealed[-1]^1]),True)
        with patch.dict(os.environ,{'GARDEN_STATE_KEY':base64.b64encode(b'b'*32).decode()}):
            with self.assertRaises(ValueError):protect_state(sealed,True)

    def test_missing_cloud_keys_cannot_pass_backup_gate(self):
        with patch.dict(os.environ,{},clear=True):
            wallets=CloudWallets();self.assertEqual(len(wallets.public()),10)
            self.assertFalse(backup_ready(wallets))
            with self.assertRaises(RuntimeError):protect_state(b'test')

    def test_encrypted_backup_preserves_existing_addresses(self):
        accounts=[Account.create() for _ in range(10)]
        public=[{'id':i,'name':str(i),'address':a.address} for i,a in enumerate(accounts)]
        password='test-only portable password'
        # Reduced work factor only for test-generated keys; production backup uses library defaults.
        rows=[{**w,'keystore':Account.encrypt(a.key,password,kdf='scrypt',iterations=1024)} for w,a in zip(public,accounts)]
        config={'GARDEN_STATE_KEY':base64.b64encode(b'c'*32).decode(),'GARDEN_WALLET_PASSWORD':password,'GARDEN_WALLET_BACKUP_JSON':json.dumps({'version':1,'wallets':rows})}
        with patch.dict(os.environ,config,clear=True):
            wallets=CloudWallets();wallets._public=public
            self.assertTrue(backup_ready(wallets))
            for row in wallets.records():
                key=protect_state(base64.b64decode(row['sealed']),True)
                self.assertEqual(Account.from_key(key).address,row['address'])
            wrong=CloudWallets()
            with self.assertRaises(ValueError):wrong.records()
        with patch.dict(os.environ,{**config,'GARDEN_WALLET_PASSWORD':'wrong'},clear=True):
            wrong=CloudWallets();wrong._public=public
            with self.assertRaises(ValueError):wrong.records()

if __name__=='__main__':unittest.main()
