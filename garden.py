"""Fly Garden accounting foundation. No signing or transaction broadcasting.

All values are ETH-denominated Decimal values. Prices must come from a future
verified market adapter; this module does not invent Pons prices.
"""
from dataclasses import dataclass, field
from decimal import Decimal

D = Decimal
EXPOSURE_LIMIT = D('0.50')
CHAIN_ID = 4663


def amount(value):
    result = D(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('Amounts must be finite and nonnegative')
    return result


@dataclass
class Fly:
    name: str
    cash: Decimal = D('0')
    address: str | None = None
    holdings: dict[str, Decimal] = field(default_factory=dict)

    def token_value(self, prices):
        total = D('0')
        for token, units in self.holdings.items():
            if not units:
                continue
            price = amount(prices[token])
            if price == 0:
                raise ValueError('A positive price is required')
            total += units * price
        return total

    def net_worth(self, prices):
        return self.cash + self.token_value(prices)

    def buy_budget(self, prices, fee='0'):
        fee = amount(fee)
        exposure = self.token_value(prices)
        post_fee_worth = self.cash + exposure - fee
        return max(D('0'), min(self.cash - fee,
                              post_fee_worth * EXPOSURE_LIMIT - exposure))


class Garden:
    def __init__(self, starting_cash='0'):
        cash = amount(starting_cash)
        self.flies = [Fly(f'Fly {i + 1:02}', cash) for i in range(10)]
        self.events = []

    def paper_buy(self, index, token, spend, prices, fee='0'):
        fly = self.flies[index]
        spend, fee = amount(spend), amount(fee)
        price = amount(prices[token])
        if spend == 0 or price == 0:
            raise ValueError('Spend and price must be positive')
        if spend > fly.buy_budget(prices, fee):
            raise ValueError('Buy exceeds cash or aggregate 50% exposure cap')
        fly.cash -= spend + fee
        fly.holdings[token] = fly.holdings.get(token, D('0')) + spend / price
        self.events.append(dict(kind='paper_buy', fly=index, token=token,
                                eth=str(spend), fee=str(fee)))

    def paper_sell(self, index, token, units, prices, fee='0'):
        fly = self.flies[index]
        units, fee = amount(units), amount(fee)
        price = amount(prices[token])
        if units == 0 or price == 0 or units > fly.holdings.get(token, D('0')):
            raise ValueError('Invalid sale quantity or price')
        proceeds = units * price
        if proceeds < fee:
            raise ValueError('Sale proceeds do not cover fees')
        fly.holdings[token] -= units
        fly.cash += proceeds - fee
        self.events.append(dict(kind='paper_sell', fly=index, token=token,
                                eth=str(proceeds), fee=str(fee)))

    def exposure_excess(self, index, prices):
        """ETH of tokens to sell after price moves (before sale fees).

        Price appreciation can push exposure above 50% without a new buy.
        The future runner must handle this before permitting further buys.
        """
        fly = self.flies[index]
        return max(D('0'), fly.token_value(prices)
                   - fly.net_worth(prices) * EXPOSURE_LIMIT)
