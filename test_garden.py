import unittest
from decimal import Decimal as D
from garden import Garden


class AccountingTests(unittest.TestCase):
    def test_ten_independent_flies(self):
        garden = Garden('1')
        self.assertEqual(len(garden.flies), 10)
        garden.paper_buy(0, 'TEST', '.5', {'TEST': '1'})
        self.assertEqual(garden.flies[1].holdings, {})

    def test_cap_is_aggregate_and_accounts_for_fees(self):
        garden = Garden('1')
        prices = {'A': '1', 'B': '2'}
        garden.paper_buy(0, 'A', '.25', prices)
        with self.assertRaises(ValueError):
            garden.paper_buy(0, 'B', '.25', prices, '.01')
        garden.paper_buy(0, 'B', '.245', prices, '.01')
        self.assertEqual(garden.flies[0].token_value(prices), D('.495'))
        self.assertEqual(garden.flies[0].cash, D('.495'))

    def test_price_rise_blocks_buys_and_reports_rebalance(self):
        garden = Garden('1')
        garden.paper_buy(0, 'A', '.5', {'A': '1'})
        self.assertEqual(garden.exposure_excess(0, {'A': '2'}), D('.25'))
        self.assertEqual(garden.flies[0].buy_budget({'A': '2'}), 0)
        garden.paper_sell(0, 'A', '.125', {'A': '2'})
        self.assertEqual(garden.exposure_excess(0, {'A': '2'}), 0)

    def test_rejected_operation_does_not_change_balances(self):
        garden = Garden('1')
        for bad in ['-1', 'NaN', 'Infinity', '0']:
            with self.assertRaises(ValueError):
                garden.paper_buy(0, 'A', bad, {'A': '1'})
        self.assertEqual(garden.flies[0].cash, 1)
        self.assertEqual(garden.events, [])

    def test_missing_quote_fails_closed(self):
        garden = Garden('1')
        garden.paper_buy(0, 'A', '.2', {'A': '1'})
        with self.assertRaises(KeyError):
            garden.paper_buy(0, 'B', '.1', {'B': '1'})


if __name__ == '__main__':
    unittest.main()
