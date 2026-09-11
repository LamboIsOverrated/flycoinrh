"""Read-only Robinhood/Pons adapter; intentionally cannot broadcast transactions."""
from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import time
import requests
from eth_abi import encode, decode
from eth_utils import keccak, to_checksum_address

ROOT = Path(__file__).parent
ZERO = '0x' + '0' * 40
ALLOWED_RPC = frozenset({'eth_chainId', 'eth_blockNumber', 'eth_getBalance',
                        'eth_getCode', 'eth_call', 'eth_estimateGas', 'eth_gasPrice',
                        'eth_getTransactionCount', 'eth_getTransactionReceipt', 'eth_getLogs', 'eth_getBlockByNumber'})

def load_config():
    config = json.loads((ROOT / 'pilot_config.json').read_text())
    if type(config['broadcast_enabled']) is not bool or config['chain_id'] != 4663:
        raise ValueError('This pilot only supports Robinhood mainnet with an explicit broadcast flag')
    if int(config['total_budget_wei']) > 10**16 or int(config['per_fly_budget_wei']) * 10 > int(config['total_budget_wei']):
        raise ValueError('Configuration exceeds the approved 0.01 ETH pilot budget')
    return config

class Rpc:
    def __init__(self, url=None):
        local = ROOT / '.garden' / 'connection.json'
        settings = json.loads(local.read_text()) if local.exists() else {}
        self.url = url or os.getenv('GARDEN_RPC_URL') or settings.get('rpc_url') or 'https://rpc.mainnet.chain.robinhood.com'
        if not self.url.startswith('https://'):
            raise ValueError('An HTTPS mainnet RPC endpoint is required')
        self.session = requests.Session()

    def call(self, method, params=None):
        if method not in ALLOWED_RPC:
            raise PermissionError('RPC method blocked: this adapter cannot broadcast or sign')
        try:
            response = self.session.post(self.url, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or []}, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            # Do not leak the endpoint or embedded API key into reports.
            raise ConnectionError('Mainnet RPC unavailable; configure an accessible provider endpoint') from None
        if data.get('error'):
            raise RuntimeError(f'RPC {method} rejected the read or simulation')
        if 'result' not in data:
            raise RuntimeError('Malformed RPC response')
        return data['result']

    def validate_chain(self):
        chain = int(self.call('eth_chainId'), 16)
        if chain != 4663:
            raise ValueError('Wrong chain: Robinhood mainnet 4663 required')
        return chain

    def view(self, address, signature, outputs, types=(), values=(), block='latest'):
        data = '0x' + (keccak(text=signature)[:4] + encode(list(types), list(values))).hex()
        result = self.call('eth_call', [{'to': to_checksum_address(address), 'data': data}, block])
        return decode(outputs, bytes.fromhex(result[2:]))

@dataclass(frozen=True)
class Curve:
    token: str
    curve: str
    block: int
    observed_at: float
    quote_reserve: int
    token_reserve: int
    real_quote: int
    reserved_tokens: int
    fee_bps: int
    tax_bps: int
    code_hash: str

    def buy_quote(self, spend):
        if type(spend) is not int or spend <= 0:
            raise ValueError('Positive integer wei required')
        net = spend - spend*self.fee_bps//10000 - spend*self.tax_bps//10000
        out = net*self.token_reserve//(self.quote_reserve+net)
        if out <= 0 or out >= self.token_reserve-self.reserved_tokens:
            raise ValueError('Unquotable trade or graduation boundary')
        return out

    def sell_quote(self, units):
        if type(units) is not int or units <= 0:
            raise ValueError('Positive integer token units required')
        gross = units*self.quote_reserve//(self.token_reserve+units)
        out = gross-gross*self.fee_bps//10000-gross*self.tax_bps//10000
        if out <= 0 or gross > self.real_quote:
            raise ValueError('Insufficient real quote liquidity')
        return out

