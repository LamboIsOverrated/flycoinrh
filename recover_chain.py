"""One-time recovery of the two independently located, confirmed pilot transactions.
No keys, signatures or broadcasting. Unknown history fails closed.
"""
import json
import time
from eth_abi import encode
from live_execution import data, TOKEN

CONTRACT='0xa644be37a9484b27ab52120ff3c58cba907d1e97'
RECORDS=[(0,60418342,'0x9b6ffe856a31ca77f430a7cb2c834d40db14902f86b3e6c648f3c4530bbb7e3f','deploy'),
         (1,60419598,'0xfbcdd563b31f38cbc8af2c142170dc7da04b74656040a8adb3472e4aa3084019','produce')]

def recover(execution):
    e=execution
    if e.meta('initial_funding'):
        return False
    if e.db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]:
        raise ValueError('Recovery requires an empty journal; existing records need reconciliation')
    e.verify_code()
    rpc=e.rpc;wallets=e.wallets.public();head=int(rpc.call('eth_blockNumber'),16)
    artifact=e.artifact()
    runtime='0x'+artifact['evm']['deployedBytecode']['object']
    if rpc.call('eth_getCode',[CONTRACT,hex(head)]).lower()!=runtime.lower():
        raise ValueError('Recovery contract runtime mismatch')
    for w in wallets:
        actual=rpc.view(CONTRACT,'flies(uint256)',['address'],['uint256'],[w['id']],hex(head))[0]
        if actual.lower()!=w['address'].lower():raise ValueError('Recovery membership mismatch')
    fees=[0]*10;verified=[]
    for fly,height,txhash,kind in RECORDS:
        block=rpc.call('eth_getBlockByNumber',[hex(height),True])
        tx=next((t for t in block['transactions'] if t['hash'].lower()==txhash),None)
        receipt=rpc.call('eth_getTransactionReceipt',[txhash])
        if (not tx or not receipt or head-height+1<12 or receipt['blockHash'].lower()!=block['hash'].lower()
            or int(receipt['blockNumber'],16)!=height or receipt['transactionHash'].lower()!=txhash
            or int(receipt['status'],16)!=1 or tx['from'].lower()!=wallets[fly]['address'].lower()
            or receipt['from'].lower()!=wallets[fly]['address'].lower() or int(tx['nonce'],16)!=0
            or int(tx['value'],16)!=0):
            raise ValueError('Recovery transaction or receipt mismatch')
        expected=('0x'+artifact['evm']['bytecode']['object']+encode(['address[10]'],[[w['address'] for w in wallets]]).hex()) if kind=='deploy' else data('produce()')
        if tx['input'].lower()!=expected.lower():raise ValueError('Recovery calldata mismatch')
        if kind=='deploy':
            if tx.get('to') is not None or receipt.get('contractAddress','').lower()!=CONTRACT:raise ValueError('Recovery deployment mismatch')
        elif tx.get('to','').lower()!=CONTRACT:raise ValueError('Recovery target mismatch')
        fees[fly]=int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16)
        verified.append((fly,kind,txhash,receipt,int(block['timestamp'],16)))
    for w in wallets:
        i=w['id'];expected_nonce=1 if i<2 else 0
        if any(int(rpc.call('eth_getTransactionCount',[w['address'],tag]),16)!=expected_nonce for tag in (hex(head),'latest','pending')):
            raise ValueError('Additional or pending wallet history; recovery stopped')
        budget,reserve=e.allocation(i)
        balance=int(rpc.call('eth_getBalance',[w['address'],hex(head)]),16)
        if balance!=budget+reserve-fees[i]:raise ValueError('Recovery balance does not reconcile')
        if rpc.view(TOKEN,'balanceOf(address)',['uint256'],['address'],[w['address']],hex(head))[0]!=0:
            raise ValueError('Unexpected token holdings during recovery')
    # Write all receipts, nonce reservations and baseline together or not at all.
    with e.db:
        for fly,kind,txhash,receipt,created in verified:
            e.db.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)',
                         ('recovered-'+txhash,fly,kind,json.dumps({'recovered':True}),0,txhash,'','confirmed',json.dumps(receipt),created))
        for key,value in {'initial_funding':{'amounts':[e.allocation(i)[0] for i in range(10)],'time':verified[0][4],'recovered':True},
                          'settlement':CONTRACT,'setup_cost_wei':fees[0],
                          'recovery':{'completed_at':time.time(),'hashes':[r[2] for r in verified],'block':head}}.items():
            e.db.execute('INSERT INTO metadata VALUES (?,?)',(key,json.dumps(value)))
    return True
