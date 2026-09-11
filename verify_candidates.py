"""Match factory-created contracts to independently recompiled runtime templates.

Only compiler-declared immutable byte ranges may differ. No opcode, metadata,
library link or arbitrary byte range is ignored. Factory/token/curve relationships
and live curve economics are checked independently through Pons.read_curve.
"""
import json
from pathlib import Path
import time
from eth_utils import keccak,to_checksum_address
from pilot_chain import Rpc,Pons,load_config

ROOT=Path(__file__).parent

def match_template(code,template):
    if template.get('linkReferences'):raise ValueError('Linked library template unsupported')
    actual=bytearray.fromhex(code.removeprefix('0x'))
    expected=bytearray.fromhex(template['object'])
    if len(actual)!=len(expected):return False
    for entries in template.get('immutableReferences',{}).values():
        for entry in entries:
            start,length=entry['start'],entry['length']
            if start<0 or length!=32 or start+length>len(actual):raise ValueError('Invalid compiler immutable range')
            actual[start:start+length]=b'\0'*length
            expected[start:start+length]=b'\0'*length
    return actual==expected

def main():
    cfg=load_config();rpc=Rpc();rpc.validate_chain()
    templates=json.loads((ROOT/'scratch'/'pons-bytecode-templates.json').read_text())
    candidates=json.loads((ROOT/'.garden'/'market-discovery.json').read_text())['rejected']
    found=[];rejected=[]
    for row in candidates:
        token=to_checksum_address(row['token'])
        try:
            fields=['address']*5+['uint256','uint24','int24','uint16','bool','uint8','uint256','uint256','uint256','bool']
            launch=rpc.view(cfg['factory'],'getLaunchedToken(address)',fields,['address'],[token])
            curve=to_checksum_address(launch[1]);code=rpc.call('eth_getCode',[curve,'latest'])
            if not match_template(code,templates['PonsV2BondingCurve']):raise ValueError('Curve runtime does not match verified compiled template')
            token_code=rpc.call('eth_getCode',[token,'latest'])
            if not match_template(token_code,templates['PonsV2LauncherToken']):raise ValueError('Token runtime does not match verified compiled template')
            entry={'token':token,'curve':curve,'curve_codehash':'0x'+keccak(bytes.fromhex(code[2:])).hex(),
                   'token_codehash':'0x'+keccak(bytes.fromhex(token_code[2:])).hex(),
                   'verification':'exact runtime template match excluding compiler-declared immutables',
                   'source_sha256':templates['PonsV2BondingCurve']['sourceSha256'],'verified_at':time.time()}
            market=Pons(rpc,{**cfg,'approved_tokens':[entry]}).read_curve(token)
            if market.real_quote<10**17:raise ValueError('Less than 0.1 ETH real quote liquidity')
            entry['symbol']=rpc.view(token,'symbol()',['string'])[0][:32]
            found.append(entry);print(json.dumps({'token':token,'symbol':entry['symbol'],'real_quote_wei':str(market.real_quote),'verified':True}),flush=True)
        except Exception as error:rejected.append({'token':token,'reason':str(error)[:180]})
        if len(found)>=3:break
    cfg['approved_tokens']=found
    (ROOT/'pilot_config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    (ROOT/'.garden'/'candidate-verification.json').write_text(json.dumps({'accepted':found,'rejected':rejected},indent=2))
    print(json.dumps({'accepted':len(found),'rejected':rejected}),flush=True)

if __name__=='__main__':main()