class Pons:
    def __init__(self, rpc, config=None):
        self.rpc, self.config = rpc, config or load_config()

    def read_curve(self, token):
        cfg, rpc = self.config, self.rpc
        approved = next((x for x in cfg['approved_tokens'] if x['token'].lower() == token.lower()), None)
        if not approved or not cfg.get('verified_factory_codehash'):
            raise PermissionError('Token and deployed factory must be independently verified first')
        rpc.validate_chain()
        block = int(rpc.call('eth_blockNumber'), 16)
        tag = hex(block)
        factory_code = rpc.call('eth_getCode', [cfg['factory'], tag])
        if '0x'+keccak(bytes.fromhex(factory_code[2:])).hex() != cfg['verified_factory_codehash']:
            raise ValueError('Factory code hash changed')
        # Exact ABI from the official Pons V2 source; incompatible revisions fail.
        outputs = ['address']*5+['uint256','uint24','int24','uint16','bool','uint8','uint256','uint256','uint256','bool']
        launch = rpc.view(cfg['factory'], 'getLaunchedToken(address)', outputs, ['address'], [token], tag)
        if not launch[-1] or launch[0].lower() != token.lower() or launch[4] != ZERO or launch[10] != 0:
            raise ValueError('Only ungraduated native-ETH launches supported by this pilot')
        curve = to_checksum_address(launch[1])
        code = rpc.call('eth_getCode', [curve, tag])
        codehash = '0x'+keccak(bytes.fromhex(code[2:])).hex()
        if codehash != approved['curve_codehash']:
            raise ValueError('Curve code hash mismatch')
        read = lambda sig, out: rpc.view(curve, sig, out, block=tag)
        if read('factory()', ['address'])[0].lower() != cfg['factory'].lower() or read('token()', ['address'])[0].lower() != token.lower():
            raise ValueError('Curve provenance mismatch')
        if read('pairToken()', ['address'])[0] != ZERO or read('graduated()', ['bool'])[0] or read('readyToGraduate()', ['bool'])[0]:
            raise ValueError('Unsupported or completed curve')
        if rpc.view(curve,'currentSnipeTaxBps(address)',['uint256'],['address'],[ZERO],tag)[0] != 0:
            raise ValueError('Launch tax window is still active')
        quote, tokens = read('getReserves()', ['uint256','uint256'])
        real = read('realQuoteReserve()', ['uint256'])[0]
        reserved = read('reservedTokens()', ['uint256'])[0]
        fee, tax = read('feeBps()', ['uint256'])[0], read('creatorTaxBps()', ['uint256'])[0]
        if fee+tax > cfg['max_total_fee_bps'] or min(quote,tokens,real) <= 0:
            raise ValueError('Fee or liquidity policy rejected the market')
        return Curve(to_checksum_address(token), curve, block, time.time(), quote,tokens,real,reserved,fee,tax,codehash)

def buy_intent(curve, wallet, spend, cash, total_token_value, gas_cost, config=None, now=None):
    cfg = config or load_config()
    if any(type(v) is not int or v < 0 for v in [spend,cash,total_token_value,gas_cost]):
        raise ValueError('All financial quantities must be nonnegative integer wei')
    if spend <= 0 or spend > int(cfg['max_trade_wei']):
        raise ValueError('Trade size rejected')
    age = (time.time() if now is None else now)-curve.observed_at
    if age < 0 or age > cfg['max_quote_age_seconds']:
        raise ValueError('Stale quote')
    if cash-spend-gas_cost < int(cfg['gas_reserve_wei']):
        raise ValueError('Gas reserve would be consumed')
    # Full portfolio valuation is mandatory; also account for this buy's price impact.
    worth = cash+total_token_value-gas_cost
    if (total_token_value+spend)*2 > worth:
        raise ValueError('Aggregate token exposure exceeds 50%')
    units = curve.buy_quote(spend)
    net=spend-spend*curve.fee_bps//10000-spend*curve.tax_bps//10000
    acquired_mark=units*(curve.quote_reserve+net)//(curve.token_reserve-units)
    # Applying this curve's appreciation to all positions is conservative.
    appreciation_num=(curve.quote_reserve+net)*curve.token_reserve
    appreciation_den=curve.quote_reserve*(curve.token_reserve-units)
    future_exposure=(total_token_value*appreciation_num+appreciation_den-1)//appreciation_den+acquired_mark
    if future_exposure>cash-spend-gas_cost:
        raise ValueError('Post-trade marked exposure would exceed 50%')
    minimum = units*(10000-cfg['max_slippage_bps'])//10000
    if minimum <= 0:
        raise ValueError('Minimum output must be positive')
    data = '0x'+(keccak(text='buy(uint256,uint256,address)')[:4]+encode(['uint256','uint256','address'],[spend,minimum,wallet])).hex()
    return {'chainId':4663,'from':to_checksum_address(wallet),'to':curve.curve,'value':hex(spend),'data':data,
            'quote_block':curve.block,'quote_expires_at':curve.observed_at+cfg['max_quote_age_seconds'],
            'expected_units':str(units),'minimum_units':str(minimum),'status':'prepared_only'}

def preflight(wallets):
    cfg = load_config()
    report = {'checked_at':time.time(),'broadcast_enabled':False,'chain_id':4663,
              'budget_wei':cfg['total_budget_wei'],'wallets':[{**w,'balance_wei':None} for w in wallets],
              'blockers':[],
              'markets':[]}
    try:
        rpc=Rpc();rpc.validate_chain()
        report['block']=int(rpc.call('eth_blockNumber'),16)
        for row in report['wallets']:
            row['balance_wei']=str(int(rpc.call('eth_getBalance',[row['address'],hex(report['block'])]),16))
        for token in cfg['approved_tokens']:
            report['markets'].append(asdict(Pons(rpc,cfg).read_curve(token['token'])))
    except Exception as error:
        report['blockers'].append(str(error))
    selected=ROOT/'.garden/selected-market.json'
    if selected.exists():
        report['markets'].append(json.loads(selected.read_text()))
    else:
        report['blockers'].append('Selected PONS market has not completed its quote check')
    from live_execution import backup_ready
    if not backup_ready():report['blockers'].append('Complete the local portable encrypted wallet backup before funding')
    if not cfg['broadcast_enabled']:report['blockers'].append('Automatic execution is disabled')
    report['broadcast_enabled']=cfg['broadcast_enabled']
    report['ready_to_fund']=not report['blockers'] and all(w['balance_wei']=='0' for w in report['wallets'])
    return report
