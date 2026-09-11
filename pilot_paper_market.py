"""Paper settlement against fresh mainnet quotes. Never signs or broadcasts."""
from pilot_chain import load_config
from pilot_v3 import inspect_market, sell_quote

class PaperMarket:
    def __init__(self):self.config=load_config()

    def mark(self,fly):
        units=fly.get('pons_units',0)
        fly['token_value_wei']=sell_quote(units) if units else 0
        return fly['token_value_wei']

    def decide(self,fly,tick):
        cash=fly['paper_cash_wei']; value=self.mark(fly); worth=cash+value
        limit=int(self.config['per_fly_budget_wei'])*(10000-self.config['max_drawdown_bps'])//10000
        # Sell when necessary to restore the cap, or to stop after a portfolio loss.
        if value and (value>cash or worth<limit):
            units=fly['pons_units']; fly['pons_units']=0;fly['token_value_wei']=0
            fly['paper_cash_wei']+=value;fly['last_market_tick']=tick
            return {'kind':'paper_pons_sell','fly':fly['id'],'units':str(units),'wei':str(value),'settlement':'paper_only'}
        if worth<limit or tick-fly.get('last_market_tick',-10)<10:return None
        spend=min(int(self.config['max_trade_wei']),max(0,(cash-value)//2),max(0,cash-int(self.config['gas_reserve_wei'])))
        if spend<10**12:return None
        quote=inspect_market(amount=spend)
        units=int(quote['bought_units']);future_units=fly.get('pons_units',0)+units
        future_value=sell_quote(future_units)
        if future_value>cash-spend:return None
        fly['paper_cash_wei']-=spend;fly['pons_units']=future_units
        fly['token_value_wei']=future_value;fly['last_market_tick']=tick
        return {'kind':'paper_pons_buy','fly':fly['id'],'units':str(units),'wei':str(spend),
                'quote_block':quote['block'],'settlement':'paper_only','gas_modeled':False}
