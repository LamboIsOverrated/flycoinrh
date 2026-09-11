"""Selected PONS market: read-only identity and atomic buy/sell simulation.

The state override lives inside eth_call only. No wallet is funded, no transaction
is signed, and no probe is deployed. Observed code hashes are NOT source audits.
"""
import json
import time
from pathlib import Path
from eth_abi import encode, decode
from eth_utils import keccak
from pilot_chain import Rpc, load_config

ROOT=Path(__file__).parent
TOKEN='0x39dBED3a2bd333467115dE45665cC57F813C4571'
POOL='0x10cc6bd38112cac182db90b6a71d8bb5939526ba'
FACTORY='0x1f7d7550b1b028f7571e69a784071f0205fd2efa'
ROUTER='0xcaf681a66d020601342297493863e78c959e5cb2'
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
LAUNCHER='0x0c37a24f5d23a486fa692d1500881d698b1f77a4'
PROBE='0x00000000000000000000000000000000000F17aA'

def inspect_market(rpc=None,amount=10**14):
    cfg=load_config()
    if type(amount) is not int or not 0<amount<=int(cfg['max_trade_wei']):
        raise ValueError('Quote amount exceeds pilot limit')
    r=rpc or Rpc(); r.validate_chain()
    block=r.call('eth_blockNumber'); b=int(block,16)
    def view(a,s,o,t=(),v=()):return r.view(a,s,o,t,v,block)
    expected=[(POOL,'factory()',FACTORY),(POOL,'token0()',WETH),(POOL,'token1()',TOKEN),
              (ROUTER,'factory()',FACTORY),(ROUTER,'WETH9()',WETH),
              (TOKEN,'liquidityPool()',POOL),(TOKEN,'launchFactory()',LAUNCHER)]
    for a,s,value in expected:
        if view(a,s,['address'])[0].lower()!=value.lower():raise ValueError('Market relationship changed: '+s)
    if view(FACTORY,'getPool(address,address,uint24)',['address'],['address','address','uint24'],[WETH,TOKEN,10000])[0].lower()!=POOL.lower():
        raise ValueError('Factory pool mismatch')
    dex=view(LAUNCHER,'getDexConfig(uint256)',['(string,address,address,address,uint24,int24,bool)'],['uint256'],[0])[0]
    if dex[1].lower()!=FACTORY.lower() or dex[3].lower()!=ROUTER.lower() or not dex[6]:raise ValueError('Launcher route changed')
    if view(POOL,'fee()',['uint24'])[0]!=10000:raise ValueError('Unexpected pool fee')
    if b<=view(TOKEN,'restrictionEndBlock()',['uint256'])[0]:raise ValueError('Launch restrictions remain active')
    liquidity=view(POOL,'liquidity()',['uint128'])[0]
    weth_balance=view(WETH,'balanceOf(address)',['uint256'],['address'],[POOL])[0]
    if liquidity<=0 or weth_balance<10**17:raise ValueError('Insufficient liquidity')
    if r.call('eth_getCode',[PROBE,block])!='0x':raise ValueError('Probe address is occupied')
    artifact=json.loads((ROOT/'build/QuoteProbe.json').read_text())
    data='0x'+(keccak(text='roundTrip(address,address,address,uint24,uint256)')[:4]+encode(
        ['address','address','address','uint24','uint256'],[ROUTER,WETH,TOKEN,10000,amount])).hex()
    result=r.call('eth_call',[{'to':PROBE,'data':data},block,
        {PROBE:{'code':'0x'+artifact['evm']['deployedBytecode']['object'],'balance':hex(amount)}}])
    bought,returned=decode(['uint256','uint256'],bytes.fromhex(result[2:]))
    if bought<=0 or returned<=0 or returned>amount:raise ValueError('Unexpected round-trip result')
    loss=(amount-returned)*10000//amount
    if loss>cfg['max_total_fee_bps']:raise ValueError('Round-trip loss exceeds policy')
    hashes={a:'0x'+keccak(bytes.fromhex(r.call('eth_getCode',[a,block])[2:])).hex() for a in [TOKEN,POOL,ROUTER,FACTORY,WETH]}
    return {'token':TOKEN,'symbol':'PONS','pool':POOL,'router':ROUTER,'chain_id':4663,'block':b,
        'checked_at':time.time(),'pool_fee_bps':100,'active_liquidity':str(liquidity),
        'pool_weth_wei':str(weth_balance),'spend_wei':str(amount),'bought_units':str(bought),
        'returned_weth_wei':str(returned),'round_trip_loss_bps':loss,
        'observed_code_hashes':hashes,'simulation':'atomic_buy_and_sell_eth_call',
        'broadcast_enabled':False,'live_approved':False,
        'remaining_checks':['Live execution and recovery integration','Encrypted portable wallet backup']}

def sell_quote(units,rpc=None):
    if type(units) is not int or not 0<units<2**255:raise ValueError('Invalid token units')
    r=rpc or Rpc();r.validate_chain();block=r.call('eth_blockNumber')
    if r.call('eth_getCode',[PROBE,block])!='0x':raise ValueError('Probe address is occupied')
    artifact=json.loads((ROOT/'build/QuoteProbe.json').read_text())
    data='0x'+(keccak(text='quoteSell(address,uint256)')[:4]+encode(['address','uint256'],[POOL,units])).hex()
    result=r.call('eth_call',[{'to':PROBE,'data':data},block,{PROBE:{'code':'0x'+artifact['evm']['deployedBytecode']['object']}}])
    output=decode(['uint256'],bytes.fromhex(result[2:]))[0]
    if not output:raise ValueError('No sell output')
    return output

if __name__=='__main__':
    report=inspect_market()
    (ROOT/'.garden/selected-market.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
