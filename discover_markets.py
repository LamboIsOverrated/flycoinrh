"""Read-only discovery, independently verified source/code pinning, and quotes.

Only records native-ETH curves matching the factory's verified compiled source.
This does not authorize live execution or assess whether a token is a good buy.
"""
import hashlib
import concurrent.futures
import json
from pathlib import Path
import time
import urllib.request
from eth_utils import keccak,to_checksum_address
from pilot_chain import Rpc,Pons,ZERO,load_config

ROOT=Path(__file__).parent

def verify(address,rpc,source_suffix=None,expected_source=None):
    url=f'https://sourcify.dev/server/v2/contract/4663/{address}?fields=all'
    with urllib.request.urlopen(url,timeout=30) as response:record=json.load(response)
    if record.get('runtimeMatch')!='exact_match' or record.get('proxyResolution',{}).get('isProxy'):
        raise ValueError('Exact, non-proxy verification required')
    chain_code=rpc.call('eth_getCode',[address,'latest'])
    if chain_code.lower()!=record['runtimeBytecode']['onchainBytecode'].lower():
        raise ValueError('Current bytecode differs from the verified deployment')
    if expected_source is not None:
        source=next(v['content'] for k,v in record['stdJsonInput']['sources'].items() if k.endswith(source_suffix))
        if source!=expected_source:raise ValueError('Curve source differs from the pinned factory build')
    return record,'0x'+keccak(bytes.fromhex(chain_code[2:])).hex()

def main():
    cfg=load_config();rpc=Rpc();rpc.validate_chain()
    record,codehash=verify(cfg['factory'],rpc)
    cfg['verified_factory_codehash']=codehash
    (ROOT/'pilot_config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    source=next(v['content'] for k,v in record['stdJsonInput']['sources'].items() if k.endswith('/PonsV2BondingCurve.sol'))
    latest=int(rpc.call('eth_blockNumber'),16)
    topic='0x'+keccak(text='TokenLaunched(address,address,address,address,uint256,uint256)').hex()
    found=[];errors=[]
    # Bounded scan; does not crawl all historical launches or send transactions.
    def scan(high):
        return Rpc().call('eth_getLogs',[{'address':cfg['factory'],'fromBlock':hex(max(0,high-9)),
                                         'toBlock':hex(high),'topics':[topic]}])
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        batches=list(pool.map(scan,range(latest,latest-1000,-10)))
    for logs in batches:
        for event in reversed(logs):
            if len(event['topics'])!=4 or '0x'+event['data'][26:66]!=ZERO:continue
            token=to_checksum_address('0x'+event['topics'][1][-40:]);curve=to_checksum_address('0x'+event['topics'][2][-40:])
            try:
                verified,curvehash=verify(curve,rpc,'/PonsV2BondingCurve.sol',source)
                candidate={'token':token,'curve_codehash':curvehash,'verified_at':time.time(),
                           'verification_url':f'https://sourcify.dev/server/v2/contract/4663/{curve}',
                           'source_sha256':hashlib.sha256(source.encode()).hexdigest()}
                check={**cfg,'approved_tokens':[candidate]}
                market=Pons(rpc,check).read_curve(token)
                if market.real_quote<10**17:raise ValueError('Less than 0.1 ETH real liquidity')
                candidate['curve']=curve
                found.append(candidate)
                print(json.dumps({'token':token,'curve':curve,'real_liquidity_wei':str(market.real_quote),'verified':True}),flush=True)
            except Exception as error:
                errors.append({'token':token,'reason':str(error).split('?')[0][:180]})
            if len(found)>=3:break
        if len(found)>=3:break
    cfg['approved_tokens']=found
    (ROOT/'pilot_config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    (ROOT/'.garden'/'market-discovery.json').write_text(json.dumps({'block':latest,'verified_candidates':found,'rejected':errors},indent=2))
    print(json.dumps({'verified_candidates':len(found),'rejected':len(errors),'factory_verified':True}),flush=True)

if __name__=='__main__':main()
