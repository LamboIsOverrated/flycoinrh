"""Compare the full router runtime with Uniswap's published 1.3.1 artifact.

Only complete zero-valued PUSH32 address placeholders may differ. Metadata and
every opcode must match. This is artifact matching, not an independent audit.
"""
import json
import requests
from eth_utils import keccak
from pilot_chain import Rpc
from pilot_v3 import ROOT, ROUTER, FACTORY, WETH

URL='https://unpkg.com/@uniswap/swap-router-contracts@1.3.1/artifacts/contracts/SwapRouter02.sol/SwapRouter02.json'

def compare(template, actual, addresses):
    if len(template)!=len(actual):raise ValueError('Router runtime length differs')
    allowed={bytes.fromhex(a[2:]).rjust(32,b'\0') for a in addresses}
    i=0; substitutions=0
    while i<len(template):
        op=template[i]
        if actual[i]!=op:raise ValueError('Router opcode differs')
        n=op-0x5f if 0x60<=op<=0x7f else 0
        if n:
            x=template[i+1:i+1+n];y=actual[i+1:i+1+n]
            if x!=y:
                if n!=32 or x!=bytes(32) or y not in allowed:
                    raise ValueError('Router operand differs outside an address placeholder')
                substitutions+=1
        i+=n+1
    return substitutions

def verify():
    r=Rpc();r.validate_chain();block=r.call('eth_blockNumber')
    response=requests.get(URL,timeout=30);response.raise_for_status();artifact=response.json()
    code=bytes.fromhex(r.call('eth_getCode',[ROUTER,block])[2:])
    addresses=[r.view(ROUTER,s,['address'],block=block)[0] for s in ['factory()','WETH9()','factoryV2()','positionManager()']]
    if addresses[:2]!=[FACTORY.lower(),WETH.lower()]:raise ValueError('Router immutable identity mismatch')
    substitutions=compare(bytes.fromhex(artifact['deployedBytecode'][2:]),code,addresses)
    report={'router':ROUTER,'block':int(block,16),'source':URL,'runtime_code_hash':'0x'+keccak(code).hex(),
            'artifact_match':True,'address_substitutions':substitutions,
            'limitations':'Published artifact match with constructor addresses; not an independent security audit'}
    (ROOT/'.garden/router-verification.json').write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':print(json.dumps(verify(),indent=2))
